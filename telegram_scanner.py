"""
TELEGRAM VOLUME SPIKE ALERT
=============================
GitHub Actions மூலமா ஒவ்வொரு 15 நிமிடமும் தானாகவே run ஆகும்.
Spike இருந்தா Telegram-க்கு message அனுப்பும் — App திறக்கவே வேண்டாம்.
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
# SETTINGS — வேணும்னா இங்க மாத்திக்கலாம்
# -----------------------------------------------------------
INTERVAL = "60m"       # yfinance-க்கு 1 hour = "60m"
PERIOD = "1mo"
AVG_WINDOW = 20
SPIKE_THRESHOLD = 2.0  # 2x = சராசரியை விட 2 மடங்கு

MARKET_TICKERS = {
    "NIFTY 50":            "^NSEI",
    "BANK NIFTY":          "^NSEBANK",
    "SENSEX":              "^BSESN",
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

# -----------------------------------------------------------
# உன் Stocks — இங்க max 20 stocks type பண்ணு (.NS தானா சேர்க்கும்)
# -----------------------------------------------------------
CUSTOM_STOCKS = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]
for sym in CUSTOM_STOCKS:
    MARKET_TICKERS[sym] = sym if "." in sym else sym + ".NS"


def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"})


def check_spikes():
    spikes = []
    for name, symbol in MARKET_TICKERS.items():
        try:
            df = yf.download(symbol, period=PERIOD, interval=INTERVAL,
                              progress=False, auto_adjust=True)
            if df.empty:
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            if "Volume" not in df.columns:
                continue
            if df.index.tz is None:
                df.index = df.index.tz_localize("UTC").tz_convert(IST)
            else:
                df.index = df.index.tz_convert(IST)
            df["Avg_Volume"] = df["Volume"].rolling(window=AVG_WINDOW).mean()
            df["RVOL"] = df["Volume"] / df["Avg_Volume"]
            df.dropna(inplace=True)
            if df.empty:
                continue
            latest = df.iloc[-1]
            rvol = float(latest["RVOL"])
            price = float(latest["Close"])
            if rvol >= SPIKE_THRESHOLD:
                spikes.append(f"🔥 <b>{name}</b> — RVOL {rvol:.2f}x | Price {price:,.2f}")
        except Exception as e:
            print(f"{name} skip: {e}")
            continue
    return spikes


if __name__ == "__main__":
    spikes = check_spikes()
    if spikes:
        now = datetime.now(IST).strftime("%d-%b %H:%M IST")
        message = f"📊 <b>Volume Spike Alert</b> ({now})\n\n" + "\n".join(spikes)
        send_telegram(message)
        print("Alert sent:", spikes)
    else:
        print("No spikes found at", datetime.now(IST).strftime("%H:%M IST"))
