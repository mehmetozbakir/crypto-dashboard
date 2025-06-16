import sys
import pathlib
import importlib
import time
import requests
import json

import panel as pn

from core.data_streams import restart_stream, TICKS, CANDLES
from core.helpers_header import header_row, update_header
import views.chart as chart_view  # grafik modülü

# ─── TICKER TAPE CONFIGURATION ───────────────────────────────────────
TICKER_SYMBOLS = [
    {"proName": "FOREXCOM:SPXUSD", "title": "S&P 500 Index"},
    {"proName": "FOREXCOM:NSXUSD", "title": "US 100 Cash CFD"},
    {"proName": "FX_IDC:EURUSD",  "title": "EUR to USD"},
    {"proName": "BITSTAMP:BTCUSD","title": "Bitcoin"},
    {"proName": "BITSTAMP:ETHUSD","title": "Ethereum"},
]

def generate_ticker_pane(symbols):
    cfg = {
      "symbols": symbols,
      "showSymbolLogo": True,
      "isTransparent": False,
      "displayMode": "compact",
      "colorTheme": "light",
      "locale": "en"
    }
    embed = f"""
<div class="tradingview-widget-container">
  <div class="tradingview-widget-container__widget"></div>
  <script type="text/javascript"
    src="https://s3.tradingview.com/external-embedding/embed-widget-ticker-tape.js"
    async>
{json.dumps(cfg, indent=2)}
  </script>
</div>
"""
    srcdoc = embed.replace("'", "&#39;").replace("\n", "")
    iframe = (
        f"<iframe srcdoc='{srcdoc}' "
        "style='width:100%;height:60px;border:none;'></iframe>"
    )
    return pn.pane.HTML(iframe, sizing_mode="stretch_width")

ticker_pane = generate_ticker_pane(TICKER_SYMBOLS)

# ─── MARKET OVERVIEW CONFIGURATION ───────────────────────────────────
MARKET_OVERVIEW_CONFIG = {
  "colorTheme": "light",
  "dateRange": "12M",
  "showChart": True,
  "locale": "en",
  "largeChartUrl": "",
  "isTransparent": False,
  "showSymbolLogo": True,
  "showFloatingTooltip": False,
  "width": "400",
  "height": "750",
  "plotLineColorGrowing": "rgba(41, 98, 255, 1)",
  "plotLineColorFalling": "rgba(41, 98, 255, 1)",
  "gridLineColor": "rgba(240, 243, 250, 0)",
  "scaleFontColor": "rgba(15, 15, 15, 1)",
  "belowLineFillColorGrowing": "rgba(41, 98, 255, 0.12)",
  "belowLineFillColorFalling": "rgba(41, 98, 255, 0.12)",
  "belowLineFillColorGrowingBottom": "rgba(41, 98, 255, 0)",
  "belowLineFillColorFallingBottom": "rgba(41, 98, 255, 0)",
  "symbolActiveColor": "rgba(41, 98, 255, 0.12)",
  "tabs": [
    {
      "title": "Indices",
      "symbols": [
        {"s": "FOREXCOM:SPXUSD", "d": "S&P 500 Index"},
        {"s": "FOREXCOM:NSXUSD", "d": "US 100 Cash CFD"},
        {"s": "FOREXCOM:DJI",    "d": "Dow Jones Industrial Average Index"},
        {"s": "INDEX:NKY",       "d": "Japan 225"},
        {"s": "INDEX:DEU40",     "d": "DAX Index"},
        {"s": "FOREXCOM:UKXGBP", "d": "FTSE 100 Index"},
        {"s": "CAPITALCOM:DXY",  "d": "dxy"},
        {"s": "NASDAQ:NDAQ",     "d": "nasdaq"},
        {"s": "TVC:VIX",         "d": "vix"},
        {"s": "CRYPTOCAP:TOTAL"},
        {"s": "CRYPTOCAP:TOTAL2"},
        {"s": "CRYPTOCAP:TOTAL3"},
        {"s": "CRYPTOCAP:OTHERS"},
        {"s": "CRYPTOCAP:TOTALE50"},
        {"s": "CRYPTOCAP:TOTALE100"},
        {"s": "CRYPTOCAP:TOTALDEFI"}
      ],
      "originalTitle": "Indices"
    },
    {
      "title": "Bybit",
      "symbols": []
    }
  ]
}

