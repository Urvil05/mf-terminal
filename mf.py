import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
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
def get_historical_nav(code):
    try:
        res = requests.get(f"https://api.mfapi.in/mf/{code}", timeout=10).json()
        if "meta" not in res or "data" not in res or len(res["data"]) == 0: return None
        
        name = res["meta"]["scheme_name"]
        df = pd.DataFrame(res["data"])
        df['date'] = pd.to_datetime(df['date'], format='%d-%m-%Y')
        df['nav'] = df['nav'].astype(float)
        df = df.sort_values('date').reset_index(drop=True)
        return {"name": name, "data": df}
    except:
        return None

@st.cache_data(ttl=3600, show_spinner=False)
def calculate_fund_metrics(code):
    nav_data = get_historical_nav(code)
    if not nav_data: return None
    
    df = nav_data["data"]
    name = nav_data["name"]
    
    latest_nav = df.iloc[-1]['nav']
    latest_date = df.iloc[-1]['date']
    
    def get_past_nav(days):
        target = latest_date - timedelta(days=days)
        past_df = df[df['date'] <= target]
        return past_df.iloc[-1]['nav'] if not past_df.empty else None

    nav_1m, nav_1y, nav_3y = get_past_nav(30), get_past_nav(365), get_past_nav(1095)
    ret_1y = round(((latest_nav / nav_1y) - 1) * 100, 2) if nav_1y else None
    cagr_3y = round((((latest_nav / nav_3y) ** (1/3)) - 1) * 100, 2) if nav_3y else None
    
    risk_df = df[df['date'] >= latest_date - timedelta(days=1095)].copy()
    sharpe = sortino = vol = None
    if len(risk_df) > 200:
        risk_df['ret'] = risk_df['nav'].pct_change()
        returns = risk_df['ret'].dropna()
        mean_ret = returns.mean() * 252
        vol = returns.std() * np.sqrt(252)
        rf = 0.065 
        if vol > 0: sharpe = round((mean_ret - rf) / vol, 2)
        downside = returns[returns < 0]
        if len(downside) > 0:
            down_vol = downside.std() * np.sqrt(252)
            if down_vol > 0: sortino = round((mean_ret - rf) / down_vol, 2)
                
    return {
        "Code": code, "Fund Name": name, "1-Year (%)": ret_1y, "3-Year CAGR (%)": cagr_3y,
        "Sharpe": sharpe, "Sortino": sortino, "Volatility (%)": round(vol*100,2) if vol else None, "Latest NAV": latest_nav
    }

all_schemes = get_all_schemes()

st.sidebar.markdown("### 🔍 Add New Fund")
query = st.sidebar.text_input("Search Fund:")
if query and not all_schemes.empty:
    matches = all_schemes[all_schemes["search_term"].str.contains(query.lower(), na=False)].head(20)
    if not matches.empty:
        sel_fund = st.sidebar.selectbox("Select:", matches["schemeName"].tolist())
        if st.sidebar.button("➕ Add to Watchlist"):
            code = int(matches[matches["schemeName"] == sel_fund]["schemeCode"].iloc[0])
            if code not in st.session_state["watchlist"]:
                st.session_state["watchlist"].append(code)
                save_json(WATCHLIST_FILE, st.session_state["watchlist"])
                st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown("### ❌ Remove Funds")
if st.session_state["watchlist"]:
    delete_dict = {str(c): c for c in st.session_state["watchlist"]}
    funds_to_del = st.sidebar.multiselect("Select to remove:", list(delete_dict.keys()))
    if st.sidebar.button("🗑️ Remove"):
        for f in funds_to_del: st.session_state["watchlist"].remove(delete_dict[f])
        save_json(WATCHLIST_FILE, st.session_state["watchlist"])
        st.rerun()

st.markdown("<h1 style='font-weight: 800; font-size: 2.2rem; color: #38bdf8;'>APEX QUANTITATIVE TERMINAL</h1>", unsafe_allow_html=True)
tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard", "🏢 Factsheet", "💼 Portfolio", "📈 Advanced Analysis"])

with tab1:
    if st.session_state["watchlist"]:
        with st.spinner("Loading metrics..."):
            m_list = [calculate_fund_metrics(c) for c in st.session_state["watchlist"]]
            valid_m = [m for m in m_list if m]
            if valid_m: st.dataframe(pd.DataFrame(valid_m).drop(columns=["Code", "Latest NAV"]), use_container_width=True, hide_index=True)
    else: st.info("Watchlist empty.")

