"""
Wrapper für die cBioPortal API — https://www.cbioportal.org/api

Im Sinne des Mediator-Wrapper-Musters kapselt dieses Modul den gesamten
Zugriff auf eine konkrete Datenquelle (hier: cBioPortal, das bereits
aufbereitete klinische und genomische Krebsdaten aus vielen Studien
bereitstellt, u. a. auch TCGA/GDC-Daten in aufbereiteter Form) und liefert
Daten in einer vom Mediator erwarteten, normalisierten Zwischenform. Die
Transformation nach anndata/.h5ad ist bewusst NICHT Teil dieses Wrappers —
das ist ein separater, späterer Schritt auf Mediator-Seite (siehe
`wrappers/gdc/client.py` für dasselbe Prinzip beim ersten Wrapper).

STRUKTURELLER UNTERSCHIED ZU GDC/GEO/ENA: cBioPortal hat keinen einzelnen
generischen Such-Endpunkt (wie GDCs `/query` oder ENAs `/search`), sondern
ein REST-Ressourcen-pro-Endpunkt-Design (`/studies`, `/studies/{id}/
clinical-data`, `/molecular-profiles/{id}/molecular-data/fetch`, ...).
Deshalb hat dieser Wrapper bewusst KEINE generischen `query()`/`search()`-
Methoden wie die anderen Wrapper, sondern eine Methode je Ressourcentyp.
Das Schema ist außerdem studienspezifisch (klinische Attribute
unterscheiden sich je Studie) statt global wie bei GDC/GEO/ENA — `get_schema()`
braucht deshalb eine `study_id`.

Drei Ebenen statt der üblichen zwei Tiers, weil cBioPortal selbst schon
kuratierte (nicht rohe) Daten liefert:
  - `list_studies()`                                    – welche Studien gibt es
  - `get_schema()` (clinical-attributes)                  – welche klinischen Felder gibt es in einer Studie
  - `get_clinical_data()`                                 – klinische Werte pro Patient/Sample
  - `list_molecular_profiles()` / `list_sample_lists()` /
    `get_molecular_data()`                                – "Bulk"-Analogon: genomische
    Profildaten (Mutationen, Kopienzahl-Varianten, Expression) für eine
    Gen-/Sample-Auswahl. cBioPortal liefert selbst keine rohen
    Sequenzdateien (FASTQ/BAM) wie GDC/ENA — das ist bewusst außerhalb des
    Scopes dieses Wrappers.

ONTOLOGIE-/MAPPING-SCHICHT (spätere Ausbaustufe, analog zum GDC-Wrapper):
`get_schema()` liefert die klinischen Attribut-IDs einer Studie (z. B.
"AGE", "AJCC_PATHOLOGIC_TUMOR_STAGE"). Diese Liste ist die Grundlage, gegen
die künftige Feld-Mappings (cBioPortal-Feld -> internes
DataBridge-Schema/Ontologie-Begriff) definiert werden — pro Studie ggf.
mit Überschneidungen zu GDC-Feldern (z. B. Diagnose-Stadium), da beide
Quellen teils dieselben TCGA-Ursprungsdaten aufbereiten.
"""

from __future__ import annotations

from typing import Any, Optional

import requests

from .cache import WrapperCache

DEFAULT_BASE_URL = "https://www.cbioportal.org/api"
DEFAULT_TIMEOUT = 30


