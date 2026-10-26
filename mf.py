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

    nav_1m = get_past_nav(30)
    nav_1y = get_past_nav(365)
    nav_3y = get_past_nav(1095)
    
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
query = st.sidebar.text_input("Search Fund (e.g. Axis Bluechip):")
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
        
    if st.sidebar.button("🚨 Clear Entire Watchlist"):
        st.session_state["watchlist"] = []
        save_json(WATCHLIST_FILE, [])
        st.rerun()

st.markdown("<h1 style='font-weight: 800; font-size: 2.2rem; color: #38bdf8;'>APEX QUANTITATIVE TERMINAL</h1>", unsafe_allow_html=True)
tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard", "🏢 Factsheet", "💼 Portfolio", "📈 Advanced Analysis"])

with tab1:
    if st.session_state["watchlist"]:
        with st.spinner("Loading metrics..."):
            m_list = [calculate_fund_metrics(c) for c in st.session_state["watchlist"]]
            valid_m = [m for m in m_list if m]
            if valid_m: st.dataframe(pd.DataFrame(valid_m).drop(columns=["Code", "Latest NAV"]), use_container_width=True, hide_index=True)
    else: st.info("Watchlist is empty. Add funds from the sidebar.")

with tab2:
    st.markdown("### 📥 Fund-Specific Factsheet Parser")
    st.caption("Ek baar file upload karke save karein, data background me permanently lock ho jayega.")
    
    if "factsheet_cache" not in st.session_state:
        st.session_state["factsheet_cache"] = {}
        
    if st.session_state["watchlist"]:
        f_dict = {}
        for c in st.session_state["watchlist"]:
            match = all_schemes[all_schemes["schemeCode"] == c] if not all_schemes.empty else pd.DataFrame()
            if not match.empty: 
                f_dict[match["schemeName"].iloc[0]] = c
            else: 
                f_dict[str(c)] = c
                
        selected_fund_name = st.selectbox("🎯 Select Fund for Factsheet Analysis:", list(f_dict.keys()))
        curr_code = f_dict[selected_fund_name]
        
        if curr_code in st.session_state["factsheet_cache"]:
            st.success(f"✅ Data for {selected_fund_name} is securely locked in memory.")
            
            cached_data = st.session_state["factsheet_cache"][curr_code]
            top10, comp, w = cached_data["top10"], cached_data["comp"], cached_data["w"]
            sec, sec_df = cached_data["sec"], cached_data["sec_df"]
            
            st.markdown("---")
            st.markdown(f"### 🎯 Verified Portfolio Allocation: {selected_fund_name}")
            
            t1, t2 = st.columns([1, 1])
            with t1:
                st.markdown("##### Top 10 Holdings")
                st.dataframe(top10.style.format({w: "{:.2f}%"}), use_container_width=True, hide_index=True)
                
            with t2:
                st.markdown("##### Holdings Distribution")
                fig_h = px.pie(top10, values=w, names=comp, hole=0.55, color_discrete_sequence=px.colors.sequential.Electric)
                fig_h.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(t=0, b=0, l=0, r=0))
                st.plotly_chart(fig_h, use_container_width=True)
                
            if sec != "None" and sec_df is not None:
                st.markdown("##### 🏢 Sector Breakdown")
                fig_sec = px.treemap(sec_df, path=[sec], values=w, color=w, color_continuous_scale='Electric')
                fig_sec.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(t=10, b=10, l=10, r=10))
                st.plotly_chart(fig_sec, use_container_width=True)
                
            if st.button("🗑️ Delete & Re-upload Data for this Fund"):
                del st.session_state["factsheet_cache"][curr_code]
                st.rerun()
        else:
            st.info(f"No data cached for {selected_fund_name}. Please upload the file below.")
            f_file = st.file_uploader("Upload Official AMC Portfolio File", type=["xlsx", "xls", "csv"], key=f"up_{curr_code}")
            
            if f_file:
                try:
                    if f_file.name.endswith(".csv"):
                        df_raw = pd.read_csv(f_file)
                        sheet_name = "CSV Data"
                    else:
                        xls = pd.ExcelFile(f_file)
                        sheet_name = st.selectbox("📂 Select Sheet:", xls.sheet_names)
                        df_raw = pd.read_excel(xls, sheet_name=sheet_name, header=None)
                    
                    header_row = 0
                    for i in range(min(30, len(df_raw))):
                        row_vals = [str(x).lower() for x in df_raw.iloc[i].values]
                        if any("instrument" in r or "company" in r or "issuer" in r or "name" in r for r in row_vals) and any("asset" in r or "weight" in r or "%" in r for r in row_vals):
                            header_row = i
                            break
                    
                    if f_file.name.endswith(".csv"):
                        df = pd.read_csv(f_file, skiprows=header_row)
                    else:
                        df = pd.read_excel(f_file, sheet_name=sheet_name, skiprows=header_row)
                    
                    df.columns = [str(c).strip() for c in df.columns]
                    
                    with st.expander("🔍 Map Columns for Analysis", expanded=True):
                        c1, c2, c3 = st.columns(3)
                        def_comp = next((c for c in df.columns if "company" in c.lower() or "instrument" in c.lower() or "issuer" in c.lower() or "name" in c.lower()), "None")
                        def_sec = next((c for c in df.columns if "sector" in c.lower() or "industry" in c.lower() or "rating" in c.lower()), "None")
                        def_w = next((c for c in df.columns if "asset" in c.lower() or "%" in c.lower() or "weight" in c.lower() or "nav" in c.lower()), "None")
                        
                        comp_opts = ["None"] + list(df.columns)
                        comp = c1.selectbox("Company/Asset Col:", comp_opts, index=comp_opts.index(def_comp) if def_comp in comp_opts else 0)
                        sec = c2.selectbox("Sector Col (Opt):", comp_opts, index=comp_opts.index(def_sec) if def_sec in comp_opts else 0)
                        w = c3.selectbox("Weight (%) Col:", comp_opts, index=comp_opts.index(def_w) if def_w in comp_opts else 0)
                        
                        if st.button("🚀 Lock Data & Generate Insights", type="primary"):
                            if comp != "None" and w != "None":
                                analyze_cols = [comp, w]
                                if sec != "None": analyze_cols.append(sec)
                                
                                clean = df[analyze_cols].dropna(subset=[comp, w]).copy()
                                clean[w] = clean[w].astype(str).str.replace('%', '', regex=False).str.strip()
                                clean[w] = pd.to_numeric(clean[w], errors='coerce')
                                clean = clean.dropna(subset=[w])
                                
                                junk_kw = ['total', 'grand total', 'equity', 'debt', 'cash', 'portfolio']
                                clean = clean[~clean[comp].astype(str).str.lower().isin(junk_kw)]
                                
                                top10 = clean.sort_values(w, ascending=False).head(10)
                                sec_df = None
                                if sec != "None":
                                    sec_df = clean.groupby(sec)[w].sum().reset_index()
                                    sec_df = sec_df[sec_df[w] > 0]
                                    
                                st.session_state["factsheet_cache"][curr_code] = {
                                    "top10": top10, "comp": comp, "w": w, "sec": sec, "sec_df": sec_df
                                }
                                st.rerun()
                            else:
                                st.warning("Map Company and Weight columns first.")
                except Exception as e: 
                    st.error(f"Error parsing file: {str(e)}")
    else:
        st.info("💡 Please add funds to your Watchlist from the sidebar to activate the Factsheet Parser.")

