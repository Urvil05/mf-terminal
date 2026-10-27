import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import requests
import json
import os
from datetime import datetime, timedelta
from github import Github

# Streamlit secrets se secure credentials fetch karna
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", None)
REPO_NAME = st.secrets.get("REPO_NAME", None)

def load_json(filepath, default_val):
    if GITHUB_TOKEN and REPO_NAME:
        try:
            g = Github(GITHUB_TOKEN)
            repo = g.get_repo(REPO_NAME)
            file_content = repo.get_contents(filepath)
            return json.loads(file_content.decoded_content.decode("utf-8"))
        except:
            pass # Agar file GitHub par pehli baar nahi bani hai toh aage badhega
            
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f: return json.load(f)
        except: pass
    return default_val

def save_json(filepath, data):
    # 1. Local system me turant save karna (UI fast rakhne ke liye)
    with open(filepath, "w") as f: json.dump(data, f)
    
    # 2. GitHub repo me background commit karna (Permanent storage)
    if GITHUB_TOKEN and REPO_NAME:
        try:
            g = Github(GITHUB_TOKEN)
            repo = g.get_repo(REPO_NAME)
            content_str = json.dumps(data, indent=4)
            
            try:
                contents = repo.get_contents(filepath)
                repo.update_file(contents.path, f"APEX Auto-Sync: Update {filepath}", content_str, contents.sha)
            except:
                repo.create_file(filepath, f"APEX Auto-Sync: Create {filepath}", content_str)
        except Exception as e:
            st.sidebar.error(f"GitHub Sync Failed: {e}")

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
FACTSHEET_FILE = "factsheet_data.json"
DEFAULT_WATCHLIST = [] 

def load_factsheet_cache():
    cache = load_json(FACTSHEET_FILE, {})
    for k, v in cache.items():
        if "top10" in v: v["top10"] = pd.DataFrame(v["top10"])
        if "sec_df" in v and v["sec_df"] is not None: v["sec_df"] = pd.DataFrame(v["sec_df"])
    return cache

def save_factsheet_cache(cache):
    serializable_cache = {}
    for k, v in cache.items():
        serializable_cache[k] = {
            "top10": v["top10"].to_dict(orient="records"),
            "comp": v["comp"],
            "w": v["w"],
            "sec": v["sec"],
            "sec_df": v["sec_df"].to_dict(orient="records") if v["sec_df"] is not None else None
        }
    save_json(FACTSHEET_FILE, serializable_cache)

if "watchlist" not in st.session_state: st.session_state["watchlist"] = load_json(WATCHLIST_FILE, DEFAULT_WATCHLIST)
if "portfolio" not in st.session_state: st.session_state["portfolio"] = load_json(PORTFOLIO_FILE, [])
if "factsheet_cache" not in st.session_state: st.session_state["factsheet_cache"] = load_factsheet_cache()

@st.cache_data(ttl=86400, show_spinner=False)
def get_all_schemes():
    try:
        res = requests.get("https://api.mfapi.in/mf", timeout=10)
        df = pd.DataFrame(res.json())
        df["search_term"] = df["schemeName"].str.lower()
        return df
    except: return pd.DataFrame()

@st.cache_data(ttl=3600, show_spinner=False)
def get_historical_nav(code):
    try:
        res = requests.get(f"https://api.mfapi.in/mf/{code}", timeout=10).json()
        if "meta" not in res or "data" not in res or len(res["data"]) == 0: return None
        df = pd.DataFrame(res["data"])
        df['date'] = pd.to_datetime(df['date'], format='%d-%m-%Y')
        df['nav'] = df['nav'].astype(float)
        return {"name": res["meta"]["scheme_name"], "data": df.sort_values('date').reset_index(drop=True)}
    except: return None

