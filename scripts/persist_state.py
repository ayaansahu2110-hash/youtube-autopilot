"""Merge published-video history safely after concurrent GitHub Actions runs."""

import json
import subprocess
import sys
from pathlib import Path


def command(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def merge_history(remote: dict, local: dict) -> dict:
    merged = dict(remote)
    videos = {item["video_id"]: item for item in remote.get("videos", []) if item.get("video_id")}
    for item in local.get("videos", []):
        video_id = item.get("video_id")
        if video_id:
            existing = videos.get(video_id, {})
            # Preserve the fuller production record and fresher analytics.
            videos[video_id] = {**item, **existing} if existing.get("script_preview") else {**existing, **item}
            if existing.get("analytics_updated_at", "") > item.get("analytics_updated_at", ""):
                videos[video_id]["analytics"] = existing.get("analytics", {})
                videos[video_id]["analytics_updated_at"] = existing["analytics_updated_at"]
    merged["videos"] = sorted(videos.values(), key=lambda item: item.get("created_at", ""))[-300:]
    topics = {}
    for item in [*remote.get("topics", []), *local.get("topics", [])]:
        key = (item.get("title") or item.get("topic", "")).lower().strip(), item.get("created_at", "")
        topics[key] = {**topics.get(key, {}), **item}
    merged["topics"] = sorted(topics.values(), key=lambda item: item.get("created_at", ""))[-300:]
    return merged


def persist(history_path: str, learning_path: str) -> None:
    paths = [Path(history_path), Path(learning_path)]
    local = {path: json.loads(path.read_text()) for path in paths if path.exists()}
    for attempt in range(5):
        command("fetch", "origin", "main")
        command("reset", "--hard", "origin/main")
        for path, value in local.items():
            remote = json.loads(path.read_text()) if path.exists() else {}
            if path == paths[0]:
                value = merge_history(remote, value)
            elif remote.get("generated_at", "") > value.get("generated_at", ""):
                value = remote
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
        command("add", *(str(path) for path in paths))
        if not command("diff", "--cached", "--name-only"):
            return
        command("commit", "-m", "chore: merge autopilot upload history [skip ci]")
        try:
            command("push", "origin", "HEAD:main")
            return
        except subprocess.CalledProcessError:
            print(f"Concurrent state update; merging again ({attempt + 1}/5)", flush=True)
    raise RuntimeError("Could not persist uploads after five concurrent update attempts")


if __name__ == "__main__":
    persist(sys.argv[1], sys.argv[2])
