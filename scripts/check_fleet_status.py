import json

channels = [
    ("wondertales", "WonderTales Kids"),
    ("mokshavani", "MokshaVani"),
    ("apexstoic", "ApexStoic"),
    ("chronosenigma", "ChronosEnigma"),
    ("empirepulse", "EmpirePulse"),
]

for profile, name in channels:
    p = f"state/{profile}/history.json"
    with open(p, "r", encoding="utf-8") as f:
        d = json.load(f)
    vids = d.get("videos", [])
    print(f"=== {name} ({profile}): {len(vids)}/5 published ===")
    for idx, v in enumerate(vids, 1):
        vid_id = v.get("video_id")
        title = v.get("title")
        print(f"  {idx}. https://youtube.com/shorts/{vid_id} | {title}")
    print()
