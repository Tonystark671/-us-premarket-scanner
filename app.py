from __future__ import annotations

import math
import os
import time
from datetime import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

import requests
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

TV_URL = "https://scanner.tradingview.com/america/scan"
UA = {"User-Agent": "Mozilla/5.0 USMomentumScanner/1.0"}
NY = ZoneInfo("America/New_York")

MIN_TOTAL_MOVE = 5.0
MIN_TOTAL_VOLUME = 90_000
MAX_ROWS = 40

# TradingView scanner columns. The app calculates the latest candle move from open|15 -> close|15.
TV_COLUMNS = [
    "name", "description", "exchange", "close", "change", "volume",
    "open|15", "close|15", "volume|15", "EMA20|15", "EMA50|15", "BB.upper|15",
    "premarket_change", "premarket_volume", "premarket_close",
    "postmarket_change", "postmarket_volume", "postmarket_close",
    "relative_volume_10d_calc",
]



def current_session(now: datetime | None = None) -> str:
    now = (now or datetime.now(tz=NY)).astimezone(NY)
    if now.weekday() >= 5:
        return "CLOSED"
    m = now.hour * 60 + now.minute
    if m >= 20 * 60 or m < 4 * 60:
        return "OVERNIGHT"
    if m < 9 * 60 + 30:
        return "PRE-MARKET"
    if m < 16 * 60:
        return "MARKET"
    if m < 20 * 60:
        return "AFTER-HOURS"
    return "CLOSED"


