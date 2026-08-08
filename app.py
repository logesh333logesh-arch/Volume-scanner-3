"""
MULTI-MARKET VOLUME SPIKE SCANNER — Streamlit Web App
========================================================
Nifty, BankNifty, Sensex, FinNifty, US Index, Bitcoin, ETH, SOL,
Gold, Silver, Crude Oil, Natural Gas + உன் own 20 Stocks வரைக்கும்.

NOTE: MCX-ஓட exact Gold/Silver/Crude/Natural Gas price Yahoo Finance-ல
கிடைக்கல, அதனால international (Comex/Nymex) price காட்டுது —
trend/movement almost ஒரே மாதிரி தான் இருக்கும்.

LOCAL-ல RUN பண்ண:
    pip install streamlit yfinance pandas plotly
    streamlit run app.py
"""

import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
from zoneinfo import ZoneInfo
import time

IST = ZoneInfo("Asia/Kolkata")

# -----------------------------------------------------------
# PAGE CONFIG
# -----------------------------------------------------------
st.set_page_config(
    page_title="Volume Spike Scanner",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Multi-Market Volume Spike Scanner")
st.caption("Index + Crypto + Commodity + உன் Stocks — RVOL based spike detection")

# -----------------------------------------------------------
# SIDEBAR SETTINGS
# -----------------------------------------------------------
st.sidebar.header("⚙️ Settings")

INTERVAL = st.sidebar.selectbox(
    "Candle Interval", ["15m", "30m", "1h", "1d"], index=2
)
AVG_WINDOW = st.sidebar.slider("Average Volume Window (bars)", 5, 50, 20)
SPIKE_THRESHOLD = st.sidebar.slider("Spike Threshold (x times avg)", 1.5, 5.0, 2.0, 0.1)
LOOKBACK_PERIOD = st.sidebar.selectbox(
    "Lookback Period", ["5d", "1mo", "3mo"], index=1
)
auto_refresh = st.sidebar.checkbox("Auto-refresh every 5 min", value=False)

if st.sidebar.button("🗑️ Clear Cache & Force Refresh"):
    st.cache_data.clear()
    st.sidebar.success("Cache clear ஆச்சு! இப்போ Scan Now அழுத்து.")

# -----------------------------------------------------------
# FIXED MARKET LIST — நீ கேட்டது
# -----------------------------------------------------------
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

st.sidebar.subheader("📍 Markets")
selected_markets = st.sidebar.multiselect(
    "Track பண்ண வேண்டியது",
    list(MARKET_TICKERS.keys()),
    default=list(MARKET_TICKERS.keys())
)

# -----------------------------------------------------------
# CUSTOM STOCKS — உன் own 20 stocks add பண்ண option
# -----------------------------------------------------------
st.sidebar.subheader("📌 உன் Stocks (max 20)")
custom_input = st.sidebar.text_area(
    "NSE Stock symbols, comma-ல பிரி",
    placeholder="RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK",
    height=100
)

def parse_custom_stocks(text):
    if not text.strip():
        return {}
    raw = [s.strip().upper() for s in text.replace("\n", ",").split(",") if s.strip()]
    raw = raw[:20]
    tickers = {}
    for sym in raw:
        clean_symbol = sym if "." in sym else sym + ".NS"
        tickers[sym] = clean_symbol
    return tickers

custom_tickers = parse_custom_stocks(custom_input)

# -----------------------------------------------------------
# CORE FUNCTIONS
# -----------------------------------------------------------
@st.cache_data(ttl=300)
def fetch_volume_data(symbol, period, interval, avg_window):
    df = yf.download(symbol, period=period, interval=interval,
                      progress=False, auto_adjust=True)
    if df.empty:
        return None
    # புது yfinance versions சில நேரம் multi-level columns கொடுக்கும் — flatten பண்றது
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if "Volume" not in df.columns:
        return None
    # Yahoo data-ஐ IST-க்கு convert பண்றது — இல்லனா "Last Update" தப்பா காட்டும்
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(IST)
    else:
        df.index = df.index.tz_convert(IST)
    df["Avg_Volume"] = df["Volume"].rolling(window=avg_window).mean()
    df["RVOL"] = df["Volume"] / df["Avg_Volume"]
    df.dropna(inplace=True)
    return df

def scan_markets(tickers_dict, period, interval, avg_window, threshold):
    rows = []
    charts = {}
    for name, symbol in tickers_dict.items():
        df = fetch_volume_data(symbol, period, interval, avg_window)
        if df is None or df.empty:
            continue
        latest = df.iloc[-1]
        rvol = round(float(latest["RVOL"]), 2)
        price = round(float(latest["Close"]), 2)
        age_min = round((datetime.now(IST) - df.index[-1]).total_seconds() / 60)
        rows.append({
            "Name": name,
            "Symbol": symbol,
            "Price": price,
            "RVOL": rvol,
            "Status": "🔥 SPIKE" if rvol >= threshold else "Normal",
            "Last Update": df.index[-1].strftime("%d-%b %H:%M IST"),
            "Data Age": f"{age_min} நிமிடம் முன்பு" if age_min < 1440 else f"{age_min // 1440} நாள் முன்பு",
        })
        charts[name] = df
    return pd.DataFrame(rows), charts

def show_results(df, title):
    if df.empty:
        return
    df = df.sort_values(by="RVOL", ascending=False)
    spikes = df[df["Status"] == "🔥 SPIKE"]
    st.subheader(title)
    if not spikes.empty:
        st.success(f"🔥 {len(spikes)} spike ஆகியிருக்கு: {', '.join(spikes['Name'])}")
    st.dataframe(df, use_container_width=True, hide_index=True)

# -----------------------------------------------------------
# RUN SCAN
# -----------------------------------------------------------
if st.button("🔍 Scan Now") or auto_refresh:
    with st.spinner("Markets scan பண்றோம்..."):
        subset = {k: MARKET_TICKERS[k] for k in selected_markets}
        market_df, market_charts = scan_markets(
            subset, LOOKBACK_PERIOD, INTERVAL, AVG_WINDOW, SPIKE_THRESHOLD
        )
        if custom_tickers:
            stock_df, stock_charts = scan_markets(
                custom_tickers, LOOKBACK_PERIOD, INTERVAL, AVG_WINDOW, SPIKE_THRESHOLD
            )
        else:
            stock_df, stock_charts = pd.DataFrame(), {}

    if market_df.empty and stock_df.empty:
        st.warning("Data கிடைக்கல, தயவுசெய்து ticker அல்லது interval மாத்தி try பண்ணுங்க.")
    else:
        show_results(market_df, "📋 Market Scan Results")

        if custom_tickers:
            if stock_df.empty:
                st.warning("உன் stocks-க்கு data கிடைக்கல — symbol spelling check பண்ணு (எ.கா: RELIANCE, TCS).")
            else:
                show_results(stock_df, "📌 My Stocks — Volume Scan")

        all_charts = {**market_charts, **stock_charts}
        if all_charts:
            st.subheader("📈 Volume Chart")
            chart_name = st.selectbox("Chart பார்க்க தேர்ந்தெடு", list(all_charts.keys()))
            if chart_name:
                df_chart = all_charts[chart_name]
                fig = go.Figure()
                fig.add_trace(go.Bar(x=df_chart.index, y=df_chart["Volume"], name="Volume"))
                fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart["Avg_Volume"],
                                          name="Avg Volume", line=dict(color="orange")))
                fig.update_layout(title=f"{chart_name} — Volume vs Average",
                                   height=400, template="plotly_dark")
                st.plotly_chart(fig, use_container_width=True)

        st.caption(f"கடைசியா Scan ஆனது: {datetime.now().strftime('%d-%b-%Y %H:%M:%S')}")

if auto_refresh:
    time.sleep(300)
    st.rerun()
