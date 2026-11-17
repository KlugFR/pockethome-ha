# Notice

`pockethome-program-card.js` and its modules are a **fork** of
[heating-schedule-card](https://github.com/Pandetthe/heating-schedule-card)
(Copyright (c) 2026 Jakub Jurczyk, MIT license, text in `LICENSE-heating-schedule-card`).

Changes made for PocketHome (Elektrobock PH-CJ39):

- Data source: `pockethome.get_program` / `pockethome.set_program` services instead of the `schedule/list` and `schedule/update` WebSocket commands. No `schedule` helper is needed.
- Model: a program day is a list of at most 6 slots `(start, temperature)`; a slot lasts until the next one, so the end of a block is not editable. The first block starts at 00:00.
- Time grid of 10 minutes; temperatures from 5 to 30 °C by 0.5 °C.
- Editable program name; no thermostat or area lookup; French translation; translations converted to JS modules (no build step).