@st.cache_data(ttl=3600, show_spinner=False)
def calculate_fund_metrics(code):
    nav_data = get_historical_nav(code)
    if not nav_data: return None
    df, name = nav_data["data"], nav_data["name"]
    latest_nav, latest_date = df.iloc[-1]['nav'], df.iloc[-1]['date']
    
    # Extract Previous Day NAV & Calculate 1D Change
    prev_nav = df.iloc[-2]['nav'] if len(df) > 1 else latest_nav
    day_change = round(((latest_nav / prev_nav) - 1) * 100, 2) if prev_nav else 0.0
    
    def get_past_nav(days):
        past_df = df[df['date'] <= (latest_date - timedelta(days=days))]
        return past_df.iloc[-1]['nav'] if not past_df.empty else None

    nav_1m, nav_1y, nav_3y = get_past_nav(30), get_past_nav(365), get_past_nav(1095)
    ret_1y = round(((latest_nav / nav_1y) - 1) * 100, 2) if nav_1y else None
    cagr_3y = round((((latest_nav / nav_3y) ** (1/3)) - 1) * 100, 2) if nav_3y else None
    
    risk_df = df[df['date'] >= latest_date - timedelta(days=1095)].copy()
    sharpe = sortino = vol = None
    if len(risk_df) > 200:
        returns = risk_df['nav'].pct_change().dropna()
        mean_ret, vol = returns.mean() * 252, returns.std() * np.sqrt(252)
        if vol > 0: sharpe = round((mean_ret - 0.065) / vol, 2)
        down_vol = returns[returns < 0].std() * np.sqrt(252)
        if down_vol > 0: sortino = round((mean_ret - 0.065) / down_vol, 2)
                
    return {
        "Code": code, 
        "Fund Name": name, 
        "Current NAV": latest_nav, 
        "Prev NAV": prev_nav, 
        "1D Change (%)": day_change, 
        "1-Year (%)": ret_1y, 
        "3-Year CAGR (%)": cagr_3y, 
        "Sharpe": sharpe, 
        "Sortino": sortino, 
        "Volatility (%)": round(vol*100,2) if vol else None
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
    funds_to_del = st.sidebar.multiselect("Select to remove:", list(delete_dict.keys()), key="unique_delete_funds_key")
    if st.sidebar.button("🗑️ Remove", key="unique_remove_button_key"):
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
            valid_m = [m for m in [calculate_fund_metrics(c) for c in st.session_state["watchlist"]] if m]
            if valid_m: 
                # Removed 'Latest NAV' from drop so the new Current NAV, Prev NAV & Change show up
                st.dataframe(pd.DataFrame(valid_m).drop(columns=["Code"]), use_container_width=True, hide_index=True)
    else: st.info("Watchlist is empty. Add funds from the sidebar.")

with tab2:
    st.markdown("### 📥 Fund-Specific Factsheet Parser")
    
    if st.session_state["watchlist"]:
        f_dict = {}
        for c in st.session_state["watchlist"]:
            match = all_schemes[all_schemes["schemeCode"] == c] if not all_schemes.empty else pd.DataFrame()
            f_dict[match["schemeName"].iloc[0] if not match.empty else str(c)] = str(c)
                
        selected_fund_name = st.selectbox("🎯 Select Fund:", list(f_dict.keys()))
        curr_code = f_dict[selected_fund_name]
        
        if curr_code in st.session_state["factsheet_cache"]:
            st.success(f"✅ Data for {selected_fund_name} is permanently locked.")
            cached = st.session_state["factsheet_cache"][curr_code]
            top10, comp, w, sec, sec_df = cached["top10"], cached["comp"], cached["w"], cached["sec"], cached["sec_df"]
            
            st.markdown("---")
            t1, t2 = st.columns([1, 1])
            with t1:
                st.markdown("##### Top 10 Holdings")
                st.dataframe(top10.style.format({w: "{:.2f}%"}), use_container_width=True, hide_index=True)
            with t2:
                st.markdown("##### Holdings Distribution")
                st.plotly_chart(px.pie(top10, values=w, names=comp, hole=0.55).update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(t=0,b=0,l=0,r=0)), use_container_width=True)
                
            if sec != "None" and sec_df is not None:
                st.markdown("##### 🏢 Sector Breakdown")
                sec_df[sec] = sec_df[sec].fillna("Other").astype(str)
                st.plotly_chart(px.treemap(sec_df, path=[sec], values=w, color=w, color_continuous_scale='Electric').update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(t=10,b=10,l=10,r=10)), use_container_width=True)
                
            if st.button("🗑️ Delete & Re-upload"):
                del st.session_state["factsheet_cache"][curr_code]
                save_factsheet_cache(st.session_state["factsheet_cache"])
                st.rerun()
        else:
            st.info("No data cached. Please upload file below.")
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
                        r_vals = [str(x).lower() for x in df_raw.iloc[i].values]
                        if any(k in r for r in r_vals for k in ["company","issuer","name"]) and any(k in r for r in r_vals for k in ["asset","weight","%"]):
                            header_row = i
                            break
                    
                    df = pd.read_csv(f_file, skiprows=header_row) if f_file.name.endswith(".csv") else pd.read_excel(f_file, sheet_name=sheet_name, skiprows=header_row)
                    df.columns = [str(c).strip() for c in df.columns]
                    
                    with st.expander("🔍 Map Columns", expanded=True):
                        c1, c2, c3 = st.columns(3)
                        def_comp = next((c for c in df.columns if any(k in c.lower() for k in ["company","instrument","issuer","name"])), "None")
                        def_sec = next((c for c in df.columns if any(k in c.lower() for k in ["sector","industry","rating"])), "None")
                        def_w = next((c for c in df.columns if any(k in c.lower() for k in ["asset","%","weight","nav"])), "None")
                        
                        opts = ["None"] + list(df.columns)
                        comp = c1.selectbox("Company Col:", opts, index=opts.index(def_comp) if def_comp in opts else 0)
                        sec = c2.selectbox("Sector Col (Opt):", opts, index=opts.index(def_sec) if def_sec in opts else 0)
                        w = c3.selectbox("Weight Col:", opts, index=opts.index(def_w) if def_w in opts else 0)
                        
                        if st.button("🚀 Permanently Lock Data", type="primary"):
                            if comp != "None" and w != "None":
                                clean = df[[comp, w] + ([sec] if sec != "None" else [])].dropna(subset=[comp, w]).copy()
                                clean[w] = pd.to_numeric(clean[w].astype(str).str.replace('%', '', regex=False).str.strip(), errors='coerce')
                                clean = clean.dropna(subset=[w])
                                clean = clean[(clean[w] <= 100) & (~clean[comp].astype(str).str.lower().isin(['total','grand total','equity','debt','cash','portfolio']))]
                                
                                top10 = clean.sort_values(w, ascending=False).head(10)
                                sec_df = clean.groupby(sec)[w].sum().reset_index() if sec != "None" else None
                                if sec_df is not None: sec_df = sec_df[sec_df[w] > 0]
                                    
                                st.session_state["factsheet_cache"][curr_code] = {"top10": top10, "comp": comp, "w": w, "sec": sec, "sec_df": sec_df}
                                save_factsheet_cache(st.session_state["factsheet_cache"])
                                st.rerun()
                            else: st.warning("Map Company and Weight columns.")
                except Exception as e: st.error(f"Error: {str(e)}")
    else: st.info("Please add funds to Watchlist first.")

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
            # Updated to fetch "Current NAV" instead of "Latest NAV"
            current_nav = live_data["Current NAV"] if live_data else 0
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
