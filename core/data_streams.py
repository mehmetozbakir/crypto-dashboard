# core/data_streams.py
# ────────────────────  (yalın – sadece websocket+history görevleri)

import asyncio, json, time, requests, websockets, pandas as pd
from collections import deque

# ........................ global tamponlar
TICKS: deque = deque(maxlen=6_000)                    # (ts, price, qty, side)
CANDLES = {tf: deque(maxlen=1_500) for tf in
           ("1m", "5m", "15m", "1h", "4h", "1d")}
_WS_TASKS = []

# ........................ yardımcılar
_MINUTES = {"5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1_440}

def _aggregate_last(tf):
    m = _MINUTES[tf]
    chunk = list(CANDLES["1m"])[-m:]
    if len(chunk) < m:
        return
    t0, o, *_ = chunk[0]
    *_, c = chunk[-1]
    hi = max(r[2] for r in chunk)
    lo = min(r[3] for r in chunk)
    vol = sum(r[5] for r in chunk)
    CANDLES[tf].append((t0, o, hi, lo, c, vol))

def _backfill_higher_tfs():
    for tf in _MINUTES:
        CANDLES[tf].clear()
    for i in range(len(CANDLES["1m"])):
        if (i + 1) % _MINUTES["5m"]  == 0: _aggregate_last("5m")
        if (i + 1) % _MINUTES["15m"] == 0: _aggregate_last("15m")
        if (i + 1) % _MINUTES["1h"]  == 0: _aggregate_last("1h")
        if (i + 1) % _MINUTES["4h"]  == 0: _aggregate_last("4h")
        if (i + 1) % _MINUTES["1d"]  == 0: _aggregate_last("1d")

# ........................ REST geçmiş (1000 × 1 dak.)
def _fetch_history_1m(exchange, symbol):
    if exchange == "Binance":
        url = "https://fapi.binance.com/fapi/v1/klines"
        r = requests.get(url, params={"symbol":symbol, "interval":"1m", "limit":1000}, timeout=8)
        r.raise_for_status()
        rows = [(k[0]//1000, *map(float, k[1:6])) for k in r.json()]
    else:                                            # Bybit
        url = "https://api.bybit.com/v5/market/kline"
        r = requests.get(url, params={
            "category":"linear", "symbol":symbol,
            "interval":"1", "limit":1000}, timeout=8)
        r.raise_for_status()
        rows = [(int(k[0])//1000, float(k[1]), float(k[2]),
                 float(k[3]), float(k[4]), float(k[5]))
                for k in reversed(r.json()["result"]["list"])]
    CANDLES["1m"].extend(rows)

# ........................ WebSocket toplama
async def _binance_stream(sym):
    uri = f"wss://stream.binance.com/stream?streams={sym.lower()}@trade"
    async with websockets.connect(uri) as ws:
        async for msg in ws:
            d = json.loads(msg)["data"]
            TICKS.append((d["T"]//1000, float(d["p"]), float(d["q"]),
                          "sell" if d["m"] else "buy"))

async def _bybit_stream(sym):
    uri = "wss://stream.bybit.com/v5/public/linear"
    sub = json.dumps({"op":"subscribe", "args":[f"publicTrade.{sym}"]})
    async with websockets.connect(uri) as ws:
        await ws.send(sub)
        async for msg in ws:
            m = json.loads(msg)
            if m.get("topic","").startswith("publicTrade"):
                for tr in m["data"]:
                    TICKS.append((tr["T"]//1000, float(tr["p"]), float(tr["v"]),
                                   "sell" if tr["S"] == "Sell" else "buy"))

# ........................ 1-dakikalık mum üreticisi
async def _candle_worker():
    while True:
        nxt = (int(time.time()) // 60 + 1) * 60
        cur = []
        while time.time() < nxt:
            while TICKS and TICKS[0][0] < nxt:
                cur.append(TICKS.popleft())
            await asyncio.sleep(0.25)

        if cur:
            prices = [p for _, p, *_ in cur]
            vol    = sum(q for *_, q, _ in cur)
            CANDLES["1m"].append((nxt-60, prices[0], max(prices),
                                   min(prices), prices[-1], vol))
            if len(CANDLES["1m"]) > 1_500:
                CANDLES["1m"].popleft()

            for tf in _MINUTES:
                if len(CANDLES["1m"]) % _MINUTES[tf] == 0:
                    _aggregate_last(tf)

asyncio.create_task(_candle_worker())

# ........................ herkese açık API
def restart_stream(exchange, symbol):
    """REST+WS akışını sıfırla, son kapanışı anında fiyat tamponuna koy."""
    # WS’leri kes
    for t in _WS_TASKS: t.cancel()
    _WS_TASKS.clear()

    # tamponları sıfırla
    TICKS.clear()
    for dq in CANDLES.values(): dq.clear()

    # REST geçmiş + son fiyatı dummy tick olarak ekle
    _fetch_history_1m(exchange, symbol)
    if CANDLES["1m"]:
        ts, *_, close, _ = CANDLES["1m"][-1]
        TICKS.append((ts, close, 0, ""))

    _backfill_higher_tfs()

    # yeni WS görevi
    stream = _binance_stream if exchange == "Binance" else _bybit_stream
    _WS_TASKS.append(asyncio.create_task(stream(symbol)))

def df_candles(tf="1m") -> pd.DataFrame:
    raw = pd.DataFrame(list(CANDLES[tf]),
                       columns=["epoch","open","high","low","close","vol"])
    if raw.empty:
        return raw
    raw["time"] = pd.to_datetime(raw["epoch"], unit="s", utc=True)
    return raw.set_index("time")
