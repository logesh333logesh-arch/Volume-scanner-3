"""
COMBINED VOLUME + PRICE SPIKE SCANNER — Telegram Alerts (v3)
================================================================
V3 Changes:
1. Trend Filter — Price 50-Bar Moving Average-க்கு மேலயா/கீழயா இருக்கு
   பாத்து, அந்த Trend-கூட Match ஆகுற Spike மட்டும் Alert பண்ணும்
   (Counter-Trend Noise Filter Out ஆகும்)
2. Duplicate Fix — ஒரே Candle-க்கு ஒரே தடவை மட்டும் Alert, Repeated
   Spam நிக்கும் (alert_state.json-ல Track பண்ணும்)
"""

import os
import json
import requests
import yfinance as yf
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
STATE_FILE = "alert_state.json"

# -----------------------------------------------------------
# SETTINGS
# -----------------------------------------------------------
INTERVAL = "60m"
PERIOD = "1mo"
AVG_WINDOW = 20
TREND_WINDOW = 50         # Trend Decide பண்ண இத்தனை Bars-ஓட Average Use பண்றோம்
Z_THRESHOLD = 2.0
PRICE_THRESHOLD = 1.0
MOVE_MIN = 0.05            # இதுக்கு கீழ Move-ஐ "Flat/No Direction"-ஆ Consider பண்றோம்

MARKET_TICKERS = {
    "NIFTY 50":            "NIFTYBEES.NS",
    "BANK NIFTY":          "BANKBEES.NS",
    "SENSEX":              "SENSEXETF.NS",
    "FIN NIFTY":           "NIFTY_FIN_SERVICE.NS",
    "US INDEX (S&P 500)":  "^GSPC",
    "BITCOIN":             "BTC-USD",
    "ETHEREUM":            "ETH-USD",
    "SOLANA":              "SOL-USD",
    "GOLD":                "GC=F",
    "SILVER":              "SI=F",
    "CRUDE OIL":           "CL=F",
    "NATURAL GAS":         "NG=F",
}
CUSTOM_STOCKS = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]
for sym in CUSTOM_STOCKS:
    MARKET_TICKERS[sym] = sym if "." in sym else sym + ".NS"


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    resp = requests.post(url, data={"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"})
    if not resp.ok:
        print("‼️ Telegram send FAILED:", resp.status_code, resp.text)
    else:
        print("✅ Telegram send OK")


def analyze(name, symbol):
    try:
        df = yf.download(symbol, period=PERIOD, interval=INTERVAL, progress=False, auto_adjust=True)
    except Exception as e:
        print(f"{name} ({symbol}): DOWNLOAD ERROR — {e}")
        return None

    if df.empty:
        print(f"{name} ({symbol}): No data returned")
        return None

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if "Volume" not in df.columns or "Close" not in df.columns:
        print(f"{name} ({symbol}): Missing Volume/Close columns")
        return None

    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(IST)
    else:
        df.index = df.index.tz_convert(IST)

    df["Avg_Volume"] = df["Volume"].rolling(window=AVG_WINDOW).mean()
    df["Std_Volume"] = df["Volume"].rolling(window=AVG_WINDOW).std()
    df["RVOL"] = df["Volume"] / df["Avg_Volume"]
    df["Zscore"] = (df["Volume"] - df["Avg_Volume"]) / df["Std_Volume"].replace(0, pd.NA)
    df["Pct_Change"] = df["Close"].pct_change() * 100
    df["MA_Trend"] = df["Close"].rolling(window=TREND_WINDOW).mean()
    df.dropna(subset=["RVOL", "Zscore", "MA_Trend"], inplace=True)

    if df.empty:
        print(f"{name} ({symbol}): Not enough history yet ({TREND_WINDOW}-bar trend needs more data)")
        return None

    latest = df.iloc[-1]
    rvol = float(latest["RVOL"])
    zscore = float(latest["Zscore"])
    pct_change = float(latest["Pct_Change"]) if not pd.isna(latest["Pct_Change"]) else 0.0
    price = float(latest["Close"])
    trend_ma = float(latest["MA_Trend"])
    trend = "up" if price > trend_ma else "down"
    candle_time = df.index[-1].isoformat()

    print(f"{name:22s} | RVOL={rvol:5.2f}x | Z={zscore:+5.2f}σ | Price%={pct_change:+6.2f}% | "
          f"Trend={trend.upper():4s} | Price={price:,.2f}")

    move_direction = "up" if pct_change > MOVE_MIN else ("down" if pct_change < -MOVE_MIN else None)
    trend_aligned = (move_direction == trend)

    tags = []
    if zscore >= Z_THRESHOLD and trend_aligned:
        vol_emoji = "🟢" if trend == "up" else "🔴"
        vol_word = "Bullish" if trend == "up" else "Bearish"
        tags.append(f"📊 {vol_emoji} {vol_word} Volume Spike (RVOL {rvol:.2f}x, {zscore:.1f}σ) — Trend-Aligned")
    if abs(pct_change) >= PRICE_THRESHOLD and trend_aligned:
        direction_emoji = "📈" if trend == "up" else "📉"
        tags.append(f"{direction_emoji} Price Spike ({pct_change:+.2f}%) — Trend-Aligned")

    if not trend_aligned and (zscore >= Z_THRESHOLD or abs(pct_change) >= PRICE_THRESHOLD):
        print(f"   ↳ Skipped: Counter-Trend (Move={move_direction}, Trend={trend})")

    if tags:
        return {
            "message": f"🔥 <b>{name}</b>\n" + "\n".join(tags) +
                       f"\nCandle: {df.index[-1].strftime('%H:%M IST')} | Price: {price:,.2f}",
            "candle_time": candle_time,
        }
    return None


if __name__ == "__main__":
    print(f"=== Scan Started: {datetime.now(IST).strftime('%d-%b-%Y %H:%M:%S IST')} ===")
    state = load_state()
    state_changed = False
    alerts = []

    for name, symbol in MARKET_TICKERS.items():
        result = analyze(name, symbol)
        if result is None:
            continue
        if state.get(name) == result["candle_time"]:
            print(f"   ↳ Skipped: Already Alerted for this Candle")
            continue
        alerts.append(result["message"])
        state[name] = result["candle_time"]
        state_changed = True

    now = datetime.now(IST).strftime("%d-%b %H:%M IST")
    event_name = os.environ.get("GITHUB_EVENT_NAME", "manual")

    if alerts:
        message = f"🚨 <b>Spike Alert</b> ({now})\n\n" + "\n\n".join(alerts)
        send_telegram(message)
        print(f"\n{len(alerts)} Alert(s) sent")
    elif event_name == "workflow_dispatch":
        send_telegram(f"✅ Test message — Scanner சரியா Connect ஆயிருக்கு! ({now})\nஇப்போ Trend-Aligned Spike எதுவும் இல்ல.")
        print("\nTest message sent (manual run)")
    else:
        print(f"\nNo new trend-aligned spikes at {now}")

    if state_changed:
        save_state(state)
        print("State file updated")

    print("=== Scan Complete ===")
