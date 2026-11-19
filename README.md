# FrontLines Maps pipeline

Famous battles, day by day, on the map. Music only.

* `battles/<id>.json` – one battle: places with dated control changes, events, arrows, YouTube text.
* `queue.json` – order of battles; `done.json` – already made.
* `render.py` – renders a long 16:9 video, a 9:16 Short (`--short`), a part (`--part b`) or a thumbnail (`--thumb`).
* `music/styles.py` – original music (style `ottoman_slow`, chosen by the owner on 19 Nov 2026).
* `.github/workflows/daily.yml` – 16:00 MY every day: renders the next battle and pushes `long.mp4`, `short_a.mp4`, `short_b.mp4`, `thumb.png`, `meta.json` to the `out` branch.

Uploads to the FrontLines Maps channel are done by scheduled Claude tasks through Composio:
long + Short A at 19:30 MY, Short B at 09:30 MY the next day.
