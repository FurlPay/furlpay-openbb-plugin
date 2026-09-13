# FurlPay for OpenBB

![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![OpenBB](https://img.shields.io/badge/OpenBB-FFDC00?style=flat-square)
![Solana](https://img.shields.io/badge/Solana-9945FF?style=flat-square&logo=solana&logoColor=white)
![x402](https://img.shields.io/badge/x402-0052FF?style=flat-square)

The **execution layer** for [OpenBB Workspace](https://openbb.co). OpenBB gives analysts and AI agents world-class financial *data* — but it can't move a dollar. This backend adds the missing half: screen an asset in OpenBB, then **trade it, dollar-cost-average into it, or settle agentic API revenue** — all funded and settled in stablecoins, 24/7.

It registers as a standard OpenBB [custom backend](https://docs.openbb.co/workspace/developers/data-integration) (serves `/widgets.json` + `/apps.json`) and ships a ready-made **"Research → Execution"** app. Zero-config: it runs on deterministic demo data out of the box, and goes live the moment you set a FurlPay API key.

Maintained by [FurlPay](https://furlpay.com) · MIT licensed.

## Why

Every incumbent in 2026 ships data + MCP and stops there — [OpenBB](https://openbb.co/blog/introducing-workspace-mcp/), [Morningstar](https://developer.morningstar.com/direct-web-services/documentation/morningstar-mcp-server/about), Bloomberg. None execute. FurlPay is the open-source layer that *does*. This plugin drops that execution layer directly into the OpenBB canvas an analyst already lives in.

## Widgets

| Widget | Type | What it does |
| --- | --- | --- |
| **Research → Execute** | markdown | Explains the research→execute loop; shows live/demo mode |
| **Portfolio Summary** | metric | Total value, invested, USDC cash, unrealized P&L |
| **Positions** | table | Open positions with cost basis and P&L (green/red) |
| **Stablecoin Balances** | table | USDC + tokens across Solana and Base |
| **x402 Paywall Revenue** | table + chart | Per-resource agentic API calls and USDC revenue |
| **Recent Payments** | table | Latest checkout / card / x402 payments |
| **Place Order** ⚡ | form | Buy/sell a fractional position, funded in USDC |
| **Auto-Invest (DCA)** ⚡ | form | Schedule a recurring stablecoin buy |
| **Send Stablecoins** ⚡ | form | Send USDC/USDT to a wallet or FurlPay handle |

⚡ = **action widget** — the execution OpenBB itself doesn't have. Each form POSTs to FurlPay and refreshes a blotter table with the result.

## Quickstart

```sh
pip install -r requirements.txt
uvicorn main:app --reload --port 7777
```

Then in OpenBB Workspace → **Apps → Connect backend → Custom backend**, add:

```
http://localhost:7777
```

The **FurlPay — Research to Execution** app appears with four tabs (Overview, Investing, Agentic, Execute). Every widget renders immediately on demo data.

### Go live

```sh
cp .env.example .env
# edit .env:  FURLPAY_API_KEY=fp_live_sk_...
```

With a key set, reads hit `GET https://api.furlpay.com/v1/...` and the action forms execute real orders, DCA schedules, and transfers. Without a key the plugin stays in **demo mode** — every call returns deterministic sample data and the forms simulate (never touching the network), so you can evaluate the whole app safely.

Point at a sandbox with `FURLPAY_API_BASE=https://sandbox.api.furlpay.com/v1`.

## How it fits OpenBB

- `GET /widgets.json` returns a **dict** of widget definitions (OpenBB's required shape).
- `GET /apps.json` returns an **array** with one app; its tabs place widgets on a 40-column grid.
- CORS allows `https://pro.openbb.co` (+ localhost) so the browser client can reach the backend.
- Action widgets use OpenBB's `form` parameter: the form POSTs to an execution endpoint; on `200` the widget auto-refreshes its blotter GET.

## Deploy

```sh
docker build -t furlpay-openbb .
docker run -p 7777:7777 -e FURLPAY_API_KEY=fp_live_sk_... furlpay-openbb
```

Any host that exposes port 7777 over HTTPS works as an OpenBB custom backend — Fly, Render, a Vercel Python function, or your own box.

## Test

```sh
pip install pytest
python -m pytest test_backend.py -q      # 12 contract tests
# or, no pytest:
python test_backend.py
```

The suite asserts the exact OpenBB contract: `widgets.json` is a dict and `apps.json` an array, every widget endpoint has a live route, every app layout references a real widget, every action form POSTs and its blotter reflects the submission, and metric/table/markdown shapes are correct. Green = it will register and render in OpenBB.

## Scope

This backend orchestrates FurlPay's public API into OpenBB widgets. It does not custody funds or sign transactions itself — execution happens in the FurlPay API, which handles wallets, MPC custody, brokerage (via Alpaca), and x402 settlement. Point it at your own FurlPay account and it operates on your data.

## License

MIT
