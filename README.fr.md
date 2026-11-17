# PocketHome pour Home Assistant

Intégration Home Assistant **locale** (sans cloud ni MQTT) pour le chauffage **Elektrobock PocketHome**, centrale **PH-CJ39 WiFi** en mode LOCAL IP. Non officielle, sans lien avec Elektrobock.

> **Nécessite une centrale PH-CJ39 WiFi** (Elektrobock PocketHome) sur votre réseau, en mode LOCAL IP. Sans elle, l'intégration ne fait rien. Les anciennes centrales (ex. PH-CJ37) utilisent un autre protocole et ne sont **pas prises en charge**. Développée et testée avec une PH-CJ39 WiFi, des thermostats PH-ET7-V et un récepteur PH-BP1-P9 ; les autres modèles de la gamme ne sont pas testés.

Langues : English, Français, Deutsch, Čeština (entités, services, cartes). [English](README.md).

## Fonctions
- Une entité `climate` par thermostat : température, consigne, auto/manuel/éteint, chauffage en cours.
- **Les programmes restent dans la centrale et les thermostats** : HA est une « version web » plus pratique de l'app officielle. Aucun planificateur côté HA.
- Carte d'édition des programmes (fork de [heating-schedule-card](https://github.com/Pandetthe/heating-schedule-card), MIT) : 22 programmes en liste déroulante, 6 plages par jour, grille de 10 min, copier/coller d'un jour, renommage.
- Par thermostat : choix du programme, nom dans la centrale, qualité du lien radio, alerte « signal perdu », capteurs de puissance et d'énergie du radiateur.
- Modes de la centrale : été, absence (consigne imposée à toutes les pièces), vacances (période + température, ex. hors gel).
- Blueprint « signal perdu » : notification sur l'app HA mobile quand un thermostat ne répond plus (en général : piles vides).
- Vue de tableau de bord prête à l'emploi.

## Prérequis
- PH-CJ39 WiFi en mode **LOCAL IP** (appui de 4 à 10 s sur le bouton LOCAL IP ; la LED NET ON-LINE clignote 3,5 s allumée / 0,5 s éteinte). La centrale n'est alors plus visible du cloud du fabricant.
- Adresse IP de la centrale (réservation DHCP conseillée), port TCP 4000. Le protocole n'a **aucune authentification** : réseau de confiance seulement.
- Home Assistant 2025.1 ou plus (développé sur 2026.11).

## Installation
### HACS
1. Ouvrir HACS (sur Home Assistant 2026.11+ il est intégré : *Paramètres → Marketplace*) et ajouter `https://github.com/KlugFR/pockethome-ha` avec le bouton **« ajouter grâce à un lien »**, comme dépôt de type *Intégration*. Dans l'ancien HACS : menu ⋮ → *Dépôts personnalisés*.
2. Installer **PocketHome (Elektrobock)**, redémarrer Home Assistant.

### Manuelle
1. Créer l'archive avec `scripts/package.sh` (ou prendre `pockethome-<version>.zip` dans les releases) et la décompresser dans `/config/` pour obtenir `/config/custom_components/pockethome/`. Sur Home Assistant OS, `scripts/deploy.sh root@<ip-de-ha>` copie le dossier en SSH et redémarre HA.
2. Redémarrer Home Assistant.

### Configuration
1. *Paramètres → Appareils et services → Ajouter une intégration → PocketHome* : IP de la centrale, port 4000.
2. Vider le cache du navigateur une fois (Cmd/Ctrl+Maj+R) pour charger les cartes.
3. Saisir la puissance (W) de chaque radiateur (entité *Puissance du radiateur*) pour obtenir puissance et énergie.

Au démarrage, l'intégration copie le blueprint dans `/config/blueprints/automation/pockethome/` (elle écrase une copie modifiée).

## Tableau de bord
Dans l'onglet voulu : crayon → ⋮ → *Modifier en YAML*, puis coller [`dashboards/chauffage.yaml`](dashboards/chauffage.yaml). Trois cartes, sans identifiant d'entité à écrire :

```yaml
- type: custom:pockethome-modes-card       # été / absence / vacances
- type: custom:pockethome-rooms-card       # thermostats : chauffage, programme, énergie du jour
    # total_label: Chauffage total (maison + atelier)
    # extra_energy: sensor.shelly_..._energy   # ajoute un autre capteur d'énergie (kWh ou Wh) au total
- type: custom:pockethome-program-card     # éditeur ; `program: 10` fige un programme
```

## Alerte « signal perdu »
*Paramètres → Automatismes → Créer → Utiliser un blueprint → « PocketHome - alerte thermostat »* : choisir les capteurs **Signal perdu** des thermostats à piles, le téléphone (app HA mobile) et un délai (10 min). Ne pas choisir les thermostats hors réseau en permanence. Un second téléphone demande une seconde automatisation. Le drapeau « batterie faible » est désactivé par défaut : les accus NiCd/NiMH le signalent dès leur pose.

## Services
`pockethome.get_program`, `get_programs`, `set_program`, `copy_day` (*Outils de développement → Actions*).

## À savoir
- **Radio et piles** : lecture du cache de la centrale (sans radio) toutes les 60 s. Le bouton **Actualiser le thermostat (radio)** force une lecture radio (5 min minimum entre deux appuis) : chaque échange radio coûte de la pile.
- La centrale est capricieuse : elle ignore parfois une requête ou répond pour une autre pièce. Le client vérifie chaque réponse et réessaie ; les écritures sont contrôlées par relecture.
- Les programmes sont écrits en entier (comme l'app). Noms : 16 caractères (Latin-1).
- Le programme 1, d'usine, répète les débuts pour les plages inutilisées : l'intégration les masque.
- L'énergie est estimée : état de la sortie relevé toutes les 60 s × puissance saisie.
- Non vérifié : l'actualisation radio ne prouve pas que les thermostats prennent un nouveau mode (été/vacances). Protocole et niveaux de confiance : [`docs/protocole.fr.md`](docs/protocole.fr.md).

## Développement
```
python3 -m unittest discover tests
node tests/test_card.mjs
```
`docs/historique-du-projet.fr.md` est le journal de rétro-ingénierie.

## Crédits et licences
MIT, voir [LICENSE](LICENSE). La carte des programmes est un fork de heating-schedule-card © 2026 Jakub Jurczyk (MIT), voir `custom_components/pockethome/www/NOTICE.md`. « PocketHome » et « Elektrobock » sont des marques de leurs propriétaires ; l'icône fournie est originale, pas le logo du fabricant.
