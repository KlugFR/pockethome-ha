# Forum post (Home Assistant community, "Share your Projects")

**Title:** PocketHome (Elektrobock PH-CJ39): local, no-cloud integration, looking for testers

---

Hi all,

I built a custom integration for the **Elektrobock PocketHome** heating system (the PH-CJ39 WiFi central unit with PH-ET7-V thermostats). It talks to the central unit directly on your LAN, with no cloud and no MQTT. The vendor publishes no protocol documentation, so I reverse-engineered it from network captures of the official app.

**What it does**
- One `climate` entity per thermostat: temperature, setpoint, auto / manual / off, heating on/off.
- **Programs stay in the central unit and the thermostats.** Home Assistant is a nicer "web version" of the official app, not a scheduler.
- A program editor card (a fork of Pandetthe's heating-schedule-card, MIT): 22 programs in a drop-down, up to 6 slots a day on a 10 min grid, copy/paste of days, program renaming.
- Per thermostat: program selector, name stored in the central unit, radio link quality, a "signal lost" sensor, and optional radiator power / energy sensors for statistics.
- Central modes: summer, absence (one setpoint for all rooms) and holiday (period plus temperature, e.g. frost protection).
- A thermostats card with the heating state and the energy of the day per radiator and in total.
- A blueprint that sends a push notification to the HA mobile app when a thermostat stops answering (usually empty batteries).
- A ready-made dashboard view. The cards find their entities themselves, so there are no entity ids to write.
- Translated into English, French, German and Czech.

**Requirements**
- A **PH-CJ39 WiFi** central unit switched to **LOCAL IP** mode (press the LOCAL IP button for 4–10 s). In this mode it is no longer reachable from the vendor cloud.
- Its IP address, TCP port 4000. The protocol has **no authentication**, so keep the unit on a trusted network.
- Home Assistant 2025.1 or newer (developed on 2026.11). Older units such as the PH-CJ37 use a different protocol and are not supported.

**Security warning:** while reverse-engineering the protocol I found that the official apps talk to the central unit in **clear text over TCP port 4000, with no password, token or encryption**. Anyone who can reach the unit's IP address can read and change your heating (setpoints, programs, modes), and anyone sniffing the segment can read the traffic. Keep the unit on a trusted network (ideally an isolated VLAN reachable only from Home Assistant), never expose port 4000 to the Internet, and don't put it on a guest or shared Wi-Fi. The integration can't make this safer.

**Install with HACS**
1. Open HACS (on 2026.11 and later it is part of HA, under *Settings → Marketplace*).
2. Add `https://github.com/KlugFR/pockethome-ha` by its link (in the new Marketplace, the "add via link" button; in classic HACS, ⋮ → *Custom repositories*), as an *Integration*.
3. Install **PocketHome (Elektrobock)** and restart Home Assistant.
4. *Settings → Devices & services → Add integration → PocketHome*, enter the IP address and port 4000.
5. Hard-refresh the browser once so the cards load, then paste `dashboards/chauffage.yaml` from the repository into a dashboard view (⋮ → *Edit in YAML*).

**Manual install:** download `pockethome-0.3.0.zip` from the Releases page of the repository, unzip it into `/config/`, and restart.

**Transparency:** this integration was developed with substantial help from an AI coding assistant (Claude Code). I reviewed it, tested it against my own central unit, and take responsibility for it. The protocol was reverse-engineered from network captures of the official app.

**Good to know**
- Tested on my installation only: one PH-CJ39 WiFi, PH-ET7-V thermostats and a PH-BP1-P9 receiver. Other models of the range are untested.
- The central unit is flaky: it sometimes ignores a request or answers about another room. The client checks every reply and retries, and writes are verified by a read-back.
- Battery safety: the integration reads the central unit's cache every 60 s and never forces a radio read on its own. A "refresh (radio)" button does it on demand, with a 5 min cooldown.
- Energy is an estimate: the heating output is sampled every 60 s and multiplied by the radiator power you enter.
- The German and Czech translations have not been reviewed by native speakers: corrections welcome.
- Not verified yet: whether a radio refresh pushes a new summer/holiday mode to the thermostats.

This is an unofficial project, not affiliated with Elektrobock, and it can write to your heating controller. Please try it with that in mind.

Feedback and bug reports are welcome: https://github.com/KlugFR/pockethome-ha (issues are open). If you have a different PocketHome central unit or thermostat model and it works (or doesn't), I'd love to hear about it.
