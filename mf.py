import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
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
PORTFOLIO_FILE = "paper_portfolio.json"
DEFAULT_WATCHLIST = [] 

def load_json(filepath, default_val):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f: return json.load(f)
        except: pass
    return default_val

def save_json(filepath, data):
    with open(filepath, "w") as f: json.dump(data, f)

if "watchlist" not in st.session_state:
    st.session_state["watchlist"] = load_json(WATCHLIST_FILE, DEFAULT_WATCHLIST)
if "portfolio" not in st.session_state:
    st.session_state["portfolio"] = load_json(PORTFOLIO_FILE, [])

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
        elif "index" in cat_low: bench = "NIFTY 50 TRI"
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
            "Sortino Ratio": sortino,
            "Latest NAV": latest_nav
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
                save_json(WATCHLIST_FILE, st.session_state["watchlist"])
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
            save_json(WATCHLIST_FILE, st.session_state["watchlist"])
            st.rerun()

# --- MAIN UI ---
st.markdown("<h1 style='font-weight: 800; font-size: 2.2rem; color: #38bdf8;'>APEX QUANTITATIVE TERMINAL</h1>", unsafe_allow_html=True)
tab1, tab2, tab3 = st.tabs(["📊 Quant Dashboard", "🏢 Factsheet Parser", "💼 Paper Portfolio (LTCG/STCG)"])

with tab1:
    if st.session_state["watchlist"]:
        st.write(f"**Tracking {len(st.session_state['watchlist'])} Funds** | *Live data fetching directly from AMFI API...*")
        with st.spinner("Calculating Metrics..."):
            metrics_list = []
            for code in st.session_state["watchlist"]:
                data = calculate_fund_metrics(code)
                if data:
                    metrics_list.append(data)
            
            if metrics_list:
                df_display = pd.DataFrame(metrics_list).drop(columns=["Code", "Latest NAV"])
                st.dataframe(df_display, use_container_width=True, hide_index=True)
    else:
        st.info("Watchlist is empty. Add funds from the sidebar on the left.")

with tab2:
    st.markdown("### 📥 Smart Factsheet Parser")
    st.caption("Pitching ke liye AMC ki official website se downloaded Monthly Portfolio (.xlsx / .csv) upload karein.")
    factsheet_file = st.file_uploader("Upload Official AMC Portfolio File", type=["xlsx", "xls", "csv"])
    if factsheet_file is not None:
        try:
            raw_df = pd.read_csv(factsheet_file) if factsheet_file.name.endswith(".csv") else pd.read_excel(factsheet_file)
            st.success(f"File '{factsheet_file.name}' loaded successfully!")
            with st.expander("🔍 Inspect Raw Factsheet Data"):
                st.dataframe(raw_df.head(15), use_container_width=True)
            
            col1, col2 = st.columns(2)
            company_col = col1.selectbox("Select 'Company Name' Column:", ["None"] + list(raw_df.columns))
            weight_col = col2.selectbox("Select 'Weight (%)' Column:", ["None"] + list(raw_df.columns))
            
            if company_col != "None" and weight_col != "None":
                clean_df = raw_df[[company_col, weight_col]].copy()
                clean_df[weight_col] = pd.to_numeric(clean_df[weight_col], errors='coerce')
                clean_df = clean_df.dropna(subset=[company_col, weight_col])
                clean_df = clean_df.sort_values(by=weight_col, ascending=False).head(10) 
                
                h1, h2 = st.columns([3, 2])
                with h1: st.dataframe(clean_df, use_container_width=True, hide_index=True)
                with h2:
                    fig_h = px.pie(clean_df, values=weight_col, names=company_col, hole=0.55, color_discrete_sequence=px.colors.sequential.Electric)
                    fig_h.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#94a3b8"), margin=dict(t=10, b=10, l=10, r=10))
                    st.plotly_chart(fig_h, use_container_width=True)
        except:
            st.error("Error reading file. Kripya ensure karein format sahi hai.")
