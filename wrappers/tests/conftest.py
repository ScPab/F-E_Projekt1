"""Pytest-Setup für die Wrapper-Tests.

Läuft auch ohne vorheriges ``pip install -e ./wrappers`` (Muster wie
``wrappers/gdc/scripts/check_connection.py``): ``wrappers/`` wird direkt auf
den Suchpfad gelegt, damit ``import gdc`` funktioniert.

English: Pytest setup for the wrapper tests.

Also runs without a prior ``pip install -e ./wrappers`` (pattern like
``wrappers/gdc/scripts/check_connection.py``): ``wrappers/`` is put
directly on the search path so ``import gdc`` works.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
