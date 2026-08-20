"""
COMBINED VOLUME + PRICE SPIKE SCANNER — Telegram Alerts
============================================================
Ovvoru Run-லயும் ovvoru Instrument-ஓட RVOL & Price Change-ஐ Print பண்ணும்
(Debug பண்ண Easy-ஆ இருக்க). Volume Spike ஆனாலும், Price Spike ஆனாலும்
Telegram-க்கு Alert அனுப்பும்.
"""

import os
import requests
import yfinance as yf
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# -----------------------------------------------------------
# SETTINGS
# -----------------------------------------------------------
INTERVAL = "15m"          # yfinance-க்கு 15 minutes = "15m"  (60m-ல இருந்து மாத்தப்பட்டது — delay fix)
PERIOD = "1mo"             # 15m data-க்கு yfinance max 60 days தரும், 1mo (30 days) அதுக்குள்ள வரும்
AVG_WINDOW = 20
Z_THRESHOLD = 2.0         # Volume, Average-ல இருந்து 2 Standard Deviations மேல போனா = Spike
PRICE_THRESHOLD = 1.0     # 1 Candle-ல் 1%-க்கு மேல Move = Price Spike

MARKET_TICKERS = {
    "NIFTY 50":            "NIFTYBEES.NS",   # Raw ^NSEI-க்கு Volume Data இல்ல, ETF Proxy
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

# உன் Stocks — இங்க Max 20 Stocks Type பண்ணு (.NS தானா சேர்க்கும்)
CUSTOM_STOCKS = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]
for sym in CUSTOM_STOCKS:
    MARKET_TICKERS[sym] = sym if "." in sym else sym + ".NS"


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
    df["Volume_Zscore"] = (df["Volume"] - df["Avg_Volume"]) / df["Std_Volume"].replace(0, pd.NA)
    df["Pct_Change"] = df["Close"].pct_change() * 100
    df.dropna(subset=["RVOL", "Volume_Zscore"], inplace=True)

    if df.empty:
        print(f"{name} ({symbol}): Not enough history for {AVG_WINDOW}-bar average yet")
        return None

    latest = df.iloc[-1]
    rvol = float(latest["RVOL"])
    zscore = float(latest["Volume_Zscore"])
    pct_change = float(latest["Pct_Change"]) if not pd.isna(latest["Pct_Change"]) else 0.0
    price = float(latest["Close"])

    # Debug Log — ஒவ்வொரு Instrument-க்கும் Exact Value இதுல தெரியும்
    print(f"{name:22s} | RVOL={rvol:5.2f}x | Z-score={zscore:+5.2f}σ | Price%={pct_change:+6.2f}% | Price={price:,.2f}")

    tags = []
    if zscore >= Z_THRESHOLD:
        if pct_change > 0.05:
            vol_direction = "🟢 Bullish"
        elif pct_change < -0.05:
            vol_direction = "🔴 Bearish"
        else:
            vol_direction = "⚪ Neutral"
        tags.append(f"📊 {vol_direction} Volume Spike (RVOL {rvol:.2f}x, Unusual by {zscore:.1f}σ)")
    if abs(pct_change) >= PRICE_THRESHOLD:
        direction = "📈" if pct_change > 0 else "📉"
        tags.append(f"{direction} Price Spike ({pct_change:+.2f}%)")

    if tags:
        return f"🔥 <b>{name}</b>\n{' | '.join(tags)}\nPrice: {price:,.2f}"
    return None


if __name__ == "__main__":
    print(f"=== Scan Started: {datetime.now(IST).strftime('%d-%b-%Y %H:%M:%S IST')} ===")
    alerts = []
    for name, symbol in MARKET_TICKERS.items():
        result = analyze(name, symbol)
        if result:
            alerts.append(result)

    now = datetime.now(IST).strftime("%d-%b %H:%M IST")
    event_name = os.environ.get("GITHUB_EVENT_NAME", "manual")

    if alerts:
        message = f"🚨 <b>Spike Alert</b> ({now})\n\n" + "\n\n".join(alerts)
        send_telegram(message)
        print(f"\n{len(alerts)} Alert(s) sent")
    elif event_name == "workflow_dispatch":
        send_telegram(f"✅ Test message — Scanner சரியா Connect ஆயிருக்கு! ({now})\nஇப்போ Volume/Price Spike எதுவும் இல்ல.")
        print("\nTest message sent (manual run, no spikes right now)")
    else:
        print(f"\nNo spikes at {now}")

    print("=== Scan Complete ===")