with tab3:
    st.markdown("### 💼 Portfolio Ledger & Taxation Engine")
    
    # FIFO Calculation for LTCG/STCG (Backward Compatible)
    holdings = {}
    for t in st.session_state["portfolio"]:
        code = t.get('code')
        if not code: continue
        
        if code not in holdings: holdings[code] = {'name': t.get('name', 'Unknown Fund'), 'lots': []}
        
        t_type = t.get('type', 'Buy')
        t_date = t.get('date', t.get('buy_date', '2026-01-01'))
        t_nav = t.get('nav', t.get('buy_nav', 0.0))
        t_units = t.get('units', 0.0)
        
        if t_type in ['Buy', 'SIP']:
            try:
                dt_obj = datetime.strptime(t_date, '%Y-%m-%d')
            except:
                dt_obj = datetime.today()
            holdings[code]['lots'].append({'date': dt_obj, 'units': float(t_units), 'nav': float(t_nav)})
        elif t_type == 'Sell':
            units_to_sell = float(t_units)
            for lot in holdings[code]['lots']:
                if lot['units'] > 0:
                    if lot['units'] >= units_to_sell:
                        lot['units'] -= units_to_sell
                        units_to_sell = 0
                        break
                    else:
                        units_to_sell -= lot['units']
                        lot['units'] = 0

    today = datetime.today()
    portfolio_rows = []
    
    for code, data in holdings.items():
        total_units = 0
        total_inv = 0
        stcg_units = 0
        ltcg_units = 0
        
        for lot in data['lots']:
            if lot['units'] > 0:
                total_units += lot['units']
                total_inv += lot['units'] * lot['nav']
                if (today - lot['date']).days > 365:
                    ltcg_units += lot['units']
                else:
                    stcg_units += lot['units']
                    
        if total_units > 0.001: 
            live_data = calculate_fund_metrics(code)
            current_nav = live_data["Latest NAV"] if live_data else 0
            current_value = total_units * current_nav
            pnl = current_value - total_inv
            
            portfolio_rows.append({
                "Fund Name": data['name'],
                "Total Units": round(total_units, 3),
                "Invested (₹)": round(total_inv, 2),
                "Current Value (₹)": round(current_value, 2),
                "P&L (₹)": round(pnl, 2),
                "STCG Units (<1Y)": round(stcg_units, 3),
                "LTCG Units (>1Y)": round(ltcg_units, 3)
            })

    if portfolio_rows:
        st.dataframe(pd.DataFrame(portfolio_rows), use_container_width=True, hide_index=True)
    else:
        st.info("No active holdings found in portfolio.")

    st.markdown("---")
    if st.button("🚨 Clear Entire Portfolio JSON Cache"):
        st.session_state["portfolio"] = []
        save_json(PORTFOLIO_FILE, [])
        st.rerun()

    with st.expander("➕ Execute Trade (Lumpsum / SIP / Sell)", expanded=True):
        if st.session_state["watchlist"]:
            # FAST INTERNAL MAPPING (Bypasses API Lag)
            f_dict = {}
            for c in st.session_state["watchlist"]:
                match = all_schemes[all_schemes["schemeCode"] == c] if not all_schemes.empty else pd.DataFrame()
                if not match.empty:
                    f_dict[match["schemeName"].iloc[0]] = c
                else:
                    f_dict[str(c)] = c
            
            st.markdown("#### Record New Transaction")
            trade_fund = st.selectbox("Select Target Scheme:", list(f_dict.keys()))
            
            col1, col2 = st.columns(2)
            trade_type = col1.selectbox("Transaction Type:", ["Buy", "SIP", "Sell"])
            trade_date = col2.date_input("Transaction Date", value=today)
            
            c_u, c_n = st.columns(2)
            trade_units = c_u.number_input("Number of Units", min_value=0.001, value=10.0, step=1.0)
            trade_nav = c_n.number_input("NAV at execution (₹)", min_value=0.01, value=100.0, step=1.0)
            
            if st.button("Commit Transaction", type="primary"):
                new_trade = {
                    "code": f_dict[trade_fund],
                    "name": trade_fund,
                    "type": trade_type,
                    "date": trade_date.strftime('%Y-%m-%d'),
                    "units": float(trade_units),
                    "nav": float(trade_nav)
                }
                st.session_state["portfolio"].append(new_trade)
                save_json(PORTFOLIO_FILE, st.session_state["portfolio"])
                st.rerun()
        else:
            st.warning("Please add funds to your Watchlist from the sidebar first to execute trades.")
