import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import requests
import json
import os
from datetime import datetime, timedelta

st.set_page_config(page_title="Mutual Fund Terminal", page_icon="⚡", layout="wide")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;800&family=JetBrains+Mono:wght@400;700&display=swap');
    html, body, [class*="css"] { font-family: 'Plus Jakarta Sans', sans-serif; }
    .stApp { background: radial-gradient(circle at top right, #0f172a 0%, #030712 100%); color: #f8fafc; }
    div[data-testid="stDataFrame"] { border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 12px; overflow: hidden; }
</style>
""", unsafe_allow_html=True)

WATCHLIST_FILE = "tracked_funds.json"
DEFAULT_WATCHLIST = [] 

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
        
        cat_low = str(category).lower()
        if "large" in cat_low: bench = "NIFTY 100 TRI"
        elif "mid" in cat_low: bench = "NIFTY Midcap 150 TRI"
        elif "small" in cat_low: bench = "NIFTY Smallcap 250 TRI"
        elif "flexi" in cat_low or "multi" in cat_low: bench = "NIFTY 500 TRI"
        elif "elss" in cat_low: bench = "NIFTY 500 TRI"
        elif "index" in cat_low: bench = "NIFTY INDIA DEFENCE TRI"
        elif "debt" in cat_low or "liquid" in cat_low: bench = "NIFTY Liquid Index"
        else: bench = "NIFTY 500 TRI" 
        
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
        
        risk_df = df[df['date'] >= latest_date - timedelta(days=1095)].copy()
        sharpe, sortino = None, None
        
        if len(risk_df) > 200:
            risk_df['ret'] = risk_df['nav'].pct_change()
            returns = risk_df['ret'].dropna()
            
            mean_annual_ret = returns.mean() * 252
            std_dev_annual = returns.std() * np.sqrt(252)
            rf = 0.065 
            
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

# --- SIDEBAR (ADD & FAST DELETE) ---
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
st.sidebar.markdown("### ❌ Fast Bulk Delete")
if st.session_state["watchlist"]:
    delete_dict = {}
    for c in st.session_state["watchlist"]:
        if not all_schemes.empty:
            match = all_schemes[all_schemes["schemeCode"] == c]
            if not match.empty:
                delete_dict[match["schemeName"].iloc[0]] = c
                continue
        delete_dict[str(c)] = c

    funds_to_delete = st.sidebar.multiselect("Select multiple funds to remove:", list(delete_dict.keys()))
    
    if st.sidebar.button("🗑️ Remove Selected Funds"):
        if funds_to_delete:
            for f in funds_to_delete:
                if delete_dict[f] in st.session_state["watchlist"]:
                    st.session_state["watchlist"].remove(delete_dict[f])
            save_watchlist(st.session_state["watchlist"])
            st.rerun()

    if st.sidebar.button("🚨 Clear Entire Watchlist"):
        st.session_state["watchlist"] = []
        save_watchlist([])
        st.rerun()

# --- MAIN UI ---
st.markdown("<h1 style='font-weight: 800; font-size: 2.2rem; color: #38bdf8;'>MUTUAL FUND TERMINAL</h1>", unsafe_allow_html=True)
tab1, tab2 = st.tabs(["📊 Quant Dashboard", "🏢 Factsheet Parser"])

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
    st.markdown("### 📥 Smart Factsheet Parser")
    st.caption("Pitching ke liye AMC ki official website se downloaded Monthly Portfolio (.xlsx / .csv) upload karein.")
    
    factsheet_file = st.file_uploader("Upload Official AMC Portfolio File", type=["xlsx", "xls", "csv"])
    
    if factsheet_file is not None:
        try:
            if factsheet_file.name.endswith(".csv"):
                raw_df = pd.read_csv(factsheet_file)
            else:
                raw_df = pd.read_excel(factsheet_file)
                
            st.success(f"File '{factsheet_file.name}' loaded successfully!")
            
            with st.expander("🔍 Inspect Raw Factsheet Data"):
                st.dataframe(raw_df.head(15), use_container_width=True)
            
            st.markdown("#### ⚙️ Map Columns for Accurate Pitch Data")
            col1, col2 = st.columns(2)
            company_col = col1.selectbox("Select 'Company Name' Column:", ["None"] + list(raw_df.columns))
            weight_col = col2.selectbox("Select 'Weight (%)' Column:", ["None"] + list(raw_df.columns))
            
            if company_col != "None" and weight_col != "None":
                clean_df = raw_df[[company_col, weight_col]].copy()
                clean_df[weight_col] = pd.to_numeric(clean_df[weight_col], errors='coerce')
                clean_df = clean_df.dropna(subset=[company_col, weight_col])
                clean_df = clean_df.sort_values(by=weight_col, ascending=False).head(10) 
                
                st.markdown("---")
                st.markdown("### 🎯 Verified Top 10 Holdings")
                
                h1, h2 = st.columns([3, 2])
                with h1:
                    st.dataframe(clean_df, use_container_width=True, hide_index=True)
                with h2:
                    fig_h = px.pie(
                        clean_df, 
                        values=weight_col, 
                        names=company_col, 
                        hole=0.55, 
                        color_discrete_sequence=px.colors.sequential.Electric
                    )
                    fig_h.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)", 
                        plot_bgcolor="rgba(0,0,0,0)", 
                        font=dict(color="#94a3b8"), 
                        margin=dict(t=10, b=10, l=10, r=10)
                    )
                    st.plotly_chart(fig_h, use_container_width=True)
        
        except Exception as e:
            st.error(f"Error reading file. Kripya ensure karein format sahi hai.")
