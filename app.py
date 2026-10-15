from __future__ import annotations

import math
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

TV_URL = "https://scanner.tradingview.com/america/scan"
YF_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
UA = {"User-Agent": "Mozilla/5.0 Pulse15/1.0"}
NY = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

MAX_CANDIDATES = 35
MAX_ROWS = 35
MIN_TOTAL_VOLUME = 10_000
TV_COLUMNS = [
    "name", "description", "exchange", "close", "change", "volume",
    "premarket_change", "premarket_volume", "premarket_close",
    "postmarket_change", "postmarket_volume", "postmarket_close",
]


def fnum(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def current_session(now=None):
    now = (now or datetime.now(tz=NY)).astimezone(NY)
    if now.weekday() >= 5:
        return "CLOSED"
    m = now.hour * 60 + now.minute
    if 4 * 60 <= m < 9 * 60 + 30:
        return "PRE-MARKET"
    if 9 * 60 + 30 <= m < 16 * 60:
        return "MARKET"
    if 16 * 60 <= m < 20 * 60:
        return "AFTER-HOURS"
    return "OVERNIGHT"


def tv_candidates(session):
    sort_col = {
        "PRE-MARKET": "premarket_change",
        "AFTER-HOURS": "postmarket_change",
    }.get(session, "change")
    payload = {
        "filter": [
            {"left": "type", "operation": "equal", "right": "stock"},
            {"left": "is_primary", "operation": "equal", "right": True},
        ],
        "options": {"lang": "en"},
        "markets": ["america"],
        "symbols": {"query": {"types": []}, "tickers": []},
        "columns": TV_COLUMNS,
        "sort": {"sortBy": sort_col, "sortOrder": "desc"},
        "range": [0, 120],
    }
    r = requests.post(TV_URL, json=payload, headers=UA, timeout=12)
    r.raise_for_status()
    out = []
    for item in r.json().get("data", []):
        vals = item.get("d", [])
        if len(vals) != len(TV_COLUMNS):
            continue
        d = dict(zip(TV_COLUMNS, vals))
        ticker = str(d.get("name") or "").strip()
        if not ticker:
            continue
        if session == "PRE-MARKET":
            total_move = fnum(d.get("premarket_change"))
            total_vol = fnum(d.get("premarket_volume")) or 0
            price = fnum(d.get("premarket_close"))
        elif session == "AFTER-HOURS":
            total_move = fnum(d.get("postmarket_change"))
            total_vol = fnum(d.get("postmarket_volume")) or 0
            price = fnum(d.get("postmarket_close"))
        else:
            total_move = fnum(d.get("change"))
            total_vol = fnum(d.get("volume")) or 0
            price = fnum(d.get("close"))
        if total_move is None or total_vol < MIN_TOTAL_VOLUME:
            continue
        out.append({
            "ticker": ticker,
            "company": d.get("description") or "",
            "exchange": d.get("exchange") or "",
            "price": price,
            "total_move": total_move,
            "total_volume": total_vol,
        })
        if len(out) >= MAX_CANDIDATES:
            break
    return out


def _bucket_15(ts):
    dt = datetime.fromtimestamp(ts, tz=UTC).astimezone(NY)
    minute = (dt.minute // 15) * 15
    return dt.replace(minute=minute, second=0, microsecond=0)


def yf_15m(ticker):
    r = requests.get(
        YF_URL.format(ticker=ticker),
        params={"interval": "5m", "range": "1d", "includePrePost": "true", "events": "div,splits"},
        headers=UA,
        timeout=8,
    )
    r.raise_for_status()
    result = (r.json().get("chart", {}).get("result") or [None])[0]
    if not result:
        return None
    stamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    vols = quote.get("volume") or []

    buckets = {}
    for i, ts in enumerate(stamps):
        if i >= len(opens):
            break
        o, h, l, c = map(fnum, (opens[i], highs[i], lows[i], closes[i]))
        v = fnum(vols[i]) or 0
        if None in (o, h, l, c):
            continue
        b = _bucket_15(ts)
        rec = buckets.setdefault(b, {"open": o, "high": h, "low": l, "close": c, "volume": 0.0, "start": b})
        rec["high"] = max(rec["high"], h)
        rec["low"] = min(rec["low"], l)
        rec["close"] = c
        rec["volume"] += v

    bars = [buckets[k] for k in sorted(buckets)]
    if len(bars) < 2:
        return None
    cur, prev = bars[-1], bars[-2]
    move15 = (cur["close"] / cur["open"] - 1) * 100 if cur["open"] else None
    vol_change = (cur["volume"] / prev["volume"] - 1) * 100 if prev["volume"] else None
    high_change = (cur["high"] / prev["high"] - 1) * 100 if prev["high"] else None
    return {
        "move15": move15,
        "candle": "GREEN" if cur["close"] > cur["open"] else "RED" if cur["close"] < cur["open"] else "FLAT",
        "vol15": cur["volume"],
        "prev_vol15": prev["volume"],
        "vol_change": vol_change,
        "high_change": high_change,
        "bar_start": cur["start"].strftime("%H:%M ET"),
        "bar_end": (cur["start"].timestamp() + 900),
        "last_price": cur["close"],
    }


def build_scan(session):
    candidates = tv_candidates(session)
    rows = []
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(yf_15m, c["ticker"]): c for c in candidates}
        for fut in as_completed(futs):
            base = futs[fut]
            try:
                m = fut.result()
            except Exception:
                m = None
            if not m:
                continue
            row = {**base, **m}
            if row.get("last_price") is not None:
                row["price"] = row["last_price"]
            rows.append(row)
    rows.sort(key=lambda x: (x.get("move15") is not None, x.get("move15") or -999), reverse=True)
    return rows[:MAX_ROWS]


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/scan")
def api_scan():
    requested = (request.args.get("mode") or "AUTO").upper()
    allowed = {"AUTO", "PRE-MARKET", "MARKET", "AFTER-HOURS"}
    if requested not in allowed:
        return jsonify({"error": "Invalid session"}), 400
    session = current_session() if requested == "AUTO" else requested
    base = {
        "session": session,
        "rows": [],
        "source": "TradingView movers + Yahoo 5m bars aggregated to 15m",
        "fetched_at": datetime.now(tz=UTC).isoformat(),
    }
    if session in {"OVERNIGHT", "CLOSED"}:
        base["note"] = "Scanner is designed for pre-market, regular market and after-hours."
        return jsonify(base)
    try:
        base["rows"] = build_scan(session)
        base["note"] = "Latest 15m candle is a developing candle until its 15-minute window closes. Sorted by current 15m % gain, highest first."
        return jsonify(base)
    except Exception as e:
        base["note"] = f"Scanner feed unavailable: {type(e).__name__}"
        return jsonify(base), 503


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "session": current_session(), "time_ny": datetime.now(tz=NY).isoformat()})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), debug=False)