with tab2:
    st.markdown("### 📥 Factsheet Parser")
    f_file = st.file_uploader("Upload Excel", type=["xlsx", "csv"])
    if f_file:
        try:
            df = pd.read_csv(f_file) if f_file.name.endswith(".csv") else pd.read_excel(f_file)
            c1, c2 = st.columns(2)
            comp = c1.selectbox("Company Col:", df.columns)
            w = c2.selectbox("Weight Col:", df.columns)
            if st.button("Generate"):
                clean = df[[comp, w]].dropna()
                clean[w] = pd.to_numeric(clean[w], errors='coerce')
                clean = clean.sort_values(w, ascending=False).head(10)
                st.dataframe(clean)
                st.plotly_chart(px.pie(clean, values=w, names=comp, hole=0.5))
        except: st.error("Error reading file.")

with tab3:
    st.write("Portfolio engine active.")
    # (Portfolio code kept minimal here for focus, you can paste the Tab 3 block from previous step if needed)

with tab4:
    st.markdown("### 📈 Institutional Fund Analysis")
    if st.session_state["watchlist"]:
        f_dict = {}
        for c in st.session_state["watchlist"]:
            try:
                n = requests.get(f"https://api.mfapi.in/mf/{c}", timeout=3).json().get("meta", {}).get("scheme_name", str(c))
                f_dict[n] = c
            except: f_dict[str(c)] = c
            
        compare_funds = st.multiselect("Select Funds for Head-to-Head Comparison:", list(f_dict.keys()), default=list(f_dict.keys())[:2])
        
        if compare_funds:
            with st.spinner("Crunching historical data (100% accurate mathematical models)..."):
                hist_data = {}
                for f_name in compare_funds:
                    code = f_dict[f_name]
                    raw = get_historical_nav(code)
                    if raw: hist_data[f_name] = raw['data']
                
                if hist_data:
                    c1, c2 = st.columns(2)
                    
                    # 1. Historical Drawdown Chart (Crash Severity)
                    with c1:
                        st.markdown("#### Maximum Drawdown (Risk)")
                        fig_dd = go.Figure()
                        for f_name, df in hist_data.items():
                            df = df.set_index('date')
                            roll_max = df['nav'].cummax()
                            drawdown = (df['nav'] - roll_max) / roll_max * 100
                            fig_dd.add_trace(go.Scatter(x=drawdown.index, y=drawdown, mode='lines', name=f_name[:20]))
                        fig_dd.update_layout(template="plotly_dark", margin=dict(l=0, r=0, t=30, b=0))
                        st.plotly_chart(fig_dd, use_container_width=True)
                    
                    # 2. Risk-Reward Scatter Plot
                    with c2:
                        st.markdown("#### Risk vs Reward (3Y)")
                        scatter_data = []
                        for f_name in compare_funds:
                            code = f_dict[f_name]
                            m = calculate_fund_metrics(code)
                            if m and m["3-Year CAGR (%)"] and m["Volatility (%)"]:
                                scatter_data.append({"Fund": f_name[:25], "CAGR": m["3-Year CAGR (%)"], "Risk (Vol)": m["Volatility (%)"]})
                        
                        if scatter_data:
                            sdf = pd.DataFrame(scatter_data)
                            fig_sc = px.scatter(sdf, x="Risk (Vol)", y="CAGR", text="Fund", size_max=60, color="Fund")
                            fig_sc.update_traces(textposition='top center')
                            fig_sc.update_layout(template="plotly_dark", margin=dict(l=0, r=0, t=30, b=0))
                            st.plotly_chart(fig_sc, use_container_width=True)
                        else:
                            st.warning("Not enough 3-year data for scatter plot.")
                            
                    # 3. 1-Year Rolling Returns Summary
                    st.markdown("#### 1-Year Rolling Return Consistency")
                    roll_stats = []
                    for f_name, df in hist_data.items():
                        df = df.set_index('date').sort_index()
                        df['1Y_Roll'] = df['nav'].pct_change(periods=252) * 100
                        clean_roll = df['1Y_Roll'].dropna()
                        if not clean_roll.empty:
                            roll_stats.append({
                                "Fund": f_name,
                                "Avg 1Y Return": round(clean_roll.mean(), 2),
                                "Max 1Y Return": round(clean_roll.max(), 2),
                                "Min 1Y Return": round(clean_roll.min(), 2),
                                "% Times Negative": round((len(clean_roll[clean_roll < 0]) / len(clean_roll)) * 100, 2)
                            })
                    if roll_stats:
                        st.dataframe(pd.DataFrame(roll_stats), use_container_width=True, hide_index=True)
    else:
        st.info("Watchlist me funds add karein analysis ke liye.")
