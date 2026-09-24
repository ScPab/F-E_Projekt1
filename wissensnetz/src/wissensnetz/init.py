"""Initialisierung des Stores (Aufgabe 1): Dataset sicherstellen + TBox laden.

Ablauf von :func:`initialize`:

1. Dataset ``databridge`` sicherstellen. Regulär legt es bereits der
   ``graph-db``-Container beim Start an (``FUSEKI_DATASET_1`` im
   ``stain/jena-fuseki``-Image, siehe ``graph-db/README.md``). Läuft der
   Container ohne diese Variable, wird das Dataset hier über die Fuseki-
   Admin-API nachgezogen — so ist ``wissensnetz init`` in sich abgeschlossen.
2. TBox ``ontology/databridge-core.ttl`` in den Default-Graph laden
   (idempotent: bei bereits vorhandener TBox übersprungen, außer ``force``).
3. Die Nebenvokabulare ``ontology/feedback.ttl`` (Rückkanal) und
   ``ontology/selection.ttl`` (Auswahl-Manifeste) ebenso — jeweils über eine
   eigene Marker-Abfrage, damit ein nachgereichtes Vokabular auch in einem
   bestehenden Store noch ankommt.

Die TBox liegt bewusst im selben (Default-)Graph wie später die ABox, damit
einfache SPARQL-Abfragen Klassen und Instanzen ohne ``GRAPH``-Klausel sehen.

English: Store initialization (task 1): ensure dataset + load TBox.

Flow of :func:`initialize`:

1. Ensure the ``databridge`` dataset. Normally the ``graph-db`` container
   already creates it on startup (``FUSEKI_DATASET_1`` in the
   ``stain/jena-fuseki`` image, see ``graph-db/README.md``). If the
   container runs without that variable, the dataset is created here
   retroactively via the Fuseki admin API — so ``wissensnetz init`` is
   self-contained.
2. Load the TBox ``ontology/databridge-core.ttl`` into the default graph
   (idempotent: skipped if the TBox is already present, unless ``force``).
3. Likewise the secondary vocabularies ``ontology/feedback.ttl`` (feedback
   channel) and ``ontology/selection.ttl`` (selection manifests) — each via
   its own marker query, so a vocabulary added later also arrives in an
   existing store.

The TBox deliberately lives in the same (default) graph as the ABox later,
so simple SPARQL queries see classes and instances without a ``GRAPH``
clause.
"""

from __future__ import annotations

from pathlib import Path

from .config import PREFIXES
from .graphstore import GraphStore

# ontology/ liegt im Paket-Repo neben src/ — von hier aus zwei Ebenen hoch.
# EN: ontology/ lives in the package repo next to src/ — two levels up from here.
_ONTOLOGY_DIR = Path(__file__).resolve().parents[2] / "ontology"
TBOX_PATH = _ONTOLOGY_DIR / "databridge-core.ttl"
# Rückkanal-Vokabular (Aufgabe 4), separat von der Kern-TBox gehalten.
# EN: Feedback-channel vocabulary (task 4), kept separate from the core TBox.
FEEDBACK_PATH = _ONTOLOGY_DIR / "feedback.ttl"
# Auswahl-Vokabular (Aufgabe 13), ebenfalls separat — siehe selection.py.
# EN: Selection vocabulary (task 13), also separate — see selection.py.
SELECTION_PATH = _ONTOLOGY_DIR / "selection.ttl"

# Marker-Abfragen: Ist die jeweilige TBox/das Vokabular bereits geladen?
# EN: Marker queries: is the respective TBox/vocabulary already loaded?
_TBOX_PRESENT = PREFIXES + "ASK { db:Case a owl:Class }"
_FEEDBACK_PRESENT = PREFIXES + "ASK { db:ExpertFinding a owl:Class }"
_SELECTION_PRESENT = PREFIXES + "ASK { db:Selection a owl:Class }"


def tbox_loaded(store: GraphStore) -> bool:
    """True, wenn die TBox (Marker-Klasse ``db:Case``) im Store vorhanden ist.

    English: True if the TBox (marker class ``db:Case``) is present in the store.
    """
    return store.ask(_TBOX_PRESENT)


def feedback_vocab_loaded(store: GraphStore) -> bool:
    """True, wenn das Rückkanal-Vokabular (``db:ExpertFinding``) vorhanden ist.

    English: True if the feedback-channel vocabulary (``db:ExpertFinding``) is present.
    """
    return store.ask(_FEEDBACK_PRESENT)


def selection_vocab_loaded(store: GraphStore) -> bool:
    """True, wenn das Auswahl-Vokabular (``db:Selection``) vorhanden ist.

    English: True if the selection vocabulary (``db:Selection``) is present.
    """
    return store.ask(_SELECTION_PRESENT)


def _load_vocab(store: GraphStore, path: Path, loaded: bool, *, force: bool) -> str:
    """Ein Nebenvokabular idempotent laden; gibt den Kurzbericht-Text zurück.

    English: Loads a secondary vocabulary idempotently; returns the short-report text.
    """
    if not path.exists():
        return "not found"
    if loaded and not force:
        return "skipped (bereits vorhanden)"
    store.load_turtle(path)
    return "reloaded (force)" if loaded else "loaded"


def initialize(
    store: GraphStore | None = None,
    *,
    tbox_path: Path = TBOX_PATH,
    force: bool = False,
) -> dict[str, object]:
    """Dataset sicherstellen und TBox laden. Liefert einen Kurzbericht.

    English: Ensures the dataset and loads the TBox. Returns a short report.
    """
    store = store or GraphStore()

    if not tbox_path.exists():
        raise FileNotFoundError(f"TBox-Datei nicht gefunden: {tbox_path}")

    dataset_created = store.ensure_dataset()

    already = tbox_loaded(store)
    if already and not force:
        tbox_action = "skipped (bereits vorhanden)"
    else:
        store.load_turtle(tbox_path)
        tbox_action = "reloaded (force)" if already else "loaded"

    # Nebenvokabulare (Aufgabe 4 Rückkanal, Aufgabe 13 Auswahl) mitladen.
    # EN: Also load the secondary vocabularies (task 4 feedback, task 13 selection).
    feedback_action = _load_vocab(
        store, FEEDBACK_PATH, feedback_vocab_loaded(store), force=force
    )
    selection_action = _load_vocab(
        store, SELECTION_PATH, selection_vocab_loaded(store), force=force
    )

    class_count = store.query(
        PREFIXES + "SELECT (COUNT(DISTINCT ?c) AS ?n) WHERE { ?c a owl:Class }"
    )
    n_classes = class_count[0].get("n") if class_count else "0"

    return {
        "dataset": store.settings.dataset,
        "dataset_created": dataset_created,
        "tbox": tbox_action,
        "feedback_vocab": feedback_action,
        "selection_vocab": selection_action,
        "owl_classes": n_classes,
    }
