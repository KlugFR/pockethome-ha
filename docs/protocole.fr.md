# Protocole local PH-CJ39 (TCP 4000) — observé

Source : captures `pockethome.pcap` et `pockethome2.pcap` de l'app EOB PocketHome (macOS), puis rejeu en lecture seule avec `ph_probe.py`. **Aucun rapport avec la spec CJ37** (`PH protokol_v_01.xlsx`) : les trames de cette spec sont ignorées par la CJ39.

Niveau de confiance : ✅ vérifié contre l'app · 🟡 déduit des captures · ❓ inconnu.

## Transport
- TCP, port **4000**, sans authentification ni chiffrement ✅. L'app ouvre **une connexion par requête**.
- Mode LOCAL IP uniquement. La centrale ignore parfois une requête : réessayer sur une nouvelle connexion.

## Trame (TLV, grand-boutiste)
`tag(2) longueur(2) valeur`
- Réponse : bit 15 du tag positionné pour les tags simples (`378c` → `b78c`), bit `0x4000` ajouté à la longueur. Un tag déjà à `0x8000` reste identique 🟡.
- Requête groupée : `7fff` + longueur + TLV enchaînés. Réponse : `ffff` + `0x4000|longueur` + TLV 🟡.

## Requêtes de lecture
| Requête | Réponse |
|---|---|
| `378c 0000` | nom de la centrale, ASCII (`PHWIFI_000481`) ✅ |
| `3716 0000` | `IP,masque,passerelle` en ASCII ✅ |
| `b781 0000` | chaîne `ns-ios` 🟡 |
| `803d 0002 0007` | liste d'éléments : paires `(code, adresse)` ✅ |
| `8033 0001 NN` | nom de la pièce NN (1 à 6 vu) 🟡 |
| `8050 0004 <code> <x> <adr> <mode>` | fiche d'un élément (voir plus bas) |
| `800d 0001 NN` | programme NN (1 à 22) |
| `0037 0000` | compteur de changements (toujours 0 ici) ❓ |

**Piège (vu le 17 nov. à 11:13)** : une lecture en mode `00` peut renvoyer la fiche d'une *autre* pièce (adresse 1 demandée, pièce 7 reçue). **Toujours vérifier `v[0:3]`** (code, `15`, adresse) contre la clé demandée, et relire sinon.

Modes de `8050` : `00` lecture ✅ · `04` actualisation forcée, interroge le thermostat par radio ✅ · `01` : résultats incohérents, à éviter.
Clé `63 15 <adr>` pour une pièce (adr 1 à 7), `54 09 01` pour `PK 1`.

