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

from gdc import GDCWrapper, build_filters
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
# GDCWrapper.get_schema
# ---------------------------------------------------------------------

def test_get_schema_returns_sorted_field_names(wrapper):
    wrapper.session = FakeSession(FakeResponse({"fields": ["submitter_id", "case_id", "demographic.race"]}))

    fields = wrapper.get_schema("cases")

    assert fields == ["case_id", "demographic.race", "submitter_id"]


def test_get_schema_unknown_endpoint_raises_valueerror(wrapper):
    with pytest.raises(ValueError):
        wrapper.get_schema("not_an_endpoint")
