# PocketHome for Home Assistant

Local (no cloud, no MQTT) Home Assistant integration for the **Elektrobock PocketHome** heating system, central unit **PH-CJ39 WiFi** in LOCAL IP mode. Unofficial: not affiliated with Elektrobock.

> **Requires a PH-CJ39 WiFi central unit** (Elektrobock PocketHome) on your network, in LOCAL IP mode. Without it the integration does nothing. Older central units (e.g. PH-CJ37) use a different protocol and are **not supported**. Developed and tested with one PH-CJ39 WiFi, PH-ET7-V thermostats and a PH-BP1-P9 receiver; other thermostat and receiver models of the range are untested.

Languages: English, Français, Deutsch, Čeština (entities, services, cards). Docs: [Français](README.fr.md).

## Features
- One `climate` entity per thermostat: temperature, setpoint, auto/manual/off, heating on/off.
- **Programs stay in the central unit and the thermostats**: Home Assistant is only a nicer "web version" of the official app. No scheduler runs in HA.
- Program editor card (fork of [heating-schedule-card](https://github.com/Pandetthe/heating-schedule-card), MIT): 22 programs in a drop-down, 6 slots per day, 10 min grid, day copy/paste, program renaming.
- Per thermostat: program selector, name in the central unit, radio link quality, "signal lost" alert, radiator power and energy sensors (for statistics).
- Central modes: summer, absence (setpoint imposed on every room), holiday (period + temperature, e.g. frost protection).
- "Signal lost" blueprint: push notification to the HA mobile app when a thermostat stops answering (usually empty batteries).
- Ready-made dashboard view.

## Requirements
- PH-CJ39 WiFi switched to **LOCAL IP** mode (press the LOCAL IP button 4–10 s; the NET ON-LINE LED blinks 3.5 s on / 0.5 s off). In this mode the unit is no longer visible from the vendor cloud.
- The unit's IP address (give it a DHCP reservation), TCP port 4000. The protocol has **no authentication**: keep the unit on a trusted network.
- Home Assistant 2025.1 or newer (developed on 2026.11).

## Security: the protocol is not encrypted or authenticated
While reverse-engineering the protocol we found that the official apps talk to the central unit in **clear text over TCP port 4000, with no password, no token and no encryption**. This is how the vendor's own apps work, not something this integration adds. Consequences:
- **Anyone who can reach the unit's IP address and port 4000 can read your heating state and change it**: setpoints, programs, summer/absence/holiday modes, even the room names.
- Anyone who can sniff the network segment can read the traffic.

So be careful where the central unit is connected:
- Keep it on a trusted network only: a separate VLAN or IoT network is best, reachable only from Home Assistant.
- **Never** expose port 4000 to the Internet (no port forwarding, no UPnP, no public tunnel).
- Do not put it on a guest or shared Wi-Fi.
- If your firewall allows it, accept connections to the unit from the Home Assistant host only.
- This integration adds no layer of its own: it cannot make the unit safer.

## Installation
### HACS
1. Open HACS (on Home Assistant 2026.11+ it is integrated: *Settings → Marketplace*) and add `https://github.com/KlugFR/pockethome-ha` by its link, as a repository of type *Integration*. In the Marketplace this is the "add via link" button (French UI: « ajouter grâce à un lien »); in classic HACS it is ⋮ → *Custom repositories*.
2. Install **PocketHome (Elektrobock)**, restart Home Assistant.

### Manual
1. Build the archive with `scripts/package.sh` (or take `pockethome-<version>.zip` from the releases) and unzip it into `/config/` so that `/config/custom_components/pockethome/` exists. On Home Assistant OS, `scripts/deploy.sh root@<ha-ip>` copies the folder over SSH and restarts HA.
2. Restart Home Assistant.

### Setup
1. *Settings → Devices & services → Add integration → PocketHome*: enter the central unit's IP address and port 4000.
2. Hard-refresh the browser (Cmd/Ctrl+Shift+R) once so the cards load.
3. Set the radiator power (W) of each thermostat (*Radiator power* entity) to get power and energy sensors.

The integration copies the blueprint to `/config/blueprints/automation/pockethome/` on startup (it overwrites a modified copy).

## Dashboard
Open the *Chauffage* view or any dashboard, pencil → ⋮ → *Edit in YAML*, and paste [`dashboards/chauffage.yaml`](dashboards/chauffage.yaml). It contains three cards, which need no entity id:

```yaml
- type: custom:pockethome-modes-card       # summer / absence / holiday
- type: custom:pockethome-rooms-card       # thermostats: heating, program drop-down, energy of the day
    # total_label: Heating total (house + workshop)
    # extra_energy: sensor.shelly_..._energy   # add another energy sensor (kWh or Wh) to the total
- type: custom:pockethome-program-card     # program editor; `program: 10` fixes one program
```

## Signal-lost alert
*Settings → Automations → Create → Use a blueprint → "PocketHome - thermostat alert"*: choose the **Signal lost** sensors of the battery-powered thermostats, your phone (HA mobile app) and a delay (10 min). Do not select thermostats that are permanently out of range. A second phone needs a second automation. The "battery low" flag is disabled by default: NiCd/NiMH cells report it as soon as they are installed.

## Services
`pockethome.get_program`, `get_programs`, `set_program`, `copy_day` (see *Developer tools → Actions*).

## Good to know
- **Radio and batteries**: the integration polls the central unit's cache (no radio) every 60 s. The **Refresh thermostat (radio)** button forces a radio read (5 min cooldown): each radio exchange costs thermostat battery.
- The unit is flaky: it sometimes ignores a request or answers about another room. The client checks every reply and retries; writes are verified by a read-back.
- Programs are written whole (like the app). Names: 16 characters (Latin-1).
- Program 1, the factory default, repeats start times for unused slots; the integration hides them.
- Energy is estimated: the thermostat output is sampled every 60 s and multiplied by the radiator power you entered.
- Not verified: whether a radio refresh pushes a new mode (summer/holiday) to the thermostats. See [`docs/protocole.fr.md`](docs/protocole.fr.md) for the reverse-engineered protocol and its confidence levels.
- Entity names and the cards are translated; the protocol notes are in French.

## Development
```
python3 -m unittest discover tests
node tests/test_card.mjs
```
`docs/historique-du-projet.fr.md` is the working log of the reverse engineering.

## Credits and licenses
MIT, see [LICENSE](LICENSE). The program card is a fork of heating-schedule-card © 2026 Jakub Jurczyk (MIT), see `custom_components/pockethome/www/NOTICE.md`. "PocketHome" and "Elektrobock" are their owners' trademarks; the icon shipped here is original, not the vendor's logo.
