"""API tests. Reuse the CLI fixture profiles and assert the web layer
produces the same verdicts as the engine, plus error handling."""
from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from benefit_finder.core import screen_household  # noqa: E402
from benefit_finder.web.app import app  # noqa: E402


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def test_meta_endpoint(client) -> None:
    r = client.get("/api/meta")
    assert r.status_code == 200
    body = r.json()
    assert "disclaimer" in body
    assert body["fpl_year"] >= 2025
    flag_names = {f["name"] for f in body["flags"]}
    assert "receives_snap" in flag_names
    assert {"value", "label"} <= set(body["relationships"][0])


def test_index_served(client) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "Benefit Finder" in r.text
    assert "/static/js/app.js" in r.text


def test_static_assets_served(client) -> None:
    for path in ("/static/css/styles.css", "/static/js/app.js", "/static/js/markdown.js"):
        assert client.get(path).status_code == 200, path


def test_screen_matches_engine_verdicts(client, ks_family5) -> None:
    """The API must return the exact verdicts the engine produces."""
    engine_evals = screen_household(ks_family5)
    expected = {ev.rule.id: ev.verdict.value for ev in engine_evals}

    r = client.post("/api/screen", json=ks_family5.to_dict())
    assert r.status_code == 200
    body = r.json()
    got = {ev["id"]: ev["verdict"] for ev in body["evaluations"]}
    assert got == expected


def test_screen_sorted_by_value_desc(client, ks_family5) -> None:
    r = client.post("/api/screen", json=ks_family5.to_dict())
    values = [
        (ev["estimated_value"]["high"] if ev["estimated_value"] else 0.0)
        for ev in r.json()["evaluations"]
    ]
    assert values == sorted(values, reverse=True)


def test_screen_payload_shape(client, ks_family5) -> None:
    body = client.post("/api/screen", json=ks_family5.to_dict()).json()
    assert body["total_high"] > 0
    ev = next(e for e in body["evaluations"] if e["id"] == "eitc")
    # required fields from the spec
    for key in ("program", "verdict", "reasons", "estimated_value",
                "application_url", "documents", "source_url", "last_verified"):
        assert key in ev
    assert ev["estimated_value"]["high"] == pytest.approx(4_986, abs=1)


def test_screen_reports_income_percent_of_fpl(client, ks_family5) -> None:
    body = client.post("/api/screen", json=ks_family5.to_dict()).json()
    # family of 5 at $45k, 2025 FPL for 5 is $37,650 -> ~119.5%
    assert body["income_percent_of_fpl"] == pytest.approx(119.5, abs=1.0)


def test_income_drives_eligibility(client, ks_family5) -> None:
    """Changing only income flips verdicts, which is what the live income
    control on the dashboard relies on."""
    base = ks_family5.to_dict()

    low = dict(base, agi=20_000)
    high = dict(base, agi=220_000)

    def verdicts(payload):
        body = client.post("/api/screen", json=payload).json()
        return {ev["id"]: ev["verdict"] for ev in body["evaluations"]}

    low_v = verdicts(low)
    high_v = verdicts(high)

    # SNAP is reachable at low income, not at a high income
    assert low_v["snap"] in ("likely", "yes")
    assert high_v["snap"] == "no"
    # the total value should shrink as income rises
    low_total = client.post("/api/screen", json=low).json()["total_high"]
    high_total = client.post("/api/screen", json=high).json()["total_high"]
    assert low_total > high_total
    # and the reported FPL percentage tracks income
    assert (
        client.post("/api/screen", json=high).json()["income_percent_of_fpl"]
        > client.post("/api/screen", json=low).json()["income_percent_of_fpl"]
    )


def test_screen_special_situations_present(client, ks_family5) -> None:
    body = client.post("/api/screen", json=ks_family5.to_dict()).json()
    titles = [s["title"] for s in body["special_situations"]]
    assert any("dropped" in t for t in titles)  # 62k -> 45k is a 27% drop


def test_screen_surfaces_snap_size_nuance(client, family_with_college_away) -> None:
    body = client.post("/api/screen", json=family_with_college_away.to_dict()).json()
    snap = next(e for e in body["evaluations"] if e["id"] == "snap")
    assert snap["household_size_used"] == 3
    assert snap["size_basis_explanation"]
    assert "SNAP" in snap["size_basis_explanation"]


def test_screen_single_adult(client, single_adult) -> None:
    r = client.post("/api/screen", json=single_adult.to_dict())
    assert r.status_code == 200
    assert r.json()["household_size"] == 1


def test_screen_rejects_unknown_flag(client, ks_family5) -> None:
    data = ks_family5.to_dict()
    data["flags"]["wins_lottery"] = True
    r = client.post("/api/screen", json=data)
    assert r.status_code == 422
    assert "wins_lottery" in json.dumps(r.json())


def test_screen_rejects_bad_enum(client, ks_family5) -> None:
    data = ks_family5.to_dict()
    data["members"][0]["student"] = "kindergarten"
    r = client.post("/api/screen", json=data)
    assert r.status_code == 422


def test_screen_rejects_non_numeric_age(client, ks_family5) -> None:
    data = ks_family5.to_dict()
    data["members"][0]["age"] = "old"
    r = client.post("/api/screen", json=data)
    assert r.status_code == 422


def test_screen_rejects_unknown_top_level_key(client, ks_family5) -> None:
    data = ks_family5.to_dict()
    data["surprise"] = 1
    r = client.post("/api/screen", json=data)
    assert r.status_code == 422


def test_post_report_markdown(client, ks_family5) -> None:
    r = client.post("/api/report", json=ks_family5.to_dict())
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    assert "## Summary" in r.text
    assert "Income dropped 27%" in r.text
    assert "- [ ]" in r.text


def test_get_report_query_param(client, ks_family5) -> None:
    profile = json.dumps(ks_family5.to_dict())
    r = client.get("/api/report", params={"profile": profile})
    assert r.status_code == 200
    assert "# Benefit Finder Report" in r.text


def test_get_report_bad_json(client) -> None:
    r = client.get("/api/report", params={"profile": "{not json"})
    assert r.status_code == 400


def test_get_report_invalid_profile(client) -> None:
    r = client.get("/api/report", params={"profile": json.dumps({"members": []})})
    # missing required state -> pydantic validation error
    assert r.status_code == 422


def test_zip_alias_accepted(client, ks_family5) -> None:
    data = ks_family5.to_dict()
    data["zip"] = data.pop("zip_code")
    r = client.post("/api/screen", json=data)
    assert r.status_code == 200
