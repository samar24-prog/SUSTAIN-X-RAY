"""Vercel entrypoint: serves the FastAPI backend as one Python function for /api/*."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.main import create_app  # noqa: E402

app = create_app()
