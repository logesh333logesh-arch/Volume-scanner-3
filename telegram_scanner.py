"""
COMBINED VOLUME + PRICE SPIKE SCANNER — Telegram Alerts (v7)
================================================================
V7 Changes — 4-Symbol Legend (Tier + Direction ஒரே Emoji-ல):
    🔵 EARLY, Bullish (Buy)
    🟣 EARLY, Bearish (Sell)
    🟢 CONFIRMED, Bullish (Buy)
    🔴 CONFIRMED, Bearish (Sell)
ஒரே Emoji Paatha, Tier + Direction ரெண்டும் உடனே தெரியும் — தனியா
Text படிக்க வேண்டாம்.

--- Previous V6 Changes (Volume-Led Early Trigger) ---
User Feedback: SOLANA-ல 08:30 Candle-லேயே பெரிய Volume+Price Move
Start ஆனாலும், Alert 09:00 Candle-க்கு தான் வந்துச்சு — Move-ஓட
Climax/Final Burst-ல தான் Alert Fire ஆச்சு, Start-ல இல்ல.

Root Cause: EARLY Tier-க்கு Price Threshold 1.0% வெச்சிருந்தோம் —
15 நிமிஷத்துக்குள் Full 1% Move ஆகணும்-ன்னு High Bar. Volume Price-க்கு
முன்னாடி Lead எடுக்கும், ஆனா Price 1% Move ஆக நேரம் ஆகும், அதனால
Move-ஓட Later Stage-ல தான் Alert Trigger ஆகுது.

Fix: EARLY_PRICE_THRESHOLD 1.0% → 0.1% (Volume-Led) — Volume Z-Score
Spike-கூட ஒரு சின்ன Directional Move இருந்தாலே Early Alert Fire ஆகும்.
⚠️ இந்த Low Threshold Backtest பண்ணல் — Timeliness-க்காக Trade-Off
பண்றோம், Alert Frequency அதிகரிக்கும்.

--- Previous V5 Changes (Trend-Capture Speed மேம்படுத்த) ---
1. Interval 60m → 15m — Candle Size குறைச்சு, Detection Speed 4x
   வேகமா ஆகுது (Max Delay 60 நிமிஷத்துலருந்து 15 நிமிஷமா குறையுது)
2. Dual-Tier Alerts — ஒரே Signal-க்கு 2 Message வரும்:
   🟡 EARLY     — Spike Candle முடிஞ்சதுமே உடனே (No Confirm Wait)
   🟢 CONFIRMED — அடுத்த Candle Same Direction Continue ஆனா
   Early Alert Trend-ஐ வேகமா Catch பண்ண உதவும். Confirmed Alert
   High-Confidence Follow-Up-க்கு உதவும். ரெண்டையும் பாத்து நீயே
   Decide பண்ணலாம்.
3. AVG_WINDOW (20→80) மற்றும் TREND_WINDOW (50→200) — 15m Candle-க்கு
   ஏத்த மாதிரி 4x அதிகரிச்சிருக்கேன், இதனால முன்ன 60m-ல இருந்த அதே
   "20 Hour Volume Average" மற்றும் "50 Hour Trend" Lookback Meaning
   அப்படியே இருக்கும் (Time-Span Change ஆகாது, Resolution மட்டும்
   Fine-ஆகுது)

⚠️ IMPORTANT NOTE: PRICE_THRESHOLD (1.0%) 60m Candle-க்கு Backtest
பண்ணி வெச்சது. 15m Candle-ல 15 நிமிஷத்துக்குள் 1% Move அடைவது 60m-ஐ
விட கடினம் (Rarer) — இதை நான் மாத்தலை (Backtest Data இல்லாததால Guess
பண்ண விரும்பல). இதனால Alert இன்னும் குறையலாம்-ன்னு எதிர்பார்க்கலாம்.
சில வாரம் கழிச்சு Alert Frequency ரொம்ப குறைவா இருந்தா, இதை Backtest
பண்ணி Fine-Tune பண்ணலாம்.
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
INTERVAL = "15m"
PERIOD = "1mo"
AVG_WINDOW = 80          # 20 Hours Equivalent (80 x 15min = 20hr)
TREND_WINDOW = 200       # 50 Hours Equivalent (200 x 15min = 50hr)
Z_THRESHOLD = 2.0
EARLY_PRICE_THRESHOLD = 0.1   # Volume-Led — Full 1% Wait பண்ணாம, சின்ன Directional Move போதும்
MOVE_MIN = 0.05

# Backtest Data Base பண்ணி Direction Rule
TREND_INSTRUMENTS = {"GOLD", "SILVER", "NIFTY 50"}
CONTRARIAN_INSTRUMENTS = {"BITCOIN", "ETHEREUM"}

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
                data = json.load(f)
                data.setdefault("EARLY", {})
                data.setdefault("CONFIRMED", {})
                return data
        except Exception:
            pass
    return {"EARLY": {}, "CONFIRMED": {}}


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


def required_direction_rule(name):
    if name in TREND_INSTRUMENTS:
        return "trend"
    if name in CONTRARIAN_INSTRUMENTS:
        return "contrarian"
    return "trend"


def evaluate_row(row, name):
    rvol = float(row["RVOL"])
    zscore = float(row["Zscore"])
    pct = float(row["Pct_Change"]) if not pd.isna(row["Pct_Change"]) else 0.0
    price = float(row["Close"])
    trend = "up" if price > float(row["MA_Trend"]) else "down"
    direction = "up" if pct > MOVE_MIN else ("down" if pct < -MOVE_MIN else None)
    both = (zscore >= Z_THRESHOLD) and (abs(pct) >= EARLY_PRICE_THRESHOLD)
    rule = required_direction_rule(name)
    if direction is None:
        dir_ok = False
    elif rule == "trend":
        dir_ok = (direction == trend)
    else:
        dir_ok = (direction != trend)
    return {
        "rvol": rvol, "zscore": zscore, "pct": pct, "price": price,
        "trend": trend, "direction": direction, "both": both,
        "dir_ok": dir_ok, "rule": rule,
    }


def analyze(name, symbol, state):
    try:
        df = yf.download(symbol, period=PERIOD, interval=INTERVAL, progress=False, auto_adjust=True)
    except Exception as e:
        print(f"{name} ({symbol}): DOWNLOAD ERROR — {e}")
        return []

    if df.empty:
        print(f"{name} ({symbol}): No data returned")
        return []

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if "Volume" not in df.columns or "Close" not in df.columns:
        print(f"{name} ({symbol}): Missing Volume/Close columns")
        return []

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

    if len(df) < 3:
        print(f"{name} ({symbol}): Not enough history yet ({TREND_WINDOW}-bar trend needs more data)")
        return []

    C = df.iloc[-2]              # கடைசி Fully-Closed Candle
    P = df.iloc[-3]              # அதுக்கு முந்தைய Candle
    C_time = df.index[-2].isoformat()
    P_time = df.index[-3].isoformat()

    sig_C = evaluate_row(C, name)
    sig_P = evaluate_row(P, name)

    outputs = []

    # ---------- 🟡 EARLY ALERT — Spike Candle-லேயே உடனே ----------
    if sig_C["both"] and sig_C["dir_ok"] and state["EARLY"].get(name) != C_time:
        rule_label = "Trend-Aligned" if sig_C["rule"] == "trend" else "Contrarian"
        is_bull = sig_C["direction"] == "up"
        emoji = "🔵" if is_bull else "🟣"
        dir_word = "BUY (Bullish)" if is_bull else "SELL (Bearish)"
        msg = (
            f"{emoji} <b>{name}</b> — EARLY, {dir_word}\n"
            f"Volume+Price Spike (RVOL {sig_C['rvol']:.2f}x, {sig_C['zscore']:.1f}\u03c3, {sig_C['pct']:+.2f}%) — {rule_label}\n"
            f"Candle: {df.index[-2].strftime('%H:%M IST')} | Price: {sig_C['price']:,.2f}"
        )
        outputs.append(("EARLY", name, C_time, msg))

    # ---------- 🟢 CONFIRMED ALERT — முந்தைய Early Candle Continue ஆனா ----------
    was_early = state["EARLY"].get(name) == P_time
    not_confirmed_yet = state["CONFIRMED"].get(name) != P_time
    continues = (sig_P["direction"] is not None) and (sig_C["direction"] == sig_P["direction"])
    if was_early and not_confirmed_yet and continues:
        rule_label = "Trend-Aligned" if sig_P["rule"] == "trend" else "Contrarian"
        is_bull = sig_P["direction"] == "up"
        emoji = "🟢" if is_bull else "🔴"
        dir_word = "BUY (Bullish)" if is_bull else "SELL (Bearish)"
        msg = (
            f"{emoji} <b>{name}</b> — CONFIRMED, {dir_word}\n"
            f"Volume+Price Spike (RVOL {sig_P['rvol']:.2f}x, {sig_P['zscore']:.1f}\u03c3, {sig_P['pct']:+.2f}%) — {rule_label}, Confirmed\n"
            f"Spike: {df.index[-3].strftime('%H:%M IST')} | Confirmed: {df.index[-2].strftime('%H:%M IST')} | Price: {sig_P['price']:,.2f}"
        )
        outputs.append(("CONFIRMED", name, P_time, msg))

    print(f"{name:22s} | RVOL={sig_C['rvol']:5.2f}x | Z={sig_C['zscore']:+5.2f}\u03c3 | Price%={sig_C['pct']:+6.2f}% | "
          f"Trend={sig_C['trend'].upper():4s} | Rule={sig_C['rule'].upper():10s} | Both={sig_C['both']} | DirOK={sig_C['dir_ok']}")

    return outputs


if __name__ == "__main__":
    print(f"=== Scan Started: {datetime.now(IST).strftime('%d-%b-%Y %H:%M:%S IST')} ===")
    state = load_state()
    state_changed = False
    early_alerts = []
    confirmed_alerts = []

    for name, symbol in MARKET_TICKERS.items():
        results = analyze(name, symbol, state)
        for tier, iname, itime, msg in results:
            if tier == "EARLY":
                early_alerts.append(msg)
                state["EARLY"][iname] = itime
            else:
                confirmed_alerts.append(msg)
                state["CONFIRMED"][iname] = itime
            state_changed = True

    now = datetime.now(IST).strftime("%d-%b %H:%M IST")
    event_name = os.environ.get("GITHUB_EVENT_NAME", "manual")
    all_alerts = early_alerts + confirmed_alerts

    if all_alerts:
        message = f"🚨 <b>Spike Alert (v7)</b> ({now})\n\n" + "\n\n".join(all_alerts)
        send_telegram(message)
        print(f"\n{len(early_alerts)} Early + {len(confirmed_alerts)} Confirmed Alert(s) sent")
    elif event_name == "workflow_dispatch":
        send_telegram(f"✅ Test message — Scanner v7 (🔵🟣 Early / 🟢🔴 Confirmed) சரியா Connect ஆயிருக்கு! ({now})\nஇப்போ Spike எதுவும் இல்ல.")
        print("\nTest message sent (manual run)")
    else:
        print(f"\nNo new alerts at {now}")

    if state_changed:
        save_state(state)
        print("State file updated")

    print("=== Scan Complete ===")
   