def generate_market_overview_pane(config):
    embed = f"""
<div class="tradingview-widget-container">
  <div class="tradingview-widget-container__widget"></div>
  <script type="text/javascript"
    src="https://s3.tradingview.com/external-embedding/embed-widget-market-overview.js"
    async>
{json.dumps(config, indent=2)}
  </script>
</div>
"""
    srcdoc = embed.replace("'", "&#39;").replace("\n", "")
    iframe = (
        f"<iframe srcdoc='{srcdoc}' "
        "style='width:100%;height:750px;border:none;'></iframe>"
    )
    return pn.pane.HTML(iframe, sizing_mode="fixed", width=400)

market_overview_pane = generate_market_overview_pane(MARKET_OVERVIEW_CONFIG)

# ─── PATH & EXTENSION SETUP ────────────────────────────────────────
ROOT = pathlib.Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

pn.extension(sizing_mode="stretch_width")

# ─── SYMBOL FETCHER ────────────────────────────────────────────────
def fetch_symbols(exchange: str):
    """
    Seçilen borsanın USDT-margined perpetual (swap) sözleşme listesini döndürür.
    Spot veya coin-m sözleşmeler filtrelenmez.
    """
    try:
        if exchange == "Binance":                                        # hâlâ dursun
            r = requests.get("https://fapi.binance.com/fapi/v1/exchangeInfo", timeout=5)
            r.raise_for_status()
            return [s["symbol"] for s in r.json()["symbols"]
                    if s.get("contractType") == "PERPETUAL"]

        elif exchange == "Bybit":                                       # hâlâ dursun
            r = requests.get("https://api.bybit.com/v5/market/instruments-info",
                             params={"category": "linear"}, timeout=5)
            r.raise_for_status()
            return [i["symbol"] for i in r.json()["result"]["list"]
                    if i.get("status") == "Trading"]

        elif exchange == "OKX":
            r = requests.get("https://www.okx.com/api/v5/public/instruments",
                             params={"instType": "SWAP"}, timeout=5)
            r.raise_for_status()
            return [i["instId"] for i in r.json()["data"]
                    if i["settleCcy"] == "USDT"]

        elif exchange == "Bitget":
            r = requests.get("https://api.bitget.com/api/v2/mix/market/contracts",
                             params={"productType": "usdt-futures"}, timeout=5)
            r.raise_for_status()
            return [i["symbol"] for i in r.json()["data"]
                    if i.get("status") == "normal"]

        elif exchange in ("HTX", "Huobi"):
            r = requests.get("https://api.hbdm.com/linear-swap-api/v1/swap_contract_info",
                             params={"contract_type": "swap"}, timeout=5)
            r.raise_for_status()
            return [i["contract_code"].upper() for i in r.json()["data"]]

        elif exchange == "KuCoin":
            r = requests.get("https://api.kucoin.com/api/v1/contracts/active", timeout=5)
            r.raise_for_status()
            return [i["symbol"] for i in r.json()["data"]
                    if i["type"] == "PERPETUAL" and i["quoteCurrency"] == "USDT"]

        else:
            return []

    except Exception as e:
        print(f"[WARN] Symbol fetch failed for {exchange}: {e}")
        return []

# ─── LEFT PANEL WIDGETS ───────────────────────────────────────────
price_pane  = pn.pane.Markdown("**0.00**", styles={"font-size":"24pt","text-align":"center"})
close_pane  = pn.pane.Markdown("*Kapanış ?*", styles={"font-size":"16pt","text-align":"center"})
delta_pane  = pn.pane.Markdown("", styles={"font-size":"14pt","text-align":"center"})