class CBioPortalWrapper:
    """Kapselt den Zugriff auf cBioPortal für den Mediator.

    Basis-URL laut cBioPortal-API-Dokumentation:
    https://www.cbioportal.org/api (konfigurierbar über den
    Konstruktor-Parameter `base_url` — analog zum GDC-Wrapper wäre eine
    Umgebungsvariable `CBIOPORTAL_API_BASE_URL` der nächste Schritt, sobald
    der Mediator diesen Wrapper anbindet, siehe README.md).
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        cache: Optional[WrapperCache] = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.cache = cache or WrapperCache()

    @staticmethod
    def _page_number(size: int, from_: int) -> int:
        """Übersetzt den offset-basierten `from_`/`size`-Stil der anderen
        Wrapper in cBioPortals seitenbasierte Pagination (`pageNumber`/
        `pageSize`).

        cBioPortal kennt keinen freien Offset — `from_` muss daher ein
        Vielfaches von `size` sein (sonst `ValueError`), analog zu einer
        Seitenzahl mal Seitengröße.
        """
        if size <= 0:
            raise ValueError("size muss positiv sein")
        if from_ % size != 0:
            raise ValueError(
                f"cBioPortal paginiert seitenbasiert (pageNumber/pageSize) statt über einen "
                f"freien Offset — from_={from_} muss ein Vielfaches von size={size} sein."
            )
        return from_ // size

    # ------------------------------------------------------------------
    # Metadaten-Tier: Studien
    # ------------------------------------------------------------------

    def list_studies(self, *, keyword: Optional[str] = None, size: int = 20, from_: int = 0) -> dict:
        """Listet Studien, optional gefiltert über ein Stichwort (serverseitig
        gefiltert, z. B. `keyword="breast"` -> nur Brustkrebs-Studien).

        Pagination über `pageSize`/`pageNumber` (hier als `size`/`from_`
        benannt, analog zu den anderen Wrappern — siehe `_page_number`).
        Die Query-Spezifikation selbst wird als Tier-1-Cache-Eintrag
        ("Recipe") abgelegt, wie im GDC-Wrapper.
        """
        recipe = {"keyword": keyword, "size": size, "from": from_}
        recipe_key = self.cache.recipes.key_for(recipe)
        self.cache.recipes.set(recipe_key, recipe)

        params: dict[str, Any] = {
            "pageSize": size,
            "pageNumber": self._page_number(size, from_),
            "projection": "SUMMARY",
        }
        if keyword:
            params["keyword"] = keyword

        response = self.session.get(f"{self.base_url}/studies", params=params, timeout=self.timeout)
        response.raise_for_status()
        studies = response.json()

        return {
            "source": "cbioportal",
            "recipe_key": recipe_key,
            # cBioPortal liefert wie ENA keine Gesamttrefferzahl im Response-
            # Body oder -Header — "has_more" ist eine Heuristik (Seite
            # komplett voll -> vermutlich weitere Treffer), kein Beweis.
            "pagination": {"size": size, "from": from_, "retrieved": len(studies), "has_more": len(studies) == size},
            "results": studies,
        }

    # ------------------------------------------------------------------
    # Metadaten-Tier: klinische Daten (studienspezifisch)
    # ------------------------------------------------------------------

    def get_schema(self, study_id: str) -> list[str]:
        """Ruft die klinischen Attribute einer Studie ab und liefert deren
        IDs (`clinicalAttributeId`) sortiert als Liste.

        Analog zu `GDCWrapper.get_schema()` (dort `_mapping`), aber
        studienspezifisch statt global — cBioPortal hat kein einheitliches
        Schema über alle Studien hinweg. Grundlage für die spätere
        Ontologie-/Mapping-Schicht (siehe Modul-Docstring).
        """
        response = self.session.get(
            f"{self.base_url}/studies/{study_id}/clinical-attributes", timeout=self.timeout
        )
        response.raise_for_status()
        attributes = response.json()
        return sorted(attr["clinicalAttributeId"] for attr in attributes if "clinicalAttributeId" in attr)

    def get_clinical_data(
        self,
        study_id: str,
        *,
        clinical_data_type: str = "PATIENT",
        size: int = 20,
        from_: int = 0,
    ) -> dict:
        """Liefert klinische Datenpunkte (Attribut/Wert je Patient oder
        Sample) einer Studie.

        `clinical_data_type`: "PATIENT" (Standard) oder "SAMPLE". Pagination
        wie bei `list_studies()`. Eine serverseitige Filterung nach
        bestimmten `clinicalAttributeId`s ist über diesen GET-Endpunkt nicht
        verifiziert (siehe README.md, "Noch offen") — cBioPortal bietet dafür
        einen separaten `POST .../clinical-data/fetch`-Endpunkt, der hier
        bewusst nicht implementiert ist, um nichts Ungetestetes zu committen.

        Die Query-Spezifikation selbst wird als Tier-1-Cache-Eintrag
        ("Recipe") abgelegt, wie im GDC-Wrapper.
        """
        recipe = {
            "study_id": study_id,
            "clinical_data_type": clinical_data_type,
            "size": size,
            "from": from_,
        }
        recipe_key = self.cache.recipes.key_for(recipe)
        self.cache.recipes.set(recipe_key, recipe)

        params = {
            "clinicalDataType": clinical_data_type,
            "pageSize": size,
            "pageNumber": self._page_number(size, from_),
            "projection": "SUMMARY",
        }
        response = self.session.get(
            f"{self.base_url}/studies/{study_id}/clinical-data", params=params, timeout=self.timeout
        )
        response.raise_for_status()
        data = response.json()

        return {
            "source": "cbioportal",
            "study_id": study_id,
            "recipe_key": recipe_key,
            "pagination": {"size": size, "from": from_, "retrieved": len(data), "has_more": len(data) == size},
            # cBioPortal-Originalfeldnamen unverändert (`clinicalAttributeId`,
            # `value`, ...) — Übersetzung ins interne Schema ist Aufgabe der
            # späteren Ontologie-/Mapping-Schicht, analog zum GDC-Wrapper.
            "results": data,
        }

    # ------------------------------------------------------------------
    # Bulk-Tier: genomische Profildaten
    # ------------------------------------------------------------------

    def list_molecular_profiles(self, study_id: str) -> list[dict]:
        """Listet die verfügbaren molekularen Profile einer Studie (z. B.
        Mutationen, Kopienzahl-Varianten, mRNA-Expression) — Vorbereitung für
        `get_molecular_data()`, das ein solches `molecularProfileId` braucht.
        """
        response = self.session.get(
            f"{self.base_url}/studies/{study_id}/molecular-profiles", timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()

    def list_sample_lists(self, study_id: str) -> list[dict]:
        """Listet die vordefinierten Sample-Listen einer Studie (z. B. "alle
        Samples", "Samples mit vollständigen Multi-Omics-Daten") —
        Vorbereitung für `get_molecular_data()`, das ein solches
        `sampleListId` braucht.
        """
        response = self.session.get(f"{self.base_url}/studies/{study_id}/sample-lists", timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def get_molecular_data(
        self,
        molecular_profile_id: str,
        *,
        sample_list_id: str,
        entrez_gene_ids: list[int],
        projection: str = "SUMMARY",
    ) -> dict:
        """Bulk-Tier-Äquivalent: liefert genomische Profildaten (z. B.
        Kopienzahl-Werte oder Expressions-Scores) für eine Gen-/Sample-Auswahl
        aus einem molekularen Profil.

        Anders als beim GDC-Wrapper (`download_via_gdc_client`, externes
        Tool für rohe Sequenzdateien) und beim GEO-/ENA-Wrapper (direkter
        Datei-Download) liefert cBioPortal hier bereits aufbereitete
        Werte (kein Rohdaten-Download) über einen einzelnen POST-Request
        (`POST /molecular-profiles/{id}/molecular-data/fetch`), live
        verifiziert.

        Die Query-Spezifikation selbst wird als Tier-1-Cache-Eintrag
        ("Recipe") abgelegt, wie im GDC-Wrapper.
        """
        recipe = {
            "molecular_profile_id": molecular_profile_id,
            "sample_list_id": sample_list_id,
            "entrez_gene_ids": sorted(entrez_gene_ids),
            "projection": projection,
        }
        recipe_key = self.cache.recipes.key_for(recipe)
        self.cache.recipes.set(recipe_key, recipe)

        response = self.session.post(
            f"{self.base_url}/molecular-profiles/{molecular_profile_id}/molecular-data/fetch",
            params={"projection": projection},
            json={"sampleListId": sample_list_id, "entrezGeneIds": entrez_gene_ids},
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()

        return {
            "source": "cbioportal",
            "molecular_profile_id": molecular_profile_id,
            "recipe_key": recipe_key,
            "results": data,
        }

    def to_anndata(self, raw_response: object) -> None:
        """Überführt eine cBioPortal-Antwort in das Zielformat anndata/.h5ad.

        Bewusst nicht Teil dieses Wrappers (siehe Modul-Docstring) — der
        Wrapper liefert strukturierte Metadaten-/Profildaten, die
        Transformation nach anndata ist ein separater Mediator-seitiger
        Schritt.
        """
        raise NotImplementedError(
            "Transformation nach anndata ist bewusst kein Teil des Wrappers, "
            "siehe Modul-Docstring."
        )
