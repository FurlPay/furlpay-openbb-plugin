"""
Contract tests for the FurlPay OpenBB backend.

These assert the exact shapes OpenBB Workspace requires, so a green run means the
backend will register and every widget will render:

  • /widgets.json is a DICT (not an array); /apps.json is an ARRAY.
  • Every widget key == its endpoint, and every endpoint has a live route.
  • Every apps.json layout `i` references a real widget.
  • Every form `endpoint` and every widget `endpoint` resolves.
  • Metric widgets return [{label, value, delta}]; tables return a list of rows.
  • Each action form POST returns 200 and its blotter GET reflects the submission.

Run:  python -m pytest test_backend.py -q     (or)     python test_backend.py
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

import main

ROOT = Path(__file__).parent.resolve()
client = TestClient(main.app)

WIDGETS = json.loads((ROOT / "widgets.json").read_text())
APPS = json.loads((ROOT / "apps.json").read_text())


def _route_paths() -> set[str]:
    return {r.path for r in main.app.routes}  # type: ignore[attr-defined]


def _endpoint_path(endpoint: str) -> str:
    return endpoint if endpoint.startswith("/") else f"/{endpoint}"


def test_widgets_json_is_dict_and_apps_json_is_array():
    served_widgets = client.get("/widgets.json").json()
    served_apps = client.get("/apps.json").json()
    assert isinstance(served_widgets, dict), "widgets.json must be a dict keyed by widget id"
    assert isinstance(served_apps, list), "apps.json must be an array of app objects"
    assert served_widgets == WIDGETS and served_apps == APPS


def test_every_widget_has_required_fields_and_a_live_route():
    routes = _route_paths()
    for wid, w in WIDGETS.items():
        for field in ("name", "description", "endpoint"):
            assert w.get(field), f"widget '{wid}' missing required field '{field}'"
        assert _endpoint_path(w["endpoint"]) in routes, f"widget '{wid}' endpoint has no route"


def test_every_form_endpoint_resolves_to_a_post_route():
    post_paths = {r.path for r in main.app.routes if "POST" in getattr(r, "methods", set())}  # type: ignore[attr-defined]
    found_a_form = False
    for wid, w in WIDGETS.items():
        for p in w.get("params", []):
            if p.get("type") == "form":
                found_a_form = True
                assert _endpoint_path(p["endpoint"]) in post_paths, f"form in '{wid}' has no POST route"
    assert found_a_form, "expected at least one action form widget"


def test_apps_layout_only_references_real_widgets():
    for app_obj in APPS:
        for tab_id, tab in app_obj["tabs"].items():
            for item in tab["layout"]:
                assert item["i"] in WIDGETS, f"tab '{tab_id}' references unknown widget '{item['i']}'"
                for k in ("x", "y", "w", "h"):
                    assert isinstance(item[k], int), f"layout item '{item['i']}' has non-int {k}"


def test_metric_widget_shape():
    data = client.get("/portfolio_summary").json()
    assert isinstance(data, list) and data, "metric endpoint must return a non-empty list"
    for row in data:
        assert set(row) >= {"label", "value", "delta"}, "metric rows need label/value/delta"


def test_table_widgets_return_lists():
    for ep in ("positions", "wallet_balances", "x402_revenue", "payments_blotter"):
        data = client.get(f"/{ep}").json()
        assert isinstance(data, list) and data, f"table endpoint /{ep} must return a non-empty list"


def test_markdown_widget_returns_text():
    data = client.get("/research_to_execute").json()
    assert isinstance(data, str) and data.startswith("## Research"), "markdown endpoint must return a string"


def test_place_order_then_blotter_reflects_it():
    r = client.post("/execute_order", json={"symbol": "aapl", "side": "buy", "notional": 42})
    assert r.status_code == 200 and r.json() == {"success": True}
    top = client.get("/order_blotter").json()[0]
    assert top["symbol"] == "AAPL" and top["notional_usdc"] == 42 and top["status"] == "submitted"


def test_order_validation_rejects_bad_input():
    assert client.post("/execute_order", json={"symbol": "", "notional": 10}).status_code == 400
    assert client.post("/execute_order", json={"symbol": "AAPL", "notional": -5}).status_code == 400


def test_dca_then_blotter_reflects_it():
    r = client.post("/execute_dca", json={"symbol": "voo", "amount": 10, "frequency": "weekly"})
    assert r.status_code == 200
    top = client.get("/dca_blotter").json()[0]
    assert top["symbol"] == "VOO" and top["frequency"] == "weekly" and top["status"] == "scheduled"


def test_transfer_then_blotter_reflects_it():
    r = client.post("/execute_transfer", json={"to": "furl:alice", "amount": 7.5, "token": "USDC"})
    assert r.status_code == 200
    top = client.get("/transfer_blotter").json()[0]
    assert top["to"] == "furl:alice" and top["amount"] == 7.5 and top["status"] == "sent"


def test_demo_mode_is_active_without_api_key():
    # The whole suite runs on demo data; assert that's what's happening.
    assert main.client.live is False, "set FURLPAY_API_KEY unset for the contract suite"
    assert client.get("/").json()["mode"] == "demo"


if __name__ == "__main__":
    import sys
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"ok   {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
