"""Runner per-batch. Save raw video data ke JSON yang di-merge di akhir."""

import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from main import collect_following

BATCH_OUTPUT = Path("batch_results.json")
DAYS_BACK = 7


async def main():
    if len(sys.argv) < 3:
        print("Usage: python run_batch.py <batch_label> <username1> [username2] ...")
        sys.exit(1)

    batch_label = sys.argv[1]
    usernames = sys.argv[2:]

    token = os.environ.get("MS_TOKEN", "")
    if not token:
        print("MS_TOKEN missing")
        sys.exit(1)

    print(f"Batch '{batch_label}': {len(usernames)} username\n")
    videos, silent, errored = await collect_following(token, usernames, DAYS_BACK)

    # Load existing if present
    existing = {"batches": []}
    if BATCH_OUTPUT.exists():
        existing = json.loads(BATCH_OUTPUT.read_text(encoding="utf-8"))

    existing["batches"].append({
        "label": batch_label,
        "usernames_input": usernames,
        "videos": videos,
        "silent": silent,
        "errored": errored,
    })

    BATCH_OUTPUT.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n>>> Batch '{batch_label}' selesai")
    print(f"   posting: {len(set(v['username'] for v in videos))}  •  silent: {len(silent)}  •  error: {len(errored)}")
    print(f"   total video: {len(videos)}")


if __name__ == "__main__":
    asyncio.run(main())
