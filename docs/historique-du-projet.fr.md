# PocketHome local : API et pont MQTT pour Home Assistant

Piloter en local, sans cloud, un chauffage **Elektrobock PocketHome** depuis Home Assistant.

## Matériel
- Centrale **PH-CJ39 WiFi**, utilisée en mode **LOCAL IP**.
- Thermostats **PH-ET7-V** : la programmation est dans les thermostats, les récepteurs sont passifs.
- Fabricant : ELEKTROBOCK CZ (`elektrobock.cz`, `elbock.cz`, `pockethome.cz`). Aucune doc technique publique trouvée.

## Ce qu'on sait
- **Applis officielles** : EOB PocketHome (Windows via le Microsoft Store, Android, iOS). Elles exigent une CJ39 en firmware 11.05 ou plus. La fiche App Store de l'appli iOS annonce macOS 11 ou plus sur puce Apple Silicon (non testé).
- **Modes réseau de la CJ39** : SERVER (cloud), LOCAL IP, AP. Un appui de 4 à 10 s sur le bouton LOCAL IP passe en mode local ; un deuxième appui revient en SERVER. La LED NET ON-LINE indique le mode : allumée en continu en SERVER, 3,5 s allumée / 0,5 s éteinte en LOCAL IP, 0,5 s allumée / 3,5 s éteinte en AP.
- **Connectique** : Wi-Fi, Ethernet, mini-USB.
- **Radio** : 433,92 MHz, bidirectionnelle, moins de 10 mW, portée jusqu'à 300 m. Chaque système a un identifiant unique d'usine, et les éléments sont appairés par apprentissage de code.
- **Spécification du protocole PC ↔ centrale** : dépôt GitHub [`chipsi007/PocketHome`](https://github.com/chipsi007/PocketHome), un seul fichier utile (`PH protokol_v_01.xlsx`, 2018, en tchèque). Synthèse en français dans `docs/protocole.fr.md`.
- Une intégration Home Assistant communautaire « EOB WiFi » existe pour les thermostats Wi-Fi d'Elektrobock, via leur cloud et leur serveur MQTT. Elle vise une autre gamme et rien ne dit qu'elle gère la CJ39.

## Résultat des captures (17 nov. 2026)
- La CJ39 écoute en **TCP 4000**, sans authentification. Son protocole TLV binaire **n'a rien à voir avec la spec CJ37** : voir `docs/protocole.fr.md`.
- Lecture seule validée avec `ph_probe.py` : nom de la centrale, réseau, 7 pièces (nom, température, programme), 22 programmes.
- À décoder : état de la sortie, `PK 1`, consigne, mode, heures des programmes, écritures.
- Décompiler l'app est inutile : les DLL iOS n'ont plus de code (AOT). Seules les captures servent.

## Exigences pour l'intégration HA
- **Le planning reste dans la centrale et les thermostats** : l'intégration est une version web, plus efficace, de l'app officielle. Pas de planificateur côté HA.
- Fonctions : éditer les programmes, forcer ponctuellement une consigne, mode été, remonter températures et niveau de batterie.
- Trois modes globaux, tous dans la centrale : **été** (tout éteint), **vacances** (période + température, par ex. 7 °C = hors gel), **absence** (= « atténuation centrale » de l'app : un switch + une température, sans dates, impose cette consigne à toutes les pièces). Le masque `003a` partagé par vacances et absence impose de lire l'état avant d'écrire.
- **Piles** : interroger en mode `00` seulement (pas de radio, 30 à 60 s). Le mode `04` (actualisation radio) uniquement sur demande, avec un délai minimum entre deux appuis par pièce.
- **Changement de mode été ou vacances** : après l'écriture, faire un `refresh` (mode `04`) de chaque pièce, une par une et espacées de quelques secondes. L'app ne le fait pas (vu dans la capture 5) et les thermostats ne se mettent à jour qu'à leur prochain contact avec la centrale, ce qui peut être long. Effet réel du `04` sur le thermostat : à vérifier.
- Requêtes une par une, connexions courtes : la CJ39 ignore parfois des requêtes concurrentes.
- **Édition des programmes bien plus efficace que l'app** (qui impose 6 plages par défaut, pas de copie de jour, saisie lourde) : modèle jour → liste de `(début, température)`, grille 10 min / 0,5 °C, copie de jour, écriture du programme entier puis relecture de contrôle.
- Une pièce = une entité `climate` (température, consigne, mode auto/manu, programme associé).
- La sortie chaudière `PK 1` est à exposer comme capteur, une fois son état décodé.

## Composant Home Assistant (`custom_components/pockethome/`)
- Entités : `climate` par pièce (consigne, auto/manu, on/off), liste de choix « Programme » et champ « Nom dans la centrale » par pièce (écrit le programme dans la centrale), capteurs (programme, lien radio), batterie, interrupteurs été / vacances / absence, températures et dates, bouton « Actualiser le thermostat (radio) » avec 5 min minimum.
- **Puissance et énergie** : champ « Puissance du radiateur » (W, saisi dans HA par pièce, mémorisé par HA, rien à voir avec la centrale), capteur « Puissance » (`device_class: power` : la puissance saisie quand la sortie du thermostat est active, 0 sinon) et capteur « Énergie » (`device_class: energy`, kWh, cumul compatible avec le tableau de bord Énergie). Relevé toutes les 60 s : approximation de la consommation réelle.
- **Alerte piles** : capteur « Signal perdu » par pièce (la centrale ne reçoit plus le thermostat : LED rouge clignotante, piles vides probables) et capteur « Batterie » (désactivé par défaut : les accus NiCd/NiMH sont signalés faibles dès leur pose). Le blueprint `blueprints/automation/pockethome/alerte_thermostat.yaml` (à copier dans `/config/blueprints/automation/pockethome/`) envoie une notification à l'app HA mobile quand l'un des capteurs « Signal perdu » choisis reste actif plus de N minutes. Ne pas choisir les capteurs des thermostats absents de l'installation (Petite chambre, Lit : hors réseau en permanence).
- Services : `get_program`, `get_programs`, `set_program`, `copy_day`.
- **Carte d'édition des programmes** : `www/pockethome-program-card.js`, **fork** de [heating-schedule-card](https://github.com/Pandetthe/heating-schedule-card) (MIT, © 2026 Jakub Jurczyk, licence conservée dans `www/LICENSE-heating-schedule-card`, changements dans `www/NOTICE.md`). Lit et écrit directement dans la centrale via les services ci-dessus. Chargée automatiquement par l'intégration. Usage dans un tableau de bord :
  ```yaml
  type: custom:pockethome-program-card
  program: 10
  ```
  Sans `program`, la carte affiche une liste déroulante des 22 programmes (le choix est mémorisé dans le navigateur). La liste est bloquée tant que des modifications ne sont pas enregistrées ou annulées.
- **Vue prête à l'emploi** : `dashboards/chauffage.yaml` (modes de la centrale, thermostats avec chauffage en cours, liste de choix du programme, énergie du jour (clic = historique) et total chauffage, éditeur de programmes). Les cartes `custom:pockethome-modes-card` et `custom:pockethome-rooms-card` (`www/pockethome-cards.js`) retrouvent les entités elles-mêmes : aucun identifiant à écrire.
- Tests : `python3 -m unittest discover tests` (protocole) et `node tests/test_card.mjs` (logique de la carte).
- Installation : copier `custom_components/pockethome/` dans `/config/custom_components/` de HA, redémarrer, ajouter l'intégration (IP de la centrale, port 4000), puis vider le cache du navigateur pour la carte.

## Ce qui reste à prouver (section historique, avant les captures)
- La spec date de l'époque CJ37 / PH-USB / PH-WEB. **Rien ne prouve que la CJ39 en mode local l'utilise telle quelle.**
- Ambiguïtés de la spec :
  - terminateur de trame : `FD FE 0D 0A` (lecture la plus probable) ou `FE FD 0D 0A` ;
  - mélange de valeurs décimales et hexadécimales ;
  - code de la commande « envoyer un programme » (13 décimal ou 0x13 ?) ;
  - lecture d'un programme : 42 octets contre 84 à l'envoi.
- Le **port TCP** de la centrale en mode local, l'authentification éventuelle et le chiffrement sont inconnus.
- Le PH-ET7-V n'est pas listé dans la spec. Il appartient sans doute à la famille BP7 (code élément `0x64`, `d`).

## Fichiers du projet
| Fichier | Rôle |
|---|---|
| `docs/protocole.fr.md` | Synthèse en français de la spec : trame, codes d'éléments, commandes, réponses, constantes, programmes |
| `docs/ph_probe.py` | Sonde en **lecture seule** (commandes `06 …`) en TCP ou série, avec `--dry-run`. Testée seulement contre un faux serveur |

## Plan de travail
1. Passer la CJ39 en mode LOCAL IP et relever son adresse IP (bail DHCP du routeur).
2. Scanner : `nmap -p- -sV <IP>` (et un scan UDP des ports courants si rien en TCP).
3. Capturer le trafic de l'appli officielle :
   ```
   sudo tcpdump -i en0 -w pockethome.pcap host <IP>
   ```
   pendant une séquence courte et chronométrée : ouvrir l'appli, lire l'état, changer une consigne de 0,5 °C puis la remettre, changer un programme.
4. Chercher dans la capture des trames du type `06 00 00 00 05 00 03` suivies du terminateur, et tester la sonde :
   ```
   python3 ph_probe.py --target tcp://<IP>:<PORT> hwid cjtemp counter
   ```
5. Si le protocole est confirmé :
   - écrire un client Python (lecture d'état, consignes, programmes, heure) ;
   - ajouter un pont MQTT avec découverte Home Assistant (entités `climate`, une par thermostat) ;
   - vérifier avec l'appli officielle que les deux clients cohabitent.
6. Si la CJ39 ne parle pas ce protocole : analyser la capture et l'appli (APK sous jadx) pour décoder le format réel.

## Précautions
- Ne tester d'abord que des **lectures**. Ne jamais envoyer de commande d'écriture (`02`, `07`, `08`, `09`, `0E`, `0F`, programmes) avant d'avoir compris la réponse de la centrale.
- Garder les réglages d'origine notés (programmes, consignes) avant toute écriture, pour pouvoir revenir en arrière.
- Une centrale en mode local n'est plus visible du cloud : l'appli ne fonctionnera à distance qu'en repassant en SERVER.

## Sources
- Notice et guide rapide PH-CJ39 WiFi (Elektrobock), notices PH-TS20, PH-PK20, PH-BP1-V, PH-ET7-V
- Fiches App Store et Microsoft Store de EOB PocketHome
- Dépôt GitHub `chipsi007/PocketHome`
- Forum Home Assistant : « EOB WiFi Integration »
