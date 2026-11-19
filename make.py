"""Pick the next battle from queue.json and render: long video, Short A (whole battle),
Short B (key part), thumbnail and meta.json into out/."""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
q = json.load(open(os.path.join(HERE, "queue.json")))
done = json.load(open(os.path.join(HERE, "done.json")))
force = os.environ.get("BATTLE", "").strip()
bid = force or next((b for b in q if b not in done), None)
if not bid:
    sys.exit("queue empty: add battles to queue.json")
bf = os.path.join(HERE, "battles", bid + ".json")
B = json.load(open(bf))
os.makedirs("out", exist_ok=True)
def R(kind):
    """renderer command; a battle may give its own map frame per format (long_bbox / short_bbox)"""
    b = dict(B, bbox=B.get(kind + "_bbox") or B["bbox"])
    f = os.path.join(HERE, "battles", f".{bid}.{kind}.json")
    json.dump(b, open(f, "w"))
    return [sys.executable, os.path.join(HERE, "render.py"), f]
subprocess.run(R("long") + ["out/thumb.png", "--thumb", "out/thumb.png"], check=True)
subprocess.run(R("short") + ["out/short_a.mp4", "--short"], check=True)
part = "b" if (B.get("parts") or {}).get("b") else ""
subprocess.run(R("short") + ["out/short_b.mp4", "--short"] + (["--part", "b"] if part else []), check=True)
if os.environ.get("SKIP_LONG") != "1":
    subprocess.run(R("long") + ["out/long.mp4"], check=True)
y = B["yt"]
credit = ("\n\nMap: FrontLines Maps. Borders: historical-basemaps by A. Ourednik (GPL-3.0). "
          "Front lines are approximate and drawn from dated control of towns. Music: original, FrontLines Maps.")
tags = y["tags"] + ["FrontLines Maps", "war map", "military history", "history"]
hs = " ".join("#" + t.replace(" ", "") for t in y["tags"][:3])
def desc(lead):
    return f"{lead}\n\n{y['about']}\n\n💬 Which battle should we map next? Comment below.\n🔔 Subscribe to FrontLines Maps for a new battle every day.{credit}\n\n{hs} #history #{y.get('hashtag', 'ww2')}"
meta = {
  "battle": bid,
  "long": {"title": y["long_title"][:100], "description": desc(B["title"] + ", day by day on the map."), "tags": tags},
  "short_a": {"title": y["short_a_title"][:100], "description": desc(B["title"] + " #Shorts"), "tags": tags},
  "short_b": {"title": y["short_b_title"][:100], "description": desc(B["title"] + " #Shorts"), "tags": tags},
}
json.dump(meta, open("out/meta.json", "w"), indent=1, ensure_ascii=False)
if not force:
    done.append(bid)
    json.dump(done, open(os.path.join(HERE, "done.json"), "w"), indent=1)
print("made", bid)
