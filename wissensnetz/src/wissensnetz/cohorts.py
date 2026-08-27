"""Die 32 TCGA-Kohorten des Oviedo-Originals — **Single Source of Truth**.

Die Reihenfolge ist die kanonische Oviedo-Reihenfolge und bestimmt sowohl die
Lade-Reihenfolge (`scripts/load_gdc.py --pancancer`) als auch die Farb-/
Legenden-Ordnung in MP-lite (`prototype/mp_lite/app.py`). Beide Seiten
importieren diese Konstante, damit es genau **eine** Quelle gibt.

Dieses Modul ist bewusst abhängigkeitsfrei (nur stdlib), damit es Teil des
installierbaren ``wissensnetz``-Pakets bleiben kann (Paket-Deps: rdflib/requests).
Farb-/Colormap-Logik gehört in die Prototyp-Schicht, nicht hierher.
"""

from __future__ import annotations

# Kanonische Oviedo-Reihenfolge (GDC project_id = "TCGA-<code>").
OVIEDO_COHORTS: tuple[str, ...] = (
    "ACC", "CHOL", "BLCA", "BRCA", "CESC", "COAD", "UCEC", "ESCA", "GBM", "HNSC",
    "KICH", "KIRC", "KIRP", "DLBC", "LIHC", "LGG", "LUAD", "LUSC", "SKCM", "MESO",
    "UVM", "OV", "PAAD", "PCPG", "PRAD", "READ", "SARC", "STAD", "TGCT", "THYM",
    "THCA", "UCS",
)

# Vollständige GDC-project_id-Liste in derselben Reihenfolge.
COHORT_PROJECT_IDS: tuple[str, ...] = tuple(f"TCGA-{code}" for code in OVIEDO_COHORTS)

# Schneller Lookup: Krebs-Code -> Position in der Oviedo-Reihenfolge (für Farbe).
COHORT_INDEX: dict[str, int] = {code: i for i, code in enumerate(OVIEDO_COHORTS)}


def cancer_code(project_id: str | None) -> str | None:
    """``"TCGA-PRAD" -> "PRAD"`` (Präfix ``"TCGA-"`` abschneiden); sonst
    ``project_id`` unverändert. Ohne Wert ``None``."""
    if not project_id:
        return None
    pid = str(project_id)
    return pid[len("TCGA-"):] if pid.startswith("TCGA-") else pid