exch_dd  = pn.widgets.Select(name="Exchange",
             options=["Binance","Bybit","OKX", "Bitget", "HTX", "KuCoin"], value="Binance", width=150)
sym_dd   = pn.widgets.Select(name="Symbol",
             options=fetch_symbols("Binance"), value="BTCUSDT", width=150)
analyze_btn = pn.widgets.Button(name="Analiz Yap",
                button_type="success", width=150)

# ─── PRICE UPDATER ────────────────────────────────────────────────
UTC_OFFSET = 3 * 3600  # +03:00

def _update_prices():
    if not TICKS:
        return

    live = TICKS[-1][1]

    # 1) Günlük kapanışı UTC+3 00:00 mumundan al, yoksa live
    try:
        daily = next(
            c[4] for c in CANDLES["1m"]
            if time.gmtime(c[0] + UTC_OFFSET).tm_hour == 0
               and time.gmtime(c[0] + UTC_OFFSET).tm_min == 0
        )
    except StopIteration:
        daily = live

    # 2) Dinamik ondalık hassasiyet
    def fmt(v):
        if   v >= 1      : return f"{v:,.2f}"
        elif v >= 0.01   : return f"{v:,.4f}"
        elif v >= 0.0001 : return f"{v:,.6f}"
        else              : return f"{v:.8f}"

    price_pane.object = f"**{fmt(live)}**"
    close_pane.object = f"*Kapanış {fmt(daily)}*"

    # 3) Yüzde değişim
    pct   = (live - daily) / daily * 100 if daily else 0
    color = "#29cf82" if pct >= 0 else "#ef5350"
    sign  = "+" if pct >= 0 else ""
    delta_pane.object = f"<span style='color:{color}'>{sign}{pct:,.2f}%</span>"

pn.state.add_periodic_callback(_update_prices, 200)

# ─── PANEL YÜKLEYİCİ ─────────────────────────────────────────────
def load_panel(name: str):
    if name == "Chart":
        return chart_view.panel()
    module_name = name.lower().replace(" ", "")
    try:
        mod = importlib.import_module(f"views.{module_name}")
        return mod.panel()
    except ModuleNotFoundError:
        return pn.pane.Markdown(f"**{name} view is not available.**", styles={"color":"red"})

MENU = [
    "Chart","Order Book","Heatmap","Order Flow",
    "Liquidations","Open Interest","Funding rate",
    "Crypto Coins Heatmap","Stock Heatmap Widget"
]
tabs = pn.Tabs(*( (n, load_panel(n)) for n in MENU ), active=0, sizing_mode="stretch_both")

# ─── CALLBACKS ─────────────────────────────────────────────────────
def _refresh():
    restart_stream(exch_dd.value, sym_dd.value)
    update_header(sym_dd.value)
    if hasattr(chart_view, "update_chart"):
        chart_view.update_chart(exch_dd.value, sym_dd.value)

def _on_exchange(evt):
    new_opts = fetch_symbols(evt.new)
    sym_dd.options = new_opts
    if new_opts:
        sym_dd.value = new_opts[0]
    _refresh()

exch_dd.param.watch(_on_exchange, "value")
sym_dd.param.watch(lambda e: _refresh(), "value")

# ─── LAYOUT & SERVE ───────────────────────────────────────────────
left_panel = pn.Column(
    price_pane, close_pane, delta_pane,
    exch_dd, sym_dd,
    pn.Spacer(height=10), analyze_btn,
    width=200
)

layout = pn.Column(
    ticker_pane,
    header_row,
    pn.Row(left_panel, tabs, market_overview_pane, sizing_mode="stretch_width")
)

layout.servable(title="Kripto Analiz Tahtası")

# ─── İLK ÇAĞRI ────────────────────────────────────────────────────
_refresh()
