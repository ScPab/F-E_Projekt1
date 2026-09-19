"""Krebsart-Übersetzung — der Kern des "Back-Mediators" (M9, siehe
recherche/Umsetzungsplan_UI-gesteuerte-Akquise.pdf).

Die Panel-Zeile "Krebs" liefert einen GDC-Projekt-Code (z. B. "TCGA-BRCA"),
aber das ist eigentlich eine **Krebsart** ("Breast Invasive Carcinoma") — GEO
und cBioPortal kennen keine GDC-Projekt-Codes, wohl aber Freitext-/
Stichwortsuche. `_selection_fetch()` (app/main.py) übersetzt für Nicht-GDC-
Quellen daher nicht den rohen String, sondern dieses Konzept.

`TCGA_COHORT_NAMES` ist bewusst identisch zu `frontend/config/panel.json`s
`cohort_labels` (dort `project_id`-keyed) — beide stammen aus derselben
Quelle (`GET https://api.gdc.cancer.gov/projects`, Feld `name`, live
verifiziert 2026-09-18), damit es nicht zwei unabhängig gepflegte Listen
gibt, die auseinanderlaufen können.
"""

from __future__ import annotations

from wissensnetz.cohorts import cancer_code

# Kohortencode (ohne "TCGA-"-Präfix) -> GDC-Klarname. Nur als Freitext-
# Suchbegriff genutzt (GEO-Volltextsuche, cBioPortal `list_studies(keyword=...)`)
# — keine Ontologie-Alignment-Behauptung, daher anderer Sorgfaltsmaßstab als
# z. B. die NCIt-Alignment-Tabelle (wissensnetz/ontology/alignment/).
TCGA_COHORT_NAMES: dict[str, str] = {
    "ACC": "Adrenocortical Carcinoma",
    "CHOL": "Cholangiocarcinoma",
    "BLCA": "Bladder Urothelial Carcinoma",
    "BRCA": "Breast Invasive Carcinoma",
    "CESC": "Cervical Squamous Cell Carcinoma and Endocervical Adenocarcinoma",
    "COAD": "Colon Adenocarcinoma",
    "UCEC": "Uterine Corpus Endometrial Carcinoma",
    "ESCA": "Esophageal Carcinoma",
    "GBM": "Glioblastoma Multiforme",
    "HNSC": "Head and Neck Squamous Cell Carcinoma",
    "KICH": "Kidney Chromophobe",
    "KIRC": "Kidney Renal Clear Cell Carcinoma",
    "KIRP": "Kidney Renal Papillary Cell Carcinoma",
    "DLBC": "Lymphoid Neoplasm Diffuse Large B-cell Lymphoma",
    "LIHC": "Liver Hepatocellular Carcinoma",
    "LGG": "Brain Lower Grade Glioma",
    "LUAD": "Lung Adenocarcinoma",
    "LUSC": "Lung Squamous Cell Carcinoma",
    "SKCM": "Skin Cutaneous Melanoma",
    "MESO": "Mesothelioma",
    "UVM": "Uveal Melanoma",
    "OV": "Ovarian Serous Cystadenocarcinoma",
    "PAAD": "Pancreatic Adenocarcinoma",
    "PCPG": "Pheochromocytoma and Paraganglioma",
    "PRAD": "Prostate Adenocarcinoma",
    "READ": "Rectum Adenocarcinoma",
    "SARC": "Sarcoma",
    "STAD": "Stomach Adenocarcinoma",
    "TGCT": "Testicular Germ Cell Tumors",
    "THYM": "Thymoma",
    "THCA": "Thyroid Carcinoma",
    "UCS": "Uterine Carcinosarcoma",
}


def cancer_name(cohort: str) -> str:
    """Kohortencode/GDC-project_id -> Klarname. Unbekannter/neuer Code fällt
    auf den Rohwert zurück (kein Absturz, nur eine schwächere Suche)."""
    code = cancer_code(cohort) or cohort
    return TCGA_COHORT_NAMES.get(code.upper(), cohort)


# ---------------------------------------------------------------------------
# Demo-Genpanel für POST /selection/generate mit source="cbioportal": deren
# get_molecular_data() verlangt eine explizite entrezGeneIds-Liste — es gibt
# keinen Wrapper-Aufruf für "alle in einem Profil erfassten Gene". Bewusst
# klein und nur gut etablierte Onko-Gene; Entrez-IDs live gegen
# POST https://www.cbioportal.org/api/genes/fetch verifiziert (nicht geraten).
# Kein Anspruch auf Vollständigkeit — Demo-Default, kein kuratiertes Panel für
# echte Forschungsfragen.
# ---------------------------------------------------------------------------
DEMO_GENE_PANEL: dict[str, int] = {
    "TP53": 7157,
    "EGFR": 1956,
    "KRAS": 3845,
    "PIK3CA": 5290,
    "PTEN": 5728,
    "MYC": 4609,
    "ERBB2": 2064,
    "BRAF": 673,
    "APC": 324,
    "RB1": 5925,
    "VHL": 7428,
    "IDH1": 3417,
    "CTNNB1": 1499,
    "NF1": 4763,
    "ATM": 472,
}
