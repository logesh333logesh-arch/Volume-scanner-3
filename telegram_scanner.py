"""
COMBINED VOLUME + PRICE SPIKE SCANNER — Telegram Alerts
============================================================
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
INTERVAL = "15m"
PERIOD = "1mo"
AVG_WINDOW = 20
Z_THRESHOLD = 2.0
PRICE_THRESHOLD = 1.0

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
        return None, None

    if df.empty:
        print(f"{name} ({symbol}): No data returned")
        return None, None

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    if "Volume" not in df.columns or "Close" not in df.columns:
        print(f"{name} ({symbol}): Missing Volume/Close columns")
        return None, None

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
        return None, None

    latest = df.iloc[-1]
    latest_time = df.index[-1].strftime("%H:%M")
    rvol = float(latest["RVOL"])
    zscore = float(latest["Volume_Zscore"])
    pct_change = float(latest["Pct_Change"]) if not pd.isna(latest["Pct_Change"]) else 0.0
    price = float(latest["Close"])

    debug_row = f"{name:14s} {latest_time} | RVOL={rvol:4.2f}x | Z={zscore:+4.2f}σ | Chg={pct_change:+5.2f}%"
    print(debug_row)

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

    alert_msg = None
    if tags:
        alert_msg = f"🔥 <b>{name}</b>\n{' | '.join(tags)}\nCandle: {latest_time} IST | Price: {price:,.2f}"

    return alert_msg, (name, latest_time, rvol, zscore, pct_change)


if __name__ == "__main__":
    print(f"=== Scan Started: {datetime.now(IST).strftime('%d-%b-%Y %H:%M:%S IST')} ===")
    alerts = []
    debug_rows = []
    for name, symbol in MARKET_TICKERS.items():
        alert_msg, dbg = analyze(name, symbol)
        if alert_msg:
            alerts.append(alert_msg)
        if dbg:
            debug_rows.append(dbg)

    now = datetime.now(IST).strftime("%d-%b %H:%M IST")
    event_name = os.environ.get("GITHUB_EVENT_NAME", "manual")

    if alerts:
        message = f"🚨 <b>Spike Alert</b> ({now})\n\n" + "\n\n".join(alerts)
        send_telegram(message)
        print(f"\n{len(alerts)} Alert(s) sent")
    elif event_name == "workflow_dispatch":
        # Manual run: top-5 RVOL debug snapshot Telegram-க்கு அனுப்பும்
        debug_rows.sort(key=lambda r: r[3], reverse=True)
        top5 = debug_rows[:5]
        lines = [f"{n} ({t} IST): RVOL {r:.2f}x | Z {z:+.2f}σ | {p:+.2f}%" for n, t, r, z, p in top5]
        debug_msg = f"✅ Scanner Connect ஆயிருக்கு! ({now})\nஇப்போ Spike இல்ல. Top RVOL:\n\n" + "\n".join(lines)
        send_telegram(debug_msg)
        print("\nTest/debug message sent")
    else:
        print(f"\nNo spikes at {now}")

    print("=== Scan Complete ===")
