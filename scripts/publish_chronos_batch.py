import sys
from autopilot.config import Settings
from autopilot.pipeline import AutopilotPipeline

topics = [
    "The Great Pyramid of Giza: Impossible Precision Engineering",
    "Göbekli Tepe: The 12,000-Year-Old Megalith That Defies History",
    "Derinkuyu: The Massive Ancient Underground City That Housed 20,000 People",
]

settings = Settings(
    channel_profile="chronosenigma",
    upload_privacy_status="public",
    allow_public_uploads=True,
    shorts_public=True,
    enable_uploads=True,
)
pipeline = AutopilotPipeline(settings)

for topic in topics:
    print(f"\n==========================================")
    print(f"PRODUCING CHRONOSENIGMA: {topic}")
    print(f"==========================================")
    try:
        res = pipeline.run(topic=topic, dry_run=False, video_format="short")
        print(f"RESULT: {res.status}")
        print(f"ID: {res.youtube_video_id}")
        print(f"TITLE: {res.plan.title}")
        print(f"NOTES: {res.notes}")
        if res.youtube_video_id:
            print(f"LIVE URL: https://youtube.com/shorts/{res.youtube_video_id}")
    except Exception as e:
        print(f"ERROR producing {topic}: {e}")
