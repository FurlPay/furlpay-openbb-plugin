"""
FurlPay — OpenBB Workspace backend.

OpenBB Workspace is data-only: analysts can research an asset but cannot act on
it. This backend adds the missing execution layer. It registers as a custom
OpenBB backend (serves /widgets.json + /apps.json) and exposes two kinds of
widgets:

  • Data widgets  — portfolio, positions, stablecoin balances, x402 paywall
                    revenue, recent payments (GET endpoints, rendered as
                    tables / metrics).
  • Action widgets — place a fractional order, schedule a USDC dollar-cost-
                    average, or send stablecoins, each as an OpenBB input form
                    that POSTs to FurlPay and refreshes a blotter table.

Together with any OpenBB data app this closes the research → execute loop:
screen in OpenBB, then buy/settle/pay here, funded and settled in stablecoins.

Run:  uvicorn main:app --reload --port 7777
Then add http://localhost:7777 as a custom backend in OpenBB Workspace.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from furlpay_client import FurlPayClient

ROOT = Path(__file__).parent.resolve()
client = FurlPayClient.from_env()

app = FastAPI(
    title="FurlPay for OpenBB",
    description="Execution layer for OpenBB Workspace — trade, DCA, and pay in stablecoins.",
    version="0.1.0",
)

# OpenBB Workspace calls the backend from the browser; only its origin is allowed.
# Add localhost so the OpenBB desktop/self-hosted build can reach a local backend.
ORIGINS = [
    "https://pro.openbb.co",
    "https://excel.openbb.co",
    "http://localhost:1420",
    "http://localhost:5050",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -- OpenBB discovery endpoints --------------------------------------------

@app.get("/")
def root() -> dict:
    return {
        "name": "FurlPay for OpenBB",
        "mode": "live" if client.live else "demo",
        "docs": "https://furlpay.com/docs",
    }


@app.get("/widgets.json")
def widgets() -> JSONResponse:
    return JSONResponse(content=json.loads((ROOT / "widgets.json").read_text()))


@app.get("/apps.json")
def apps() -> JSONResponse:
    return JSONResponse(content=json.loads((ROOT / "apps.json").read_text()))


# -- data widgets -----------------------------------------------------------

@app.get("/portfolio_summary")
def portfolio_summary() -> JSONResponse:
    """Metric widget: headline portfolio KPIs. Shape: [{label, value, delta}]."""
    p = client.portfolio()
    data = [
        {"label": "Total Value", "value": _usd(p["total_value"]), "delta": _num(p.get("unrealized_pl_pct"))},
        {"label": "Invested", "value": _usd(p["invested"]), "delta": ""},
        {"label": "Cash (USDC)", "value": _usd(p["cash"]), "delta": ""},
        {"label": "Unrealized P&L", "value": _usd(p["unrealized_pl"]), "delta": _num(p.get("unrealized_pl_pct"))},
        {"label": "Positions", "value": str(p.get("positions_count", "-")), "delta": ""},
    ]
    return JSONResponse(content=data)


@app.get("/positions")
def positions() -> list[dict]:
    """Table widget: open positions with unrealized P&L."""
    return client.positions()


@app.get("/wallet_balances")
def wallet_balances() -> list[dict]:
    """Table widget: stablecoin + token balances across chains."""
    return client.balances()


@app.get("/x402_revenue")
def x402_revenue() -> list[dict]:
    """Table widget: per-resource x402 paywall calls + USDC revenue."""
    return client.paywalls()


@app.get("/payments_blotter")
def payments_blotter() -> list[dict]:
    """Table widget: most recent payments."""
    return client.payments()


@app.get("/research_to_execute")
def research_to_execute() -> str:
    """Markdown widget: explains how to pair OpenBB data with FurlPay execution."""
    mode = "**LIVE**" if client.live else "**DEMO** (set `FURLPAY_API_KEY` to go live)"
    return (
        "## Research → Execute\n\n"
        f"Mode: {mode}\n\n"
        "OpenBB gives you the data. FurlPay moves the money. This app closes the loop:\n\n"
        "1. **Screen** an asset with any OpenBB data widget.\n"
        "2. **Trade** it with the *Place Order* form — fractional, funded in USDC.\n"
        "3. **Automate** it with *Auto-Invest (DCA)* — recurring buys in stablecoins.\n"
        "4. **Settle & pay** agent/API usage via the x402 paywall revenue widget.\n\n"
        "All execution is fractional and stablecoin-funded, so a $1 order works the "
        "same as a $10,000 one — no bank rails, 24/7."
    )


# -- action widgets (execution — POST, then the blotter GET refreshes) ------

# In-memory blotters make the demo self-contained; live mode still records here so
# the widget can echo what it just submitted before the next API poll.
_ORDER_BLOTTER: list[dict] = []
_DCA_BLOTTER: list[dict] = []
_TRANSFER_BLOTTER: list[dict] = []


@app.post("/execute_order")
async def execute_order(params: dict) -> JSONResponse:
    symbol = (params.get("symbol") or "").strip()
    side = (params.get("side") or "buy").strip()
    notional = _to_float(params.get("notional"))
    if not symbol:
        return JSONResponse(status_code=400, content={"error": "Symbol is required"})
    if notional is None or notional <= 0:
        return JSONResponse(status_code=400, content={"error": "Notional must be a positive number"})

    resp = client.place_order(symbol, side, notional)
    _ORDER_BLOTTER.insert(0, {
        "symbol": symbol.upper(),
        "side": side.lower(),
        "notional_usdc": notional,
        "status": "submitted" if resp.get("success", True) else "error",
        "order_id": resp.get("id", resp.get("kind", "simulated")),
        "mode": "live" if client.live else "demo",
    })
    return JSONResponse(content={"success": True})


@app.get("/order_blotter")
def order_blotter() -> list[dict]:
    return _ORDER_BLOTTER or [_EMPTY_ORDER]


@app.post("/execute_dca")
async def execute_dca(params: dict) -> JSONResponse:
    symbol = (params.get("symbol") or "").strip()
    amount = _to_float(params.get("amount"))
    frequency = (params.get("frequency") or "weekly").strip()
    if not symbol:
        return JSONResponse(status_code=400, content={"error": "Symbol is required"})
    if amount is None or amount <= 0:
        return JSONResponse(status_code=400, content={"error": "Amount must be a positive number"})

    resp = client.create_auto_invest(symbol, amount, frequency)
    _DCA_BLOTTER.insert(0, {
        "symbol": symbol.upper(),
        "amount_usdc": amount,
        "frequency": frequency,
        "status": "scheduled" if resp.get("success", True) else "error",
        "schedule_id": resp.get("id", resp.get("kind", "simulated")),
        "mode": "live" if client.live else "demo",
    })
    return JSONResponse(content={"success": True})


@app.get("/dca_blotter")
def dca_blotter() -> list[dict]:
    return _DCA_BLOTTER or [_EMPTY_DCA]


@app.post("/execute_transfer")
async def execute_transfer(params: dict) -> JSONResponse:
    to = (params.get("to") or "").strip()
    amount = _to_float(params.get("amount"))
    token = (params.get("token") or "USDC").strip()
    if not to:
        return JSONResponse(status_code=400, content={"error": "Recipient is required"})
    if amount is None or amount <= 0:
        return JSONResponse(status_code=400, content={"error": "Amount must be a positive number"})

    resp = client.send_transfer(to, amount, token)
    _TRANSFER_BLOTTER.insert(0, {
        "to": to,
        "amount": amount,
        "token": token,
        "status": "sent" if resp.get("success", True) else "error",
        "transfer_id": resp.get("id", resp.get("kind", "simulated")),
        "mode": "live" if client.live else "demo",
    })
    return JSONResponse(content={"success": True})


@app.get("/transfer_blotter")
def transfer_blotter() -> list[dict]:
    return _TRANSFER_BLOTTER or [_EMPTY_TRANSFER]


# -- helpers ----------------------------------------------------------------

_EMPTY_ORDER = {"symbol": None, "side": None, "notional_usdc": None, "status": None, "order_id": None, "mode": None}
_EMPTY_DCA = {"symbol": None, "amount_usdc": None, "frequency": None, "status": None, "schedule_id": None, "mode": None}
_EMPTY_TRANSFER = {"to": None, "amount": None, "token": None, "status": None, "transfer_id": None, "mode": None}


def _usd(v) -> str:
    try:
        return f"${float(v):,.2f}"
    except (TypeError, ValueError):
        return "-"


def _num(v) -> str:
    try:
        return f"{float(v):.2f}"
    except (TypeError, ValueError):
        return ""


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
