import json
import time
from pathlib import Path
import shutil

SESSIONS_FILE = Path("config/capture_sessions.json")


def _load_sessions() -> dict:
    if not SESSIONS_FILE.exists():
        return {}
    try:
        return json.loads(SESSIONS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_sessions(sessions: dict) -> None:
    SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSIONS_FILE.write_text(json.dumps(sessions, indent=2), encoding="utf-8")


def start_session(category: str, camera_ip: str, base_name: str, ttl_sec: int = 10, max_images: int = 50) -> None:
    """Start or reset a capture session for a given category+camera."""
    sessions = _load_sessions()
    key = f"{category}:{camera_ip}"
    sessions[key] = {
        "category": category,
        "camera_ip": camera_ip,
        "base_name": base_name,
        "ttl_sec": ttl_sec,
        "max_images": max_images,
        "count": 0,
        "last_updated": time.time(),
    }
    _save_sessions(sessions)


def is_active(category: str, camera_ip: str) -> bool:
    sessions = _load_sessions()
    key = f"{category}:{camera_ip}"
    s = sessions.get(key)
    if not s:
        return False
    if s.get("count", 0) >= s.get("max_images", 0):
        return False
    return (time.time() - s.get("last_updated", 0)) <= s.get("ttl_sec", 10)


def touch(category: str, camera_ip: str) -> None:
    sessions = _load_sessions()
    key = f"{category}:{camera_ip}"
    if key in sessions:
        sessions[key]["last_updated"] = time.time()
        _save_sessions(sessions)


def append_image(category: str, camera_ip: str, source_path: Path) -> bool:
    sessions = _load_sessions()
    key = f"{category}:{camera_ip}"
    s = sessions.get(key)
    if not s:
        return False
    # Check active and limits
    if not is_active(category, camera_ip):
        return False
    count = int(s.get("count", 0)) + 1
    s["count"] = count
    s["last_updated"] = time.time()

    # Build destination path
    data_dir = Path("data") / category
    name_prefix = s["base_name"].split("_")[0]
    known_dir = data_dir / "known" / name_prefix
    known_dir.mkdir(parents=True, exist_ok=True)

    base_name = s["base_name"]
    name_parts = base_name.rsplit(".", 1)
    if len(name_parts) == 2:
        new_name = f"{name_parts[0]}_{count:03d}.{name_parts[1]}"
    else:
        new_name = f"{base_name}_{count:03d}.png"

    dest_file = known_dir / new_name
    try:
        shutil.copy2(source_path, dest_file)
        _save_sessions(sessions)
        return True
    except Exception:
        return False
