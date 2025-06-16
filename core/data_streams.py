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
        r = requests.get(url, params={"symbol":symbol, "interval":"1m", "limit":1440}, timeout=8)
        r.raise_for_status()
        rows = [(k[0]//1000, *map(float, k[1:6])) for k in r.json()]

    elif exchange == "Bybit":
        url = "https://api.bybit.com/v5/market/kline"
        r = requests.get(url, params={
            "category":"linear",
            "symbol":symbol,
            "interval":"1",
            "limit":1440
        }, timeout=8)
        r.raise_for_status()
        rows = [
            (int(k[0])//1000,
             float(k[1]), float(k[2]), float(k[3]),
             float(k[4]), float(k[5]))
            for k in reversed(r.json()["result"]["list"])
        ]

    elif exchange == "OKX":
        url = "https://www.okx.com/api/v5/market/history-candles"
        r = requests.get(url, params={
            "instType":"UMCBL",
            "instId":symbol,
            "bar":"1m",
            "limit":1440
        }, timeout=8)
        r.raise_for_status()
        data = r.json().get("data", [])
        rows = [
            (int(k[0])//1000,
             float(k[1]), float(k[2]), float(k[3]),
             float(k[4]), float(k[5]))
            for k in data
        ]

    else:
        raise ValueError(f"Unsupported exchange for history fetch: {exchange}")

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
    stream_fn = _STREAMS.get(exchange)
    if stream_fn is None:
        raise ValueError(f"No WS stream found for exchange: {exchange}")
    _WS_TASKS.append(asyncio.create_task(stream_fn(symbol)))

def df_candles(tf="1m") -> pd.DataFrame:
    raw = pd.DataFrame(list(CANDLES[tf]),
                       columns=["epoch","open","high","low","close","vol"])
    if raw.empty:
        return raw
    raw["time"] = pd.to_datetime(raw["epoch"], unit="s", utc=True)
    return raw.set_index("time")
# ────────────────────────────── BITGET WS ────────────────────────────────
async def _bitget_stream(sym: str):
    """Bitget USDT-perp trades"""
    uri = "wss://ws.bitget.com/mix/v1/stream"
    sub = json.dumps({
        "op": "subscribe",
        "args": [{"channel": "trade", "instId": sym}]
    })
    while True:
        try:
            async with websockets.connect(uri, ping_interval=20) as ws:
                await ws.send(sub)
                async for msg in ws:
                    m = json.loads(msg)
                    if m.get("action") != "push":
                        continue
                    for d in m.get("data", []):
                        TICKS.append((
                            d["ts"] // 1000,
                            float(d["price"]),
                            float(d["size"]),
                            "sell" if d["side"] == "sell" else "buy"
                        ))
        except Exception as e:
            print("[WS] Bitget reconnect:", e)
            await asyncio.sleep(5)


# ─────────────────────────────── HTX / HUOBI ─────────────────────────────
async def _htx_stream(sym: str):
    """HTX (Huobi) linear-swap trades"""
    uri = "wss://api.huobi.pro/ws"
    ch = f"market.{sym.lower()}.trade.detail"
    sub = json.dumps({"sub": ch, "id": "id1"})
    while True:
        try:
            async with websockets.connect(uri, ping_interval=20) as ws:
                await ws.send(sub)
                async for raw in ws:
                    if isinstance(raw, bytes):
                        raw = zlib.decompress(raw, 31).decode()
                    msg = json.loads(raw)
                    if "ping" in msg:
                        await ws.send(json.dumps({"pong": msg["ping"]}))
                        continue
                    if msg.get("ch") != ch:
                        continue
                    for td in msg["tick"]["data"]:
                        TICKS.append((
                            td["ts"] // 1000,
                            float(td["price"]),
                            float(td["amount"]),
                            "sell" if td["direction"] == "sell" else "buy"
                        ))
        except Exception as e:
            print("[WS] HTX reconnect:", e)
            await asyncio.sleep(5)


# ─────────────────────────────── KUCOIN (poll) ───────────────────────────
async def _kucoin_stream(sym: str):
    """KuCoin futures REST-poll every second (skips WS auth handshake)"""
    url = f"https://api.kucoin.com/api/v1/contracts/{sym}/trades"
    last_seq = None
    while True:
        try:
            r = requests.get(url, timeout=5)
            r.raise_for_status()
            for tr in reversed(r.json()["data"]):
                seq = tr["sequence"]
                if last_seq is None or seq > last_seq:
                    TICKS.append((
                        int(tr["time"]) // 1000,
                        float(tr["price"]),
                        float(tr["size"]),
                        "sell" if tr["side"] == "sell" else "buy"
                    ))
                    last_seq = seq
        except Exception as e:
            print("[WS] KuCoin poll err:", e)
        await asyncio.sleep(1)


# ────────────────────────────── OKX WS ──────────────────────────────────
async def _okx_stream(sym: str):
    """OKX USDT-margined perpetual trades"""
    uri = "wss://ws.okx.com:8443/ws/v5/public"
    sub = json.dumps({
        "op": "subscribe",
        "args": [{"channel": "trades", "instType": "UMCBL", "instId": sym}]
    })
    while True:
        try:
            async with websockets.connect(uri, ping_interval=20) as ws:
                await ws.send(sub)
                async for msg in ws:
                    m = json.loads(msg)
                    # Sadece trades kanalından gelenleri al
                    arg = m.get("arg", {})
                    if arg.get("channel") != "trades":
                        continue
                    for d in m.get("data", []):
                        TICKS.append((
                            d["ts"] // 1000,
                            float(d["px"]),
                            float(d["sz"]),
                            "sell" if d["side"] == "sell" else "buy"
                        ))
        except Exception as e:
            print("[WS] OKX reconnect:", e)
            await asyncio.sleep(5)

# ────────────── Son olarak, _STREAMS sözlüğünüze ekleyin ────────────────
_STREAMS = {
    "Binance":  _binance_stream,
    "Bybit":    _bybit_stream,
    "OKX":      _okx_stream,
    "Bitget":   _bitget_stream,
    "HTX":      _htx_stream,
    "KuCoin":   _kucoin_stream,
}

