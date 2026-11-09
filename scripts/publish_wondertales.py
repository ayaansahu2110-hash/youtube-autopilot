from autopilot.config import Settings
from autopilot.pipeline import AutopilotPipeline

print("Starting WonderTales live production run...")
settings = Settings(
    channel_profile="wondertales",
    upload_privacy_status="public",
    allow_public_uploads=True,
    shorts_public=True,
    enable_uploads=True,
)
pipeline = AutopilotPipeline(settings)
result = pipeline.run(dry_run=False, video_format="short")
print("STATUS:", result.status)
print("YOUTUBE ID:", result.youtube_video_id)
print("TITLE:", result.plan.title)
print("NOTES:", result.notes)
if result.youtube_video_id:
    print(f"URL: https://youtube.com/shorts/{result.youtube_video_id}")
