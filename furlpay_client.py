"""
Thin FurlPay REST client for the OpenBB Workspace backend.

The plugin is clone-and-run: with no FURLPAY_API_KEY set it serves deterministic
demo data so a reviewer can add the backend to OpenBB and see every widget render
immediately. Set FURLPAY_API_KEY (and optionally FURLPAY_API_BASE) to hit the live
API at https://api.furlpay.com/v1 instead.

Only the endpoints the widgets need are wrapped. Every call fails soft: on a
network/auth error it falls back to demo data and flags the row, so a widget never
renders an empty grid during a demo.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

DEFAULT_BASE = "https://api.furlpay.com/v1"
TIMEOUT = httpx.Timeout(15.0, connect=5.0)


@dataclass
class FurlPayClient:
    api_key: str | None = None
    base_url: str = DEFAULT_BASE

    @classmethod
    def from_env(cls) -> "FurlPayClient":
        return cls(
            api_key=os.getenv("FURLPAY_API_KEY") or None,
            base_url=os.getenv("FURLPAY_API_BASE", DEFAULT_BASE).rstrip("/"),
        )

    @property
    def live(self) -> bool:
        """True when a key is configured; otherwise the plugin runs on demo data."""
        return bool(self.api_key)

    # -- transport ----------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "User-Agent": "furlpay-openbb-plugin/0.1.0",
        }

    def _get(self, path: str, params: dict | None = None) -> dict | list:
        with httpx.Client(timeout=TIMEOUT) as c:
            r = c.get(f"{self.base_url}{path}", headers=self._headers(), params=params)
            r.raise_for_status()
            return r.json()

    def _post(self, path: str, body: dict) -> dict:
        with httpx.Client(timeout=TIMEOUT) as c:
            r = c.post(f"{self.base_url}{path}", headers=self._headers(), json=body)
            r.raise_for_status()
            return r.json()

    # -- reads (data widgets) ----------------------------------------------

    def portfolio(self) -> dict:
        if not self.live:
            return _DEMO_PORTFOLIO
        try:
            return self._get("/investing/portfolio")  # type: ignore[return-value]
        except Exception:
            return {**_DEMO_PORTFOLIO, "_demo": True}

    def positions(self) -> list[dict]:
        if not self.live:
            return _DEMO_POSITIONS
        try:
            data = self._get("/investing/positions")
            return data if isinstance(data, list) else data.get("data", [])  # type: ignore[union-attr]
        except Exception:
            return _mark_demo(_DEMO_POSITIONS)

    def balances(self) -> list[dict]:
        if not self.live:
            return _DEMO_BALANCES
        try:
            data = self._get("/wallets/balances")
            return data if isinstance(data, list) else data.get("data", [])  # type: ignore[union-attr]
        except Exception:
            return _mark_demo(_DEMO_BALANCES)

    def paywalls(self) -> list[dict]:
        if not self.live:
            return _DEMO_PAYWALLS
        try:
            data = self._get("/x402/paywalls")
            rows = data if isinstance(data, list) else data.get("data", [])  # type: ignore[union-attr]
            return rows or _DEMO_PAYWALLS
        except Exception:
            return _mark_demo(_DEMO_PAYWALLS)

    def payments(self, limit: int = 15) -> list[dict]:
        if not self.live:
            return _DEMO_PAYMENTS[:limit]
        try:
            data = self._get("/payments", params={"limit": limit})
            rows = data if isinstance(data, list) else data.get("data", [])  # type: ignore[union-attr]
            return rows[:limit]
        except Exception:
            return _mark_demo(_DEMO_PAYMENTS[:limit])

    # -- writes (execution widgets — the layer OpenBB lacks) ----------------

    def place_order(self, symbol: str, side: str, notional: float) -> dict:
        body = {"symbol": symbol.upper(), "side": side.lower(), "notional": notional, "currency": "USDC"}
        if not self.live:
            return _simulated_ack("order", body)
        return self._post("/investing/orders", body)

    def create_auto_invest(self, symbol: str, amount: float, frequency: str) -> dict:
        body = {"symbol": symbol.upper(), "amount": amount, "frequency": frequency, "currency": "USDC"}
        if not self.live:
            return _simulated_ack("auto-invest", body)
        return self._post("/investing/auto-invest", body)

    def send_transfer(self, to: str, amount: float, token: str = "USDC") -> dict:
        body = {"to": to, "amount": amount, "token": token}
        if not self.live:
            return _simulated_ack("transfer", body)
        return self._post("/transfers", body)


# -- demo fixtures ----------------------------------------------------------
# Deterministic so the widgets look identical every render in demo mode.

def _mark_demo(rows: list[dict]) -> list[dict]:
    return [{**r, "source": "demo"} for r in rows]


def _simulated_ack(kind: str, body: dict) -> dict:
    return {
        "success": True,
        "simulated": True,
        "kind": kind,
        "detail": "Demo mode — set FURLPAY_API_KEY to execute against the live API.",
        "echo": body,
    }


_now = datetime.now(timezone.utc)

_DEMO_PORTFOLIO = {
    "total_value": 12840.55,
    "cash": 3120.10,
    "invested": 9720.45,
    "unrealized_pl": 742.18,
    "unrealized_pl_pct": 8.28,
    "positions_count": 5,
}

_DEMO_POSITIONS = [
    {"symbol": "VOO", "qty": 8.0, "avg_price": 512.40, "last_price": 548.90, "market_value": 4391.20, "unrealized_pl": 292.00, "unrealized_pl_pct": 7.12},
    {"symbol": "AAPL", "qty": 6.0, "avg_price": 222.10, "last_price": 241.75, "market_value": 1450.50, "unrealized_pl": 117.90, "unrealized_pl_pct": 8.85},
    {"symbol": "NVDA", "qty": 4.0, "avg_price": 168.30, "last_price": 182.60, "market_value": 730.40, "unrealized_pl": 57.20, "unrealized_pl_pct": 8.50},
    {"symbol": "VTI", "qty": 9.0, "avg_price": 268.00, "last_price": 279.15, "market_value": 2512.35, "unrealized_pl": 100.35, "unrealized_pl_pct": 4.16},
    {"symbol": "MSFT", "qty": 1.5, "avg_price": 402.00, "last_price": 425.00, "market_value": 637.50, "unrealized_pl": 34.50, "unrealized_pl_pct": 5.72},
]

_DEMO_BALANCES = [
    {"token": "USDC", "network": "Solana", "balance": 3120.10, "usd_value": 3120.10},
    {"token": "USDC", "network": "Base", "balance": 480.00, "usd_value": 480.00},
    {"token": "SOL", "network": "Solana", "balance": 6.42, "usd_value": 1123.50},
]

_DEMO_PAYWALLS = [
    {"resource": "/api/premium/quote", "network": "Solana", "calls_24h": 1842, "price_usdc": 0.01, "revenue_24h": 18.42, "revenue_30d": 512.80},
    {"resource": "/api/premium/screener", "network": "Solana", "calls_24h": 640, "price_usdc": 0.05, "revenue_24h": 32.00, "revenue_30d": 918.50},
    {"resource": "/api/premium/fundamentals", "network": "Base", "calls_24h": 221, "price_usdc": 0.10, "revenue_24h": 22.10, "revenue_30d": 604.30},
]

_DEMO_PAYMENTS = [
    {"id": f"pay_demo{i}", "created": (_now - timedelta(hours=i * 3)).isoformat(),
     "amount": round(5 + i * 7.5, 2), "currency": "USDC",
     "status": ["completed", "completed", "pending", "completed"][i % 4],
     "description": ["x402 API call", "Checkout", "Card top-up", "Agent budget"][i % 4]}
    for i in range(15)
]
