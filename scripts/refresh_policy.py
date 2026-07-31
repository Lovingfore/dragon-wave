import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


def parse_generated_at(payload):
    value = payload.get("metadata", {}).get("generatedAt")
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def should_refresh(payload, now=None, max_age_minutes=45, force=False):
    if force:
        return True
    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    generated_at = parse_generated_at(payload)
    if generated_at is None or generated_at > current_time:
        return True
    return current_time - generated_at >= timedelta(minutes=max_age_minutes)


def main():
    parser = argparse.ArgumentParser(
        description="Decide whether LFCX data needs a refresh"
    )
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--max-age-minutes", type=int, default=45)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        payload = json.loads(args.data.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        payload = {}
    print(
        str(
            should_refresh(
                payload,
                max_age_minutes=args.max_age_minutes,
                force=args.force,
            )
        ).lower()
    )


if __name__ == "__main__":
    main()
