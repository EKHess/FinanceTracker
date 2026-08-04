import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    """Keep module-reload tests isolated while production uses a stable path."""
    monkeypatch.setenv("FINANCE_TRACKER_DATABASE", str(tmp_path / "data" / "finance.db"))