## Fiche d'une pièce (`8050`, valeur de 37 octets)
| Offset | Contenu |
|---|---|
| 0-1 | `63 15` (code élément `c` = PH-S75 pour la spec) |
| 2 | adresse de la pièce (1 à 7) |
| 3 | **numéro de programme** ✅ (vérifié sur les 7 pièces) |
| 10 | état S1 : bit 0 = sortie active ✅, bit 7 = hors réseau (erreur de communication) ✅ |
| 11 | température entière en °C ✅ (bit 7 = négative 🟡) |
| 12 | bits 0-3 = dixièmes ✅ ; bit 7 = **batterie faible** ✅ (rouge dans l'app ; vert si 0 ; pas de niveau en %) |
| 17-32 | nom de la pièce, ASCII sur 16 octets ✅ |
| 33 | rappel de l'adresse de la pièce |
| 34-35 | `8a` puis un octet commun à toutes les pièces connectées (`d0`), `d4` pour les 2 injoignables ; sens ❓ |
| 36 | **qualité du lien radio**, plus bas = meilleur 🟡 : WC 46 (5/5), Cuisine 59 (3-4/5), Disque 61 (2/5), Miam 63 (2/5), Dressing 69 (1/5). Seuils exacts des barres ❓ |
| 4-5 | `v[4]` : drapeaux (bit 0 auto, bit 3 non prioritaire) ; `v[5]` : consigne en demi-degrés ✅ |

Température validée : Cuisine 21,9 → 22,0 après actualisation, identique à l'app. Petite chambre et Lit lisent 0,0 avec `S1 = 0x80` : probablement injoignables.

## Pièces (adresse → nom → programme)
1 Cuisine → 2 · 2 Dressing → 4 · 3 Petite chambre → 4 · 4 Disque → 2 · 5 Lit → 4 · 6 WC → 1 · 7 Miam → 2.

## Programmes (`800d`, 22 au total)
Valeur de 102 octets : `NN` + 7 jours (lundi en premier) × 6 plages × `(début, température)` + 1 octet de drapeau + nom ASCII sur 16 octets.
- Température = octet ÷ 2 ✅ (0x22 = 17 °C, 0x2a = 21, 0x30 = 24).
- **Début = 8 × heure + minutes ÷ 10** ✅ (8 cases de 10 min par heure, dont 6 utilisées) : `33` = 6 h 30, `39` = 7 h 10, `40` = 8 h, `bd` = 23 h 50. `bd` est la valeur de remplissage des plages inutilisées, celle que l'app propose par défaut. (La règle « pas de 7,5 min » notée avant était une coïncidence.)
- Remplissage convention de l'app : `bd` avec la température de la dernière plage utilisée. Écriture et relecture vérifiées sur le programme 10 (17 nov.). Une plage inutilisée est `bd` (+ une température sans effet).
- Une plage vaut jusqu'au début de la suivante. Les plages sont rangées dans l'ordre horaire.
- Index 1 `19`, 2 `22`, 3 `18.5 - 21.5`, 4 `18`. Le programme 10 (`Test HA`) est utilisé pour les tests.

Écriture : tag `000d`, longueur `0066`, même valeur de 102 octets ✅ (capture 4). L'app envoie le programme **entier** à chaque écriture, et renvoie aussi le nom. Les clics « sauvegarde » du lundi et du mardi n'ont rien envoyé sur le réseau : tout est parti d'un coup au renommage.

Exemple lu (programme 10, lundi puis mardi) :
`00 22 | 33 2a | 40 22 | bd 0a …` → 0 h 17 °C, 6 h 22 min **21 °C**, 8 h 17 °C
`00 24 | 39 30 | 48 22 | bd 0a …` → 0 h 18 °C, 7 h 07 min **24 °C**, 9 h 17 °C
Saisi dans l'app : 6 h 30 et 7 h 10, octets `33` et `39` (= 8×6+3 et 8×7+1).

## État de la sortie d'une pièce ✅
`v[10]` bit 0 = sortie active. Vu le 17 nov. à 11:15 : consigne de Miam forcée à 23 °C pour 21,9 °C mesurés, `v[10]` passe de `00` à `01` en moins de 2 min. Tout le reste de la fiche est inchangé (température exclue).

## `PK 1` (sortie « chaudière » du PH-BP1-P9)
Pendant que Miam chauffait (`v[10] = 01`), la fiche de `PK 1` n'a pas changé et `803f 0001 00` (« élément qui a activé la chaudière » ?) a répondu `0000`. Hypothèse 🟡 : les pièces sont des éléments **non prioritaires** (`v[4]` bit 3, `09`/`29`), qui ne commandent pas la chaudière, d'où l'absence de changement. À confirmer avec un élément prioritaire.
Élément `54 09 01`, nom `PK 1`, invisible dans l'app (ce n'est pas une pièce). L'état on/off n'est pas encore identifié ❓ : fiche `19 26 00 00 00 00 80 00 20 00 2a 00 00` + `01 00 00 ff`.

## Consigne et mode (capture 3, WC, vérifié par les relectures)
Lecture, dans la fiche `8050` : `v[5]` = **consigne en demi-degrés** (0x26 = 19,0 °C) ✅, `v[4]` = drapeaux : `09` = auto, `0a` = manu ✅ (bit 0 = auto, selon la spec).