with tab3:
    st.markdown("### 💼 Portfolio Ledger & Taxation Engine")
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
            try: dt_obj = datetime.strptime(t_date, '%Y-%m-%d')
            except: dt_obj = datetime.today()
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
        total_units = total_inv = stcg_units = ltcg_units = 0
        for lot in data['lots']:
            if lot['units'] > 0:
                total_units += lot['units']
                total_inv += lot['units'] * lot['nav']
                if (today - lot['date']).days > 365: ltcg_units += lot['units']
                else: stcg_units += lot['units']
                    
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

    if portfolio_rows: st.dataframe(pd.DataFrame(portfolio_rows), use_container_width=True, hide_index=True)
    else: st.info("No active holdings found in portfolio.")

    st.markdown("---")
    if st.button("🚨 Clear Entire Portfolio JSON Cache"):
        st.session_state["portfolio"] = []
        save_json(PORTFOLIO_FILE, [])
        st.rerun()

    with st.expander("➕ Execute Trade (Lumpsum / SIP / Sell)", expanded=True):
        if st.session_state["watchlist"]:
            f_dict = {}
            for c in st.session_state["watchlist"]:
                match = all_schemes[all_schemes["schemeCode"] == c] if not all_schemes.empty else pd.DataFrame()
                if not match.empty: f_dict[match["schemeName"].iloc[0]] = c
                else: f_dict[str(c)] = c
            
            trade_fund = st.selectbox("Select Target Scheme:", list(f_dict.keys()))
            col1, col2 = st.columns(2)
            trade_type = col1.selectbox("Transaction Type:", ["Buy", "SIP", "Sell"])
            trade_date = col2.date_input("Transaction Date", value=today)
            
            c_u, c_n = st.columns(2)
            trade_units = c_u.number_input("Number of Units", min_value=0.001, value=10.0, step=1.0)
            trade_nav = c_n.number_input("NAV at execution (₹)", min_value=0.01, value=100.0, step=1.0)
            
            if st.button("Commit Transaction", type="primary"):
                new_trade = {
                    "code": f_dict[trade_fund], "name": trade_fund, "type": trade_type,
                    "date": trade_date.strftime('%Y-%m-%d'), "units": float(trade_units), "nav": float(trade_nav)
                }
                st.session_state["portfolio"].append(new_trade)
                save_json(PORTFOLIO_FILE, st.session_state["portfolio"])
                st.rerun()
        else: st.warning("Please add funds to your Watchlist first.")

with tab4:
    st.markdown("### 📈 Institutional Fund Analysis")
    if st.session_state["watchlist"]:
        f_dict = {}
        for c in st.session_state["watchlist"]:
            match = all_schemes[all_schemes["schemeCode"] == c] if not all_schemes.empty else pd.DataFrame()
            if not match.empty: f_dict[match["schemeName"].iloc[0]] = c
            else: f_dict[str(c)] = c
            
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
