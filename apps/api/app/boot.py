"""Container entrypoints. Migrations run in the API process before it listens."""

import os
import subprocess
import sys
from pathlib import Path


def _migrate() -> None:
    root = Path(__file__).resolve().parents[1]
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=root, check=True)


def main() -> None:
    role = sys.argv[1] if len(sys.argv) > 1 else "api"
    if role == "api":
        _migrate()
        os.execvp(
            sys.executable,
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"],
        )
    if role == "worker":
        os.execvp(sys.executable, [sys.executable, "-m", "arq", "app.workers.tasks.WorkerSettings"])
    raise SystemExit(f"Unknown role {role}")


if __name__ == "__main__":
    main()
