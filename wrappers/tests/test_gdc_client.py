"""Unit-Tests für den GDC-Wrapper (`gdc.client`).

Kein Netzwerkzugriff — `GDCWrapper.session` wird durch ein Fake ersetzt
(anders als `wrappers/gdc/scripts/check_connection.py`, das bewusst live
gegen die echte GDC-API testet, siehe dortiger Modul-Docstring). Deckt die
Bausteine ab, die Teil 1a des Hand-offs
(`wissensnetz/prototype/mp_lite/HANDOFF.md`) betreffen: `build_filters`
sowie `query`/`search`/`get_schema` müssen beliebige GDC-Feldnamen
unverändert durchreichen.
"""

from __future__ import annotations

import pytest
import requests

from gdc import GDCWrapper, build_expression_filters, build_filters, extract_sample_case_rows
from gdc.cache import WrapperCache


class FakeResponse:
    """Minimales Double für `requests.Response` (nur die genutzten Methoden)."""

    def __init__(self, payload: dict | None = None, status_code: int = 200, text: str = ""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")

    def json(self) -> dict:
        return self._payload


class FakeSession:
    """Zeichnet den letzten GET-Aufruf auf und liefert eine vorbereitete Antwort."""

    def __init__(self, response: FakeResponse):
        self._response = response
        self.last_call: dict | None = None

    def get(self, url: str, params: dict | None = None, timeout: int | None = None):
        self.last_call = {"url": url, "params": params, "timeout": timeout}
        return self._response


@pytest.fixture
def wrapper(tmp_path) -> GDCWrapper:
    return GDCWrapper("https://api.gdc.cancer.gov", cache=WrapperCache(str(tmp_path)))


# ---------------------------------------------------------------------
# build_filters
# ---------------------------------------------------------------------

def test_build_filters_no_criteria_returns_none():
    assert build_filters(access=None) is None


def test_build_filters_single_project_id_as_string():
    filters = build_filters(project_id="TCGA-BRCA", access=None)
    assert filters == {
        "op": "in",
        "content": {"field": "cases.project.project_id", "value": ["TCGA-BRCA"]},
    }


def test_build_filters_project_id_as_list():
    filters = build_filters(project_id=["TCGA-BRCA", "TCGA-LUAD"], access=None)
    assert filters["content"]["value"] == ["TCGA-BRCA", "TCGA-LUAD"]


def test_build_filters_default_access_open():
    filters = build_filters()
    assert filters == {
        "op": "in",
        "content": {"field": "files.access", "value": ["open"]},
    }


def test_build_filters_combines_multiple_conditions_with_and():
    filters = build_filters(project_id="TCGA-BRCA", experimental_strategy="RNA-Seq", access="open")
    assert filters["op"] == "and"
    fields = {c["content"]["field"] for c in filters["content"]}
    assert fields == {"cases.project.project_id", "files.experimental_strategy", "files.access"}


def test_build_filters_extra_fragment_is_appended():
    extra_fragment = {"op": "=", "content": {"field": "cases.demographic.gender", "value": "female"}}
    filters = build_filters(access=None, extra=[extra_fragment])
    assert filters == extra_fragment


# ---------------------------------------------------------------------
# GDCWrapper.query
# ---------------------------------------------------------------------

def test_query_unknown_endpoint_raises_valueerror(wrapper):
    with pytest.raises(ValueError):
        wrapper.query("unknown_endpoint")


def test_query_passes_fields_through_unchanged(wrapper):
    """Kernaussage für HANDOFF Teil 1a: beliebige GDC-Feldnamen werden 1:1 durchgereicht."""
    fields = [
        "demographic.race",
        "demographic.ethnicity",
        "demographic.vital_status",
        "diagnoses.morphology",
        "diagnoses.site_of_resection_or_biopsy",
        "diagnoses.ajcc_pathologic_stage",
        "diagnoses.metastasis_at_diagnosis",
    ]
    fake_session = FakeSession(FakeResponse({"data": {"hits": [], "pagination": {"total": 0}}}))
    wrapper.session = fake_session

    wrapper.query("cases", fields=fields, size=5, from_=10, sort="submitter_id:asc")

    assert fake_session.last_call["url"] == "https://api.gdc.cancer.gov/cases"
    params = fake_session.last_call["params"]
    assert params["fields"] == ",".join(fields)
    assert params["size"] == 5
    assert params["from"] == 10
    assert params["sort"] == "submitter_id:asc"


def test_query_normalizes_response_shape(wrapper):
    payload = {
        "data": {
            "hits": [{"case_id": "abc", "submitter_id": "TCGA-XX-0001"}],
            "pagination": {"total": 1, "count": 1},
        }
    }
    wrapper.session = FakeSession(FakeResponse(payload))

    result = wrapper.query("cases", size=1)

    assert result["source"] == "gdc"
    assert result["endpoint"] == "cases"
    assert result["results"] == payload["data"]["hits"]
    assert result["pagination"] == payload["data"]["pagination"]
    assert "recipe_key" in result


def test_query_caches_recipe(wrapper):
    wrapper.session = FakeSession(FakeResponse({"data": {"hits": [], "pagination": {}}}))

    result = wrapper.query("cases", fields=["case_id"], size=1)

    cached = wrapper.cache.recipes.get(result["recipe_key"])
    assert cached == {
        "endpoint": "cases",
        "filters": None,
        "fields": ["case_id"],
        "size": 1,
        "from": 0,
        "sort": None,
    }


def test_query_propagates_http_error(wrapper):
    wrapper.session = FakeSession(FakeResponse(status_code=500))
    with pytest.raises(requests.HTTPError):
        wrapper.query("cases")


# ---------------------------------------------------------------------
# GDCWrapper.search (Komfort-Wrapper um query)
# ---------------------------------------------------------------------

def test_search_builds_filters_and_delegates_to_query(wrapper):
    fake_session = FakeSession(FakeResponse({"data": {"hits": [], "pagination": {}}}))
    wrapper.session = fake_session

    wrapper.search(
        "cases",
        project_id="TCGA-BRCA",
        fields=["demographic.race"],
        access=None,
        size=1,
    )

    import json

    params = fake_session.last_call["params"]
    assert json.loads(params["filters"]) == {
        "op": "in",
        "content": {"field": "cases.project.project_id", "value": ["TCGA-BRCA"]},
    }
    assert params["fields"] == "demographic.race"


# ---------------------------------------------------------------------
# Expressionsdaten (HANDOFF Teil 3/3a, wissensnetz/HANDOFF_anndata.md)
# ---------------------------------------------------------------------

def test_build_expression_filters_rna_seq():
    filters = build_expression_filters(assay="rna_seq", project_id="TCGA-BRCA")
    fields = {c["content"]["field"]: c["content"]["value"] for c in filters["content"]}
    assert fields["files.data_type"] == ["Gene Expression Quantification"]
    assert fields["files.experimental_strategy"] == ["RNA-Seq"]
    assert fields["cases.project.project_id"] == ["TCGA-BRCA"]
    assert fields["files.access"] == ["open"]


def test_build_expression_filters_mirna_seq():
    filters = build_expression_filters(assay="mirna_seq", access=None)
    fields = {c["content"]["field"]: c["content"]["value"] for c in filters["content"]}
    assert fields["files.data_type"] == ["miRNA Expression Quantification"]
    assert fields["files.experimental_strategy"] == ["miRNA-Seq"]


def test_build_expression_filters_unknown_assay_raises_valueerror():
    with pytest.raises(ValueError):
        build_expression_filters(assay="not_an_assay")


def test_extract_sample_case_rows_flattens_cases_and_samples():
    hits = [
        {
            "file_id": "file-1",
            "file_name": "sample-a.rna_seq.gene_counts.tsv",
            "cases": [
                {
                    "submitter_id": "TCGA-XX-0001",
                    "samples": [{"sample_id": "s-0001-01", "sample_type": "Primary Tumor"}],
                }
            ],
        },
        {"file_id": "file-2", "file_name": "no-case.tsv", "cases": []},
    ]

    rows = extract_sample_case_rows(hits)

    assert rows == [
        {
            "file_id": "file-1",
            "file_name": "sample-a.rna_seq.gene_counts.tsv",
            "submitter_id": "TCGA-XX-0001",
            "sample_id": "s-0001-01",
            "sample_type": "Primary Tumor",
        }
    ]


def test_search_expression_files_merges_default_fields(wrapper):
    fake_session = FakeSession(FakeResponse({"data": {"hits": [], "pagination": {}}}))
    wrapper.session = fake_session

    wrapper.search_expression_files(assay="rna_seq", project_id="TCGA-BRCA", fields=["md5sum"])

    params = fake_session.last_call["params"]
    requested_fields = params["fields"].split(",")
    assert "md5sum" in requested_fields
    assert "file_id" in requested_fields
    assert "cases.samples.sample_id" in requested_fields


def test_download_expression_files_maps_samples_to_local_paths(wrapper, tmp_path, monkeypatch):
    hits = [
        {
            "file_id": "file-1",
            "file_name": "s-0001-01.rna_seq.gene_counts.tsv",
            "cases": [
                {
                    "submitter_id": "TCGA-XX-0001",
                    "samples": [{"sample_id": "s-0001-01", "sample_type": "Primary Tumor"}],
                }
            ],
        }
    ]

    query_response = FakeResponse({"data": {"hits": hits, "pagination": {"total": 1}}})
    manifest_response = FakeResponse(text="id\tfilename\nfile-1\ts-0001-01.rna_seq.gene_counts.tsv\n")

    class RoutingSession:
        """Liefert je nach Endpunkt eine andere vorbereitete Antwort."""

        def get(self, url, params=None, timeout=None):
            return manifest_response if params.get("return_type") == "manifest" else query_response

    wrapper.session = RoutingSession()

    output_dir = tmp_path / "downloads"

    def fake_run(command, capture_output, text, check):
        # Simuliert das gdc-client-Ablagemuster <output_dir>/<file_id>/<file_name>.
        file_dir = output_dir / "file-1"
        file_dir.mkdir(parents=True, exist_ok=True)
        (file_dir / "s-0001-01.rna_seq.gene_counts.tsv").write_text("gene_id\tvalue\n", encoding="utf-8")

        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return Result()

    monkeypatch.setattr("gdc.client.subprocess.run", fake_run)

    result = wrapper.download_expression_files(
        assay="rna_seq", project_id="TCGA-XX", output_dir=str(output_dir)
    )

    assert result["download"]["status"] == "completed"
    assert result["sample_case_map"] == {"s-0001-01": "TCGA-XX-0001"}
    assert result["sample_types"] == {"s-0001-01": "Primary Tumor"}
    assert result["sample_files"] == {"s-0001-01": output_dir / "file-1" / "s-0001-01.rna_seq.gene_counts.tsv"}
    assert result["quantification_columns"] == {
        "id_column": "gene_id",
        "value_column": "tpm_unstranded",
        "label_column": "gene_name",
    }


def test_download_expression_files_gdc_client_not_installed(wrapper, tmp_path, monkeypatch):
    """`gdc-client` fehlt -> `sample_files` bleibt leer statt eines Absturzes."""
    hits = [
        {
            "file_id": "file-1",
            "file_name": "s-0001-01.rna_seq.gene_counts.tsv",
            "cases": [{"submitter_id": "TCGA-XX-0001", "samples": [{"sample_id": "s-0001-01"}]}],
        }
    ]
    query_response = FakeResponse({"data": {"hits": hits, "pagination": {"total": 1}}})
    manifest_response = FakeResponse(text="id\tfilename\nfile-1\ts-0001-01.rna_seq.gene_counts.tsv\n")

    class RoutingSession:
        def get(self, url, params=None, timeout=None):
            return manifest_response if params.get("return_type") == "manifest" else query_response

    wrapper.session = RoutingSession()

    def fake_run(*args, **kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr("gdc.client.subprocess.run", fake_run)

    result = wrapper.download_expression_files(
        assay="rna_seq", project_id="TCGA-XX", output_dir=str(tmp_path / "downloads")
    )

    assert result["download"]["status"] == "not_run"
    assert result["sample_case_map"] == {"s-0001-01": "TCGA-XX-0001"}
    assert result["sample_files"] == {}


# ---------------------------------------------------------------------
# GDCWrapper.get_schema
# ---------------------------------------------------------------------

def test_get_schema_returns_sorted_field_names(wrapper):
    wrapper.session = FakeSession(FakeResponse({"fields": ["submitter_id", "case_id", "demographic.race"]}))

    fields = wrapper.get_schema("cases")

    assert fields == ["case_id", "demographic.race", "submitter_id"]


def test_get_schema_unknown_endpoint_raises_valueerror(wrapper):
    with pytest.raises(ValueError):
        wrapper.get_schema("not_an_endpoint")
