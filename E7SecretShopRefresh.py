from __future__ import annotations

import sys

from app.bootstrap import run_app


if __name__ == "__main__":
    sys.exit(run_app(default_mode="mouse", from_legacy_entry=False))
