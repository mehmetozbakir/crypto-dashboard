"""
helpers_header.py
──────────────────────────────────────────────
• CoinMarketCap (mcap / arz / hacim) + CoinGecko (ATH / ATL) başlığı
• Dışa aktardığı öğeler:
    - header_row  (Panel Row, doğrudan layout’a eklenir)
    - update_header(symbol)  → header bilgilerini yeniler
"""

import os, requests
from datetime import datetime, timedelta
import panel as pn
from dotenv import load_dotenv
load_dotenv()

# ── API Ayarları
CMC_KEY   = os.getenv("CMC_KEY", "")
CMC_URL   = "https://pro-api.coinmarketcap.com/v2/cryptocurrency/quotes/latest"
CG_MARKET = "https://api.coingecko.com/api/v3/coins/markets"

# ── Pane’ler
left_hdr  = pn.pane.Markdown()
mid_hdr   = pn.pane.Markdown()
right_hdr = pn.pane.Markdown()
header_row = pn.Row(left_hdr, pn.Spacer(width=20),
                    mid_hdr, pn.Spacer(), right_hdr)

# ── Önbellek
_cmc_cache = {}  # {coin: (timestamp, data_dict)}

# ── Yardımcılar
def _fmt(x, dec=0, unit=""):
    return f"{x:,.{dec}f}{unit}" if x else "—"

def _base_coin(sym: str) -> str:
    return sym.replace("USDT", "").replace("USDC", "")

def _cmc_data(coin):
    from datetime import datetime
    now = datetime.utcnow()
    if coin in _cmc_cache and now - _cmc_cache[coin][0] < timedelta(seconds=60):
        return _cmc_cache[coin][1]

    hdr = {"X-CMC_PRO_API_KEY": CMC_KEY}
    for sym in (coin, coin.lstrip("0123456789")):
        r = requests.get(CMC_URL, params={"symbol": sym}, headers=hdr, timeout=8)
        if r.status_code != 200:
            continue
        payload = r.json()["data"].get(sym)
        if not payload:
            continue
        item = payload[0] if isinstance(payload, list) else payload
        q = item["quote"]["USD"]
        data = dict(
            mcap=q.get("market_cap", 0),
            total=item.get("total_supply", 0),
            circul=item.get("circulating_supply", 0),
            max=item.get("max_supply", 0),
            vol24=q.get("volume_24h", 0),
        )
        _cmc_cache[coin] = (now, data)
        return data
    raise ValueError(f"{coin} CMC’de bulunamadı")

def _cg_ath_atl(coin):
    try:
        r = requests.get(CG_MARKET, params={
            "vs_currency": "usd", "ids": coin.lower()
        }, timeout=6)
        r.raise_for_status()
        data = r.json()
        if data:
            return data[0]["ath"], data[0]["atl"]
    except Exception:
        pass
    return None, None

# ── Kamuya açık fonksiyon
def update_header(symbol: str):
    """
    symbol = 'BTCUSDT', '1000PEPEUSDT' …
    Pane içeriklerini günceller.
    """
    coin = _base_coin(symbol)
    try:
        cmc = _cmc_data(coin) if CMC_KEY else {}
    except Exception as e:
        cmc = {}
        mid_hdr.object = f"*CMC hata: {e}*"

    # CoinGecko her zaman
    ath, atl = _cg_ath_atl(coin)

    left_hdr.object = f"### **{coin}**"

    mid_hdr.object = (
        f"Piyasa Değeri: **{_fmt(cmc.get('mcap'), 0, '$')}** &nbsp;—&nbsp; "
        f"Toplam Arz: **{_fmt(cmc.get('total'))}** &nbsp;—&nbsp; "
        f"Dolaşımdaki Arz: **{_fmt(cmc.get('circul'))}** &nbsp;—&nbsp; "
        f"Maks. Arz: **{_fmt(cmc.get('max'))}** &nbsp;—&nbsp; "
        f"24 s Hacim: **{_fmt(cmc.get('vol24'), 0, '$')}**"
    )

    right_hdr.object = (
        f"Tüm Zamanların En Düşük: **{_fmt(atl, 2, '$')}**  <br>"
        f"Tüm Zamanların En Yüksek: **{_fmt(ath, 2, '$')}**"
    )
