"""Point d'entrée du worker : découvre et sert tous les workflows du package `worker.workflows`."""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mistralai.workflows as workflows


async def main() -> None:
    workflow_classes = workflows.discover_all_workflows_in_package("worker.workflows")
    await workflows.run_worker(workflow_classes)


if __name__ == "__main__":
    asyncio.run(main())
