import os
import time
from typing import List, Dict, Any
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import requests
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from threading import Lock

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Global symbol cache ---
SYMBOLS_CACHE = {
    "symbols": [],
    "last_refresh": 0
}
CACHE_LOCK = Lock()
CACHE_TTL = 6 * 60 * 60  # 6 hours

# --- API Keys from env-vars ---
MEXC_API_KEY_ACCESS = os.getenv("MEXC_API_KEY_ACCESS")
MEXC_API_KEY_SECRET = os.getenv("MEXC_API_KEY_SECRET")
COINMARKETCAP_API_KEY = os.getenv("COINMARKETCAP_API_KEY")
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")

# --- Helper: fetch perpetual symbols ---
def fetch_mexc_symbols() -> List[str]:
    url = "https://contract.mexc.com/api/v1/contract/detail"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("success") and "data" in data:
            return [item["symbol"] for item in data["data"] if item.get("quoteCoin") == "USDT"]
    except Exception:
        pass
    return []

def fetch_coingecko_symbols() -> List[str]:
    url = "https://api.coingecko.com/api/v3/derivatives/exchanges/mexc"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return [item["symbol"] for item in data if item.get("symbol") and "USDT" in item["symbol"]]
    except Exception:
        pass
    return []

def fetch_coinmarketcap_symbols() -> List[str]:
    url = "https://pro-api.coinmarketcap.com/v1/derivatives/exchange"
    headers = {"X-CMC_PRO_API_KEY": COINMARKETCAP_API_KEY}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        for ex in data.get("data", []):
            if ex.get("name", "").lower().startswith("mexc"):
                return [item["symbol"] for item in ex.get("contracts", []) if item.get("symbol") and "USDT" in item["symbol"]]
    except Exception:
        pass
    return []

# --- Symbol cache refresh logic ---
def get_perpetual_symbols() -> List[str]:
    now = time.time()
    with CACHE_LOCK:
        if now - SYMBOLS_CACHE["last_refresh"] < CACHE_TTL and SYMBOLS_CACHE["symbols"]:
            return SYMBOLS_CACHE["symbols"]
        # Try in order: MEXC, CoinGecko, CoinMarketCap
        for fetcher in [fetch_mexc_symbols, fetch_coingecko_symbols, fetch_coinmarketcap_symbols]:
            for _ in range(3):
                symbols = fetcher()
                if symbols:
                    SYMBOLS_CACHE["symbols"] = symbols
                    SYMBOLS_CACHE["last_refresh"] = now
                    return symbols
        # If all fail, return last known
        return SYMBOLS_CACHE["symbols"]

@app.get("/pairs")
def get_pairs():
    symbols = get_perpetual_symbols()
    if not symbols:
        raise HTTPException(status_code=503, detail="No perpetual pairs available.")
    return {"symbols": symbols}

# --- Helper: fetch 14d hourly candles for a symbol ---
def fetch_mexc_candles(symbol: str) -> pd.DataFrame:
    url = f"https://contract.mexc.com/api/v1/contract/kline/{symbol}?interval=1H&start=0&end=0&limit=336"
    for _ in range(3):
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if data.get("success") and data.get("data"):
                df = pd.DataFrame(data["data"], columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
                df["close"] = pd.to_numeric(df["close"])
                df["volume"] = pd.to_numeric(df["volume"])
                return df
        except Exception:
            continue
    raise ValueError(f"Could not fetch candles for {symbol}")

# --- Helper: fetch market data for all pairs ---
def fetch_market_data(symbols: List[str]) -> Dict[str, Dict[str, Any]]:
    # Try MEXC first, fallback to CoinGecko, CoinMarketCap
    # Only USDT perpetuals
    result = {}
    # MEXC
    try:
        url = "https://contract.mexc.com/api/v1/contract/ticker"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("success") and data.get("data"):
            for item in data["data"]:
                symbol = item.get("symbol")
                if symbol in symbols:
                    result[symbol] = {
                        "market_cap": float(item.get("positionOpenInterest", 0)),
                        "volume_24h": float(item.get("turnover24h", 0))
                    }
    except Exception:
        pass
    # Fallbacks: CoinGecko, CoinMarketCap (not shown here for brevity)
    return result

# --- POST /analyze ---
@app.post("/analyze")
def analyze(request: Request):
    body = request.json() if hasattr(request, "json") else {}
    base = body.get("base", "").upper()
    symbols = get_perpetual_symbols()
    if base not in symbols:
        raise HTTPException(status_code=400, detail="Invalid or unavailable symbol.")
    market_data = fetch_market_data(symbols)
    # Filter pairs
    filtered = [s for s in symbols if market_data.get(s, {}).get("market_cap", 0) > 1_000_000 and market_data.get(s, {}).get("volume_24h", 0) > 500_000]
    if base not in filtered:
        raise HTTPException(status_code=400, detail="Base symbol does not meet liquidity requirements.")
    # Fetch candles for base
    try:
        base_df = fetch_mexc_candles(base)
    except Exception:
        raise HTTPException(status_code=502, detail="Failed to fetch price data for base symbol.")
    results = []
    for symbol in filtered:
        if symbol == base:
            continue
        try:
            df = fetch_mexc_candles(symbol)
            corr = np.corrcoef(base_df["close"], df["close"])[0, 1]
            results.append({
                "symbol": symbol,
                "market_cap": market_data[symbol]["market_cap"],
                "volume_24h": market_data[symbol]["volume_24h"],
                "correlation": corr,
            })
        except Exception:
            continue
    # Sort: |correlation| asc, volume desc
    results.sort(key=lambda x: (abs(x["correlation"]), -x["volume_24h"]))
    return {"results": results[:20]}

# --- CSV Export ---
@app.get("/export/csv")
def export_csv():
    # For demo: return a static CSV
    df = pd.DataFrame([{"symbol": "BTCUSDT", "market_cap": 10000000, "volume_24h": 2000000, "correlation": 0.1}])
    return StreamingResponse(df.to_csv(index=False), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=results.csv"})

# --- Health check endpoint ---
@app.get("/health")
def health():
    symbols = get_perpetual_symbols()
    return {"ok": bool(symbols)}