Écriture : tag `0050` (sans bit 15), longueur `1e` (30 octets), 🟡 :
`63 15 | adr | 01 | programme | mode | consigne | 00 00 | on/off | 00 00 | nom(16) | <pièce> 26` (corrigé par la capture 9 ; l'ordre `01`/`programme` avait été inversé)
Valeurs de `mode` observées : `00` = manu, `02` = auto (avec consigne temporaire).
`on/off` (octet 9 de la valeur) ✅ : `00` = allumé, `02` = éteint. Éteint : `v[4]` passe de `09` à `0d` (bit 2) et la consigne lue vaut 0,0.
Changer de programme ✅ : champ `programme` + `consigne` = celle du nouveau programme (l'app envoie les deux ; la centrale relit programme et consigne).
Option « dépendant » : grisée dans l'app pour ce type de thermostat, comme le verrou clavier.
**Écriture testée ✅ (17 nov., Miam, valeurs identiques)** : la centrale répond par la fiche complète de la pièce (`8050 4025 …`), et une relecture 3 s plus tard est identique. Les 2 derniers octets sont `v[33]` (numéro de pièce) et `v[14]` de la fiche lue. La relecture confirme chaque écriture. L'app « actualise » ensuite avec `8050 0004 6315 <adr> 04`, puis interroge le compteur `7fff 0004 0037 0000` (réponse constante `00000000`).

La centrale **accepte une consigne en mode auto** : elle reste en `09` avec la nouvelle consigne (19 → 21 °C lu). Le blocage n'existe donc pas côté centrale. Il est dans le thermostat ou rien du tout. Verrouillage clavier : sans effet sur ce type de thermostat (l'app décoche la case après « actualize »), aucune trame dédiée.
Icône « œil » + date dans l'app : dernier échange avec le device. Hypothèse ❓ : les 3 derniers octets de la fiche `8a xx yy`.

## Mode été et vacances (capture 5)
| Fonction | Lecture | Écriture |
|---|---|---|
| **Mode été** (`LR` = « Letní Režim ») | `cc52 0000` → `cc52 4001 <A/N>` ✅ | `4c52 0001 41` (`A` = on) · `4c52 0001 4e` (`N` = off) ✅ |
| **Vacances** | `803a 0000` → `803a 4004 <4 octets>` ✅ | `003a 0002 0803` (on) · `003a 0002 0403` (off) 🟡 |

Chaque écriture est confirmée par une réponse qui renvoie le nouvel état. État des vacances : off = `20 23 08 00`, on = `00 33 08 00` (octet 0 bit 5 effacé, octet 1 bit 4 posé). **Période de vacances** (capture 6) : tag `000e`, 11 octets, dans une trame groupée `7fff` suivie de `003a 0002 XX03` ✅ :
`début(aa mm jj hh mn) | fin(aa mm jj hh mn) | température`
- année = année − 2000, **mois de 1 à 12**, température en demi-degrés (`0e` = 7,0 °C, `1e` = 15,0 °C).
- Exemple vérifié : 19/11/2026 10:00 → 19/12/2026 12:00 à 7 °C = `1a 0b 13 0a 00 | 1a 0c 13 0c 00 | 0e`.
- Réponse : `800e 400b <mêmes 11 octets>` + l'état `803a`.
- Activation = bit `0x10` de l'octet 1 de l'état `803a` (`00 33 08 00` on, `00 23 08 00` off) ✅. L'octet 0 vaut `20` ou `00` selon la dernière écriture : sens ❓.
- Bascule rejouée telle que l'app la fait : on = `0803`, off = `0403` (`0003` et `0c03` existent aussi, ❓).
- 7 °C = « hors gel » (à proposer dans l'intégration).

**Atténuation centrale = mode « absence »** (manuel, sans dates, contrairement aux vacances ; capture 7) : même tag `003a`, ✅ pour les écritures vues, 🟡 pour leur sens :
- activer : `003a 0002 0503` → état `21 23 08 00` · désactiver : `003a 0002 0003` → état `00 23 08 00`.
- Bit 0 de l'octet 0 de l'état = atténuation active.
- **Température d'atténuation** (capture 8) : tag `5456`, 1 octet en demi-degrés ✅. Écriture `5456 0001 14` (= 10,0 °C) → réponse `d456 4001 14`. Lecture `d456 0000` → `d456 4001 <octet>` ✅. Défaut 26 °C (`34`).
- **Effet réel** ✅ : une fois active, la consigne de **toutes** les pièces (`v[5]` de la fiche) vaut la température d'atténuation (10 °C lu pendant le test), à la place du programme. ~~`v[13]` = drapeau atténuation~~ : **faux**, `v[13]` bit 7 reste à 1 sur toutes les pièces après désactivation (vérifié par le client le 17 nov.) ; sens de `v[13]` ❓. Pour savoir si l'absence est active, lire l'état `803a` (bit 0 de l'octet 0). C'est donc un repli global, pas un abaissement fixe de 3 °C.

Hypothèse sur le masque d'écriture `003a 0002 MM 03` (octet `MM`) 🟡 : bit 0 (`01`) = atténuation, bit 2 (`04`) = vacances « off », bit 3 (`08`) = vacances « on ». Les valeurs vues vont dans ce sens (`04`, `08`, `0c`, `05`, `00`). L'app renvoie donc tout le masque à chaque fois : **l'intégration doit lire l'état et conserver les autres bits** avant d'écrire, sinon elle risque de couper l'atténuation en basculant les vacances. À vérifier avant toute écriture. Atténuation centrale : pas encore capturée.

## Écritures
Seul le rejeu d'écritures vues dans l'app est envisageable, jamais de trame inventée.
