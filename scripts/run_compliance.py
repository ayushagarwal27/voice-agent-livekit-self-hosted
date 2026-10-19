"""Re-run Phase 9 compliance checks for an already-ended call.

Usage: uv run python -m scripts.run_compliance <call_id>
(run as a module, not a bare script path, so the `storage`/`compliance`
packages resolve -- same reason scripts/seed_agent.py and
scripts/latency_report.py are invoked that way.)
"""

import asyncio
import json
import sys

from dotenv import load_dotenv

from compliance.runner import run_compliance

load_dotenv()


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: uv run python -m scripts.run_compliance <call_id>")
        raise SystemExit(1)

    call_id = int(sys.argv[1])
    result = asyncio.run(run_compliance(call_id))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
