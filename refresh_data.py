"""CLI entry point for automated and scheduled refreshes of the Iceland dashboard data."""

from __future__ import annotations

import argparse
import json
from data_pipeline import refresh_all


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh Iceland macroeconomic primary data.")
    parser.add_argument(
        "--trigger",
        default="cli",
        help="Trigger label recorded in refresh_log.jsonl (e.g., cli, scheduled_ci, windows_task).",
    )
    args = parser.parse_args()
    meta = refresh_all(trigger=args.trigger)
    print(json.dumps(meta, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
