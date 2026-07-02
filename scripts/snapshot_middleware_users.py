"""Generate users.json from the committed middleware database on demand."""

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "llm-mw"))

from config import DATABASE_URL  # noqa: E402
from core.auth import snapshot_users_to_json  # noqa: E402
from core.db import init_pool  # noqa: E402


if __name__ == "__main__":
    init_pool(DATABASE_URL)
    print(f"Snapshotted {snapshot_users_to_json()} middleware users.")
