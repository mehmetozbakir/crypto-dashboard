# --- core/lwc_history.py -------------------------------------------------
"""
REST'ten (Binance / Bybit) istediğin zaman diliminde en fazla 1000 mum
çekip Lightweight Charts için dizi üretir.
˓→  get_klines(exchange, symbol, interval) → list[dict]
"""

import time, requests

INT_MAP = {"1m":"1m", "5m":"5m", "15m":"15m", "1h":"1h", "4h":"4h", "1d":"1d"}

def _binance(symbol:str, interval:str):
    url = "https://fapi.binance.com/fapi/v1/klines"
    r = requests.get(url, params={"symbol":symbol, "interval":interval,
                                  "limit":1000}, timeout=8)
    r.raise_for_status()
    return [{
        "time": k[0]//1000,
        "open": float(k[1]), "high": float(k[2]),
        "low":  float(k[3]), "close":float(k[4])
    } for k in r.json()]

def _bybit(symbol: str, interval: str):
    url = "https://api.bybit.com/v5/market/kline"      # ← tek satır değişti
    r = requests.get(url, params={
        "category": "linear",
        "symbol":   symbol,
        "interval": INT_MAP[interval],
        "limit":    1000
    }, timeout=8)
    r.raise_for_status()
    out = []
    for k in reversed(r.json()["result"]["list"]):        # old → new
        out.append({
            "time":  int(k[0]) // 1000,
            "open":  float(k[1]),
            "high":  float(k[2]),
            "low":   float(k[3]),
            "close": float(k[4])
        })
    return out

def get_klines(exchange:str, symbol:str, interval:str):
    try:
        return _binance(symbol, interval) if exchange=="Binance" else _bybit(symbol, interval)
    except Exception as e:
        print(f"[WARN] REST history fail → {e} (live WS ile devam)")
        return []
