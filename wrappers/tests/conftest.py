"""Pytest-Setup für die Wrapper-Tests.

Läuft auch ohne vorheriges ``pip install -e ./wrappers`` (Muster wie
``wrappers/gdc/scripts/check_connection.py``): ``wrappers/`` wird direkt auf
den Suchpfad gelegt, damit ``import gdc`` funktioniert.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
