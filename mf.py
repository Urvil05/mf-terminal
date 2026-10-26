import streamlit as st
import pandas as pd
import numpy as np
import requests
import json
import os
from datetime import datetime, timedelta

st.set_page_config(page_title="APEX MF | Institutional Terminal", page_icon="⚡", layout="wide")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;800&family=JetBrains+Mono:wght@400;700&display=swap');
    html, body, [class*="css"] { font-family: 'Plus Jakarta Sans', sans-serif; }
    .stApp { background: radial-gradient(circle at top right, #0f172a 0%, #030712 100%); color: #f8fafc; }
    div[data-testid="stDataFrame"] { border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 12px; overflow: hidden; }
</style>
""", unsafe_allow_html=True)

WATCHLIST_FILE = "tracked_funds.json"
DEFAULT_WATCHLIST = [] # Add your final codes here later

def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, "r") as f: return json.load(f)
        except: pass
    return DEFAULT_WATCHLIST

def save_watchlist(data):
    with open(WATCHLIST_FILE, "w") as f: json.dump(data, f)

if "watchlist" not in st.session_state:
    st.session_state["watchlist"] = load_watchlist()

# --- AMFI DATA FETCHERS ---
@st.cache_data(ttl=86400, show_spinner=False)
def get_all_schemes():
    try:
        res = requests.get("https://api.mfapi.in/mf", timeout=10)
        df = pd.DataFrame(res.json())
        df["search_term"] = df["schemeName"].str.lower()
        return df
    except:
        return pd.DataFrame()

@st.cache_data(ttl=3600, show_spinner=False)
def calculate_fund_metrics(code):
    try:
        res = requests.get(f"https://api.mfapi.in/mf/{code}", timeout=10).json()
        if "meta" not in res or "data" not in res or len(res["data"]) == 0: return None
        
        name = res["meta"]["scheme_name"]
        category = res["meta"]["scheme_category"]
        
        # Smart Benchmark Assignment
        cat_low = str(category).lower()
        if "large" in cat_low: bench = "NIFTY 100 TRI"
        elif "mid" in cat_low: bench = "NIFTY Midcap 150 TRI"
        elif "small" in cat_low: bench = "NIFTY Smallcap 250 TRI"
        elif "flexi" in cat_low or "multi" in cat_low: bench = "NIFTY 500 TRI"
        elif "elss" in cat_low: bench = "NIFTY 500 TRI"
        elif "index" in cat_low: bench = "NIFTY 50 TRI"
        elif "debt" in cat_low or "liquid" in cat_low: bench = "NIFTY Liquid Index"
        else: bench = "NIFTY 500 TRI" # Fallback
        
        # DataFrame Processing
        df = pd.DataFrame(res["data"])
        df['date'] = pd.to_datetime(df['date'], format='%d-%m-%Y')
        df['nav'] = df['nav'].astype(float)
        df = df.sort_values('date').reset_index(drop=True)
        
        latest_nav = df.iloc[-1]['nav']
        latest_date = df.iloc[-1]['date']
        
        def get_past_nav(days):
            target_date = latest_date - timedelta(days=days)
            past_df = df[df['date'] <= target_date]
            return past_df.iloc[-1]['nav'] if not past_df.empty else None

        nav_1m = get_past_nav(30)
        nav_1y = get_past_nav(365)
        nav_3y = get_past_nav(1095)
        
        ret_1m = round(((latest_nav / nav_1m) - 1) * 100, 2) if nav_1m else None
        ret_1y = round(((latest_nav / nav_1y) - 1) * 100, 2) if nav_1y else None
        cagr_3y = round((((latest_nav / nav_3y) ** (1/3)) - 1) * 100, 2) if nav_3y else None
        
        # Risk Ratios (3 Year Window)
        risk_df = df[df['date'] >= latest_date - timedelta(days=1095)].copy()
        sharpe, sortino = None, None
        
        if len(risk_df) > 200:
            risk_df['ret'] = risk_df['nav'].pct_change()
            returns = risk_df['ret'].dropna()
            
            mean_annual_ret = returns.mean() * 252
            std_dev_annual = returns.std() * np.sqrt(252)
            rf = 0.065 # 6.5% Risk Free Rate
            
            if std_dev_annual > 0:
                sharpe = round((mean_annual_ret - rf) / std_dev_annual, 2)
                
            downside_ret = returns[returns < 0]
            if len(downside_ret) > 0:
                downside_std_annual = downside_ret.std() * np.sqrt(252)
                if downside_std_annual > 0:
                    sortino = round((mean_annual_ret - rf) / downside_std_annual, 2)
                    
        return {
            "Code": code,
            "Fund Name": name,
            "Category": category,
            "Benchmark": bench,
            "1-Month (%)": ret_1m,
            "1-Year (%)": ret_1y,
            "3-Year CAGR (%)": cagr_3y,
            "Sharpe Ratio": sharpe,
            "Sortino Ratio": sortino
        }
    except Exception as e:
        return None

all_schemes = get_all_schemes()

# --- SIDEBAR (ADD & DELETE) ---
st.sidebar.markdown("### 🔍 Add New Fund")
query = st.sidebar.text_input("Search Fund (e.g. Axis Bluechip):")

if query and not all_schemes.empty:
    matches = all_schemes[all_schemes["search_term"].str.contains(query.lower(), na=False)].head(20)
    if not matches.empty:
        sel_fund = st.sidebar.selectbox("Select matching fund:", matches["schemeName"].tolist())
        if st.sidebar.button("➕ Add to Watchlist"):
            code = int(matches[matches["schemeName"] == sel_fund]["schemeCode"].iloc[0])
            if code not in st.session_state["watchlist"]:
                st.session_state["watchlist"].append(code)
                save_watchlist(st.session_state["watchlist"])
                st.sidebar.success("Fund Added!")
                st.rerun()
    else:
        st.sidebar.warning("No match found.")

st.sidebar.markdown("---")
st.sidebar.markdown("### ❌ Delete Existing Fund")
if st.session_state["watchlist"]:
    # Quick fetch just for names to populate delete dropdown
    delete_dict = {}
    for c in st.session_state["watchlist"]:
        # Getting basic name safely
        try:
            n = requests.get(f"https://api.mfapi.in/mf/{c}", timeout=3).json().get("meta", {}).get("scheme_name", str(c))
            delete_dict[n] = c
        except:
            delete_dict[str(c)] = c

    fund_to_delete = st.sidebar.selectbox("Select fund to remove:", list(delete_dict.keys()))
    if st.sidebar.button("🗑️ Remove Fund"):
        st.session_state["watchlist"].remove(delete_dict[fund_to_delete])
        save_watchlist(st.session_state["watchlist"])
        st.sidebar.success("Fund Removed!")
        st.rerun()

# --- MAIN UI ---
st.markdown("<h1 style='font-weight: 800; font-size: 2.2rem; color: #38bdf8;'>APEX QUANTITATIVE TERMINAL</h1>", unsafe_allow_html=True)
tab1, tab2, tab3 = st.tabs(["📊 Quant Dashboard", "💾 Make Watchlist Permanent", "🏢 Factsheet Parser"])

with tab1:
    if st.session_state["watchlist"]:
        st.write(f"**Tracking {len(st.session_state['watchlist'])} Funds** | *Live data fetching directly from AMFI API...*")
        
        with st.spinner("Calculating 1Y/3Y Returns, Sharpe & Sortino Ratios..."):
            metrics_list = []
            for code in st.session_state["watchlist"]:
                data = calculate_fund_metrics(code)
                if data:
                    metrics_list.append(data)
            
            if metrics_list:
                df_display = pd.DataFrame(metrics_list).drop(columns=["Code"])
                st.dataframe(df_display, use_container_width=True, hide_index=True)
            else:
                st.error("Failed to load metrics.")
    else:
        st.info("Watchlist is empty. Add funds from the sidebar on the left.")

with tab2:
    st.markdown("### 🔒 Lock Your Funds Permanently")
    st.write("Streamlit cloud resets every few days. Jab aapki final watchlist tayyar ho jaye, niche diye code ko `DEFAULT_WATCHLIST` me paste kar lena:")
    st.code(f"DEFAULT_WATCHLIST = {st.session_state['watchlist']}", language="python")

with tab3:
    st.markdown("### 📥 Factsheet Engine")
    st.write("*(Watchlist ready hone ke baad yahan Excel upload engine aayega)*")
