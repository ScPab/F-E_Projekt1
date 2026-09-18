"""Aufgabe 17 — Abnahme des Mediator-Clients: ohne Qt, ohne Netz.

``requests`` ist gemockt, es geht kein Byte nach draussen. Getestet wird genau
das, was die Oberflaeche an den Mediator schickt und wie sie Fehler behandelt —
die Fenster-Schicht braucht es dafuer nicht, weil ``mediator_client`` bewusst
Qt-frei ist.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mediator_client as mc  # noqa: E402


class FakeResponse:
    """Minimales ``requests.Response``-Double."""

    def __init__(self, status_code: int = 200, payload=None, text: str = "") -> None:
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("kein JSON")
        return self._payload


def _level(**overrides):
    level = {
        "recipe_key": "abc123",
        "status": "ok",
        "requested_fields": ["case_id", "demographic.gender"],
        "failed_cohorts": [],
        "triple_count": 302,
        "turtle": "@prefix db: <x> .\n",
        "anndata": None,
        "error": None,
    }
    level.update(overrides)
    return {"levels": [level]}


# --------------------------------------------------------------------------
# build_selection_request
# --------------------------------------------------------------------------
def test_build_request_has_exactly_one_level_with_the_right_field_names() -> None:
    payload = mc.build_selection_request(
        cohort="TCGA-BRCA",
        modality="gene_expression",
        attributes=["gender", "primary_diagnosis"],
        source="gdc",
        size=20,
    )
    # Feldnamen gegen die OpenAPI des Mediators (SelectionRequest/SingleSelection).
    assert set(payload) == {"levels", "size"}
    assert len(payload["levels"]) == 1
    level = payload["levels"][0]
    assert set(level) == {"source", "cohorts", "modality", "attributes"}
    assert level["cohorts"] == ["TCGA-BRCA"]
    assert level["source"] == "gdc"
    assert level["modality"] == "gene_expression"
    assert level["attributes"] == ["gender", "primary_diagnosis"]
    assert payload["size"] == 20


def test_build_request_takes_the_checked_attributes_in_order() -> None:
    payload = mc.build_selection_request(
        cohort="TCGA-KIRC", modality="gene_expression",
        attributes=["tumor_stage", "gender", "sample_type"], source="gdc", size=5,
    )
    assert payload["levels"][0]["attributes"] == ["tumor_stage", "gender", "sample_type"]


def test_build_request_accepts_no_attributes() -> None:
    payload = mc.build_selection_request(
        cohort="TCGA-BRCA", modality="gene_expression",
        attributes=[], source="gdc", size=20,
    )
    assert payload["levels"][0]["attributes"] == []


@pytest.mark.parametrize("given, expected", [(0, 1), (1, 1), (20, 20), (200, 200), (5000, 200)])
def test_build_request_clamps_size_to_the_openapi_limits(given, expected) -> None:
    payload = mc.build_selection_request(
        cohort="TCGA-BRCA", modality="gene_expression",
        attributes=[], source="gdc", size=given,
    )
    assert payload["size"] == expected


# --------------------------------------------------------------------------
# preview / generate treffen die richtigen Pfade
# --------------------------------------------------------------------------
def test_preview_posts_to_selection_preview() -> None:
    with patch.object(mc.requests, "post", return_value=FakeResponse(payload=_level())) as post:
        result = mc.preview({"levels": []}, base_url="http://testhost:9000")
    assert post.call_args.args[0] == "http://testhost:9000/selection/preview"
    assert result.ok and result.status_code == 200
    assert result.first_level()["recipe_key"] == "abc123"


def test_generate_posts_to_selection_generate() -> None:
    with patch.object(mc.requests, "post", return_value=FakeResponse(payload=_level())) as post:
        result = mc.generate({"levels": []}, base_url="http://testhost:9000")
    assert post.call_args.args[0] == "http://testhost:9000/selection/generate"
    assert result.ok


def test_timeouts_differ_between_preview_and_generate() -> None:
    # Generieren laedt Rohdaten herunter und dauert Minuten — ein gemeinsames
    # Zeitlimit waere entweder zu knapp oder zu lasch.
    assert mc.PREVIEW_TIMEOUT < mc.GENERATE_TIMEOUT
    with patch.object(mc.requests, "post", return_value=FakeResponse(payload=_level())) as post:
        mc.preview({}, base_url="http://h")
        assert post.call_args.kwargs["timeout"] == mc.PREVIEW_TIMEOUT
        mc.generate({}, base_url="http://h")
        assert post.call_args.kwargs["timeout"] == mc.GENERATE_TIMEOUT


def test_base_url_comes_from_the_environment(monkeypatch) -> None:
    monkeypatch.delenv("MEDIATOR_URL", raising=False)
    assert mc.default_base_url() == "http://localhost:8000"
    monkeypatch.setenv("MEDIATOR_URL", "http://anderswo:8123/")
    assert mc.default_base_url() == "http://anderswo:8123"
    with patch.object(mc.requests, "post", return_value=FakeResponse(payload=_level())) as post:
        mc.preview({})
    assert post.call_args.args[0] == "http://anderswo:8123/selection/preview"


# --------------------------------------------------------------------------
# Fehler werden zurueckgegeben, nicht geworfen
# --------------------------------------------------------------------------
def test_connection_error_becomes_a_result_not_an_exception() -> None:
    with patch.object(mc.requests, "post", side_effect=requests.ConnectionError("refused")):
        result = mc.preview({}, base_url="http://localhost:8000")
    assert result.ok is False
    assert result.error and "nicht erreichbar" in result.error
    assert result.status_code is None


def test_timeout_becomes_a_result_not_an_exception() -> None:
    with patch.object(mc.requests, "post", side_effect=requests.Timeout()):
        result = mc.generate({}, base_url="http://localhost:8000")
    assert result.ok is False
    assert "Zeitüberschreitung" in result.error


def test_http_error_keeps_status_and_detail() -> None:
    body = {"detail": "Keine Treffer für Kohorte(n) ['TCGA-XXXX']."}
    with patch.object(mc.requests, "post", return_value=FakeResponse(422, payload=body)):
        result = mc.preview({}, base_url="http://localhost:8000")
    assert result.ok is False
    assert result.status_code == 422
    assert "422" in result.error and "TCGA-XXXX" in result.error


def test_non_json_answer_is_reported() -> None:
    with patch.object(mc.requests, "post", return_value=FakeResponse(200, payload=None, text="<html>")):
        result = mc.preview({}, base_url="http://localhost:8000")
    assert result.ok is False
    assert "JSON" in result.error


# --------------------------------------------------------------------------
# Result
# --------------------------------------------------------------------------
def test_first_level_is_empty_without_levels() -> None:
    assert mc.Result(ok=True, data={"levels": []}).first_level() == {}
    assert mc.Result(ok=True, data={}).first_level() == {}


def test_failed_level_is_still_an_ok_request() -> None:
    """Eine fehlgeschlagene Ebene ist keine fehlgeschlagene Anfrage — sonst
    ginge die Fehlermeldung des Mediators verloren."""
    payload = _level(status="error", error="Keine Treffer.", turtle=None, triple_count=None)
    with patch.object(mc.requests, "post", return_value=FakeResponse(payload=payload)):
        result = mc.preview({}, base_url="http://h")
    assert result.ok is True
    assert result.first_level()["status"] == "error"
    assert result.first_level()["error"] == "Keine Treffer."