def fnum(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def tv_scan(session="MARKET") -> list[dict]:
    payload = {
        "filter": [
            {"left": "type", "operation": "equal", "right": "stock"},
            {"left": "is_primary", "operation": "equal", "right": True},
        ],
        "options": {"lang": "en"},
        "markets": ["america"],
        "symbols": {"query": {"types": []}, "tickers": []},
        "columns": TV_COLUMNS,
        "sort": {"sortBy": {"PRE-MARKET": "premarket_change", "AFTER-HOURS": "postmarket_change"}.get(session, "change|15"), "sortOrder": "desc"},
        "range": [0, 250],
    }
    r = requests.post(TV_URL, json=payload, headers=UA, timeout=12)
    r.raise_for_status()
    raw = r.json().get("data", [])
    rows = []
    for item in raw:
        values = item.get("d", [])
        if len(values) != len(TV_COLUMNS):
            continue
        d = dict(zip(TV_COLUMNS, values))
        rows.append(d)
    return rows


@lru_cache(maxsize=256)
def _cached_news(ticker: str, bucket: int) -> str:
    # Best-effort, no-key headline lookup. If unavailable, return blank as requested.
    try:
        url = "https://query1.finance.yahoo.com/v1/finance/search"
        r = requests.get(url, params={"q": ticker, "quotesCount": 1, "newsCount": 3}, headers=UA, timeout=5)
        r.raise_for_status()
        news = r.json().get("news", [])
        if not news:
            return ""
        title = str(news[0].get("title") or "").strip()
        return title[:150]
    except Exception:
        return ""


def news_for(ticker: str) -> str:
    return _cached_news(ticker, int(time.time() // 300))


def normalize(rows: list[dict], session: str) -> list[dict]:
    out = []
    if session in ("OVERNIGHT", "CLOSED"):
        return []
    signal_time = None
    for d in rows:
        ticker = str(d.get("name") or "").strip()
        if not ticker:
            continue

        o15, c15 = fnum(d.get("open|15")), fnum(d.get("close|15"))
        move15 = ((c15 - o15) / o15 * 100) if o15 and c15 else None
        base_price = fnum(d.get("close"))
        regular_change = fnum(d.get("change"))
        regular_vol = fnum(d.get("volume")) or 0

        if session == "PRE-MARKET":
            total_move = fnum(d.get("premarket_change"))
            total_vol = fnum(d.get("premarket_volume")) or 0
            price = fnum(d.get("premarket_close"))
        elif session == "AFTER-HOURS":
            total_move = fnum(d.get("postmarket_change"))
            total_vol = fnum(d.get("postmarket_volume")) or 0
            price = fnum(d.get("postmarket_close"))
        elif session == "MARKET":
            total_move = regular_change
            total_vol = regular_vol
            price = c15 or base_price
        else:
            continue

        if price is None or total_move is None:
            continue
        if total_move < MIN_TOTAL_MOVE or total_vol < MIN_TOTAL_VOLUME:
            continue

        ema20 = fnum(d.get("EMA20|15"))
        ema50 = fnum(d.get("EMA50|15"))
        upper = fnum(d.get("BB.upper|15"))
        vol15 = fnum(d.get("volume|15")) or 0
        rel = fnum(d.get("relative_volume_10d_calc"))

        # Intraday indicators from this endpoint are not verified for extended sessions.
        if session != "MARKET":
            move15 = ema20 = ema50 = upper = vol15 = rel = None

        signals = []
        if move15 is not None and move15 >= 5:
            signals.append("NEW MOMENTUM")
        elif move15 is not None and move15 >= 3:
            signals.append("EARLY MOVE")
        if price is not None and upper is not None and price > upper:
            signals.append("ABOVE UPPER BB (developing)")
        if ema20 is not None and ema50 is not None and ema20 > ema50:
            signals.append("EMA20 > EMA50")
        if rel is not None and rel >= 2:
            signals.append("DAILY RVOL ≥ 2")
        if move15 is not None and move15 < 3 and total_move >= 20:
            signals.append("OLD MOVE")

        out.append({
            "ticker": ticker,
            "company": d.get("description") or "",
            "exchange": d.get("exchange") or "",
            "session": session,
            "price": price,
            "move15": move15,
            "total_move": total_move,
            "vol15": vol15,
            "total_volume": total_vol,
            "rel_vol": rel,
            "ema20": ema20,
            "ema50": ema50,
            "upper_bb": upper,
            "signal_time": signal_time,
            "signals": signals,
            "news": "",
        })

    out.sort(key=lambda x: x["move15"] if x["move15"] is not None else x["total_move"], reverse=True)
    out = out[:MAX_ROWS]

    # News is deliberately fetched only for the visible leaders to avoid hammering a free endpoint.
    # Headlines are requested separately to keep scan refreshes fast.
    return out


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/scan")
def api_scan():
    requested = (request.args.get("mode") or "AUTO").upper()
    allowed = {"AUTO", "OVERNIGHT", "PRE-MARKET", "MARKET", "AFTER-HOURS"}
    if requested not in allowed:
        return jsonify({"error": "Invalid session"}), 400
    session = current_session() if requested == "AUTO" else requested
    base = {"session": session, "rows": [], "source": "TradingView public screener", "demo": False,
            "fetched_at": datetime.now(tz=ZoneInfo("UTC")).isoformat()}
    if session in {"OVERNIGHT", "CLOSED"}:
        base["note"] = ("Overnight prices are unavailable from this feed. No regular-session prices are substituted."
                        if session == "OVERNIGHT" else "Outside weekday session schedule. Holiday coverage is not verified.")
        return jsonify(base)
    try:
        base["rows"] = normalize(tv_scan(session), session)
        base["note"] = "Best-effort feed; exchange delay and quote timestamps are unverified. 15m values are developing, not confirmed closed candles."
        if session != "MARKET":
            base["note"] += " Extended-session 15m indicators are unavailable; sorted by session change."
        if requested != "AUTO":
            base["note"] += " Manual session view may contain values from a previous session."
        return jsonify(base)
    except Exception:
        base["note"] = "Market feed unavailable. No demo prices are shown. Try again later."
        return jsonify(base), 503


@app.get("/api/news/<ticker>")
def api_news(ticker):
    if len(ticker) > 15 or not all(c.isalnum() or c in '.-' for c in ticker):
        return jsonify({"error": "Invalid ticker"}), 400
    return jsonify({"headline": news_for(ticker), "note": "Related headline, not a verified explanation for the price move."})


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "session": current_session()})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), debug=False)
