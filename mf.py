import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import requests
import json
import os
import yfinance as yf
from datetime import datetime, timedelta
from github import Github

# --- 1. GitHub API Setup (Permanent Storage) ---
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", None)
REPO_NAME = st.secrets.get("REPO_NAME", None)

def load_json(filepath, default_val):
    if GITHUB_TOKEN and REPO_NAME:
        try:
            g = Github(GITHUB_TOKEN)
            repo = g.get_repo(REPO_NAME)
            file_content = repo.get_contents(filepath)
            return json.loads(file_content.decoded_content.decode("utf-8"))
        except: pass 
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f: return json.load(f)
        except: pass
    return default_val

def save_json(filepath, data):
    with open(filepath, "w") as f: json.dump(data, f)
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
            if "404" in str(e): st.sidebar.error("GitHub Sync Failed: Repo Not Found.")
            else: st.sidebar.error(f"GitHub Sync Failed: {e}")

st.set_page_config(page_title="APEX MF | Institutional Terminal", page_icon="⚡", layout="wide")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;800&family=JetBrains+Mono:wght@400;700&display=swap');
    html, body, [class*="css"] { font-family: 'Plus Jakarta Sans', sans-serif; }
    .stApp { background: radial-gradient(circle at top right, #0f172a 0%, #030712 100%); color: #f8fafc; }
    div[data-testid="stDataFrame"] { border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 12px; overflow: hidden; }
    .nav-box { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); padding: 15px; border-radius: 10px; text-align: center; }
</style>
""", unsafe_allow_html=True)

WATCHLIST_FILE = "tracked_funds.json"
PORTFOLIO_FILE = "paper_portfolio.json"
FACTSHEET_FILE = "factsheet_data.json"
CUSTOM_TICKERS_FILE = "custom_tickers.json"

TICKER_MAP = {
    "hdfc bank ltd.": "HDFCBANK.NS", "hdfc bank limited": "HDFCBANK.NS",
    "reliance industries ltd.": "RELIANCE.NS", "reliance industries limited": "RELIANCE.NS",
    "icici bank ltd.": "ICICIBANK.NS", "icici bank limited": "ICICIBANK.NS",
    "infosys ltd.": "INFY.NS", "infosys limited": "INFY.NS",
    "larsen & toubro ltd.": "LT.NS", "itc ltd.": "ITC.NS",
    "tata consultancy services ltd.": "TCS.NS", "bharti airtel ltd.": "BHARTIARTL.NS",
    "axis bank ltd.": "AXISBANK.NS", "state bank of india": "SBIN.NS",
    "bajaj finance ltd.": "BAJFINANCE.NS", "kotak mahindra bank ltd.": "KOTAKBANK.NS",
    "maruti suzuki india ltd.": "MARUTI.NS", "sun pharmaceutical industries ltd.": "SUNPHARMA.NS",
    "tata motors ltd.": "TATAMOTORS.NS", "mahindra & mahindra ltd.": "M&M.NS"
}

if "custom_tickers" not in st.session_state: st.session_state["custom_tickers"] = load_json(CUSTOM_TICKERS_FILE, {})

def clean_stock_name(name):
    raw = str(name).lower().strip()
    if raw in st.session_state["custom_tickers"]: return st.session_state["custom_tickers"][raw]
    if raw in TICKER_MAP: return TICKER_MAP[raw]
    clean = raw.replace('ltd.', '').replace('limited', '').replace('co.', '').replace('company', '')
    clean = clean.replace('&', '').replace('-', ' ').replace(',', '')
    words = clean.split()
    if len(words) > 0: return words[0].upper() + ".NS"
    return "UNKNOWN.NS"

def load_factsheet_cache():
    cache = load_json(FACTSHEET_FILE, {})
    for k, v in cache.items():
        # Backward compatibility for 10, 20 and now 35 stocks
        if "top35" in v: v["top35"] = pd.DataFrame(v["top35"])
        elif "top20" in v: v["top35"] = pd.DataFrame(v["top20"])
        elif "top10" in v: v["top35"] = pd.DataFrame(v["top10"])
        if "sec_df" in v and v["sec_df"] is not None: v["sec_df"] = pd.DataFrame(v["sec_df"])
    return cache

def save_factsheet_cache(cache):
    serializable_cache = {}
    for k, v in cache.items():
        serializable_cache[k] = {
            "top35": v["top35"].to_dict(orient="records"),
            "comp": v["comp"], "w": v["w"], "sec": v["sec"],
            "sec_df": v["sec_df"].to_dict(orient="records") if v["sec_df"] is not None else None
        }
    save_json(FACTSHEET_FILE, serializable_cache)

if "watchlist" not in st.session_state: st.session_state["watchlist"] = load_json(WATCHLIST_FILE, [])
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
        "Code": code, "Fund Name": name, "Current NAV": latest_nav, "Prev NAV": prev_nav, 
        "1D Change (%)": day_change, "1-Year (%)": ret_1y, "3-Year CAGR (%)": cagr_3y, 
        "Sharpe": sharpe, "Sortino": sortino, "Volatility (%)": round(vol*100,2) if vol else None
    }

@st.cache_data(ttl=300, show_spinner=False)
def fetch_live_prices(ticker_list):
    prices = {}
    if not ticker_list: return prices
    try:
        tickers_str = " ".join(ticker_list)
        data = yf.download(tickers_str, period="5d", group_by="ticker", threads=True, progress=False)
        for t in ticker_list:
            try:
                if len(ticker_list) > 1: close_series = data[t]['Close'].dropna()
                else: close_series = data['Close'].dropna()
                
                if len(close_series) >= 2:
                    last_price = float(close_series.iloc[-1])
                    prev_price = float(close_series.iloc[-2])
                    change = round(((last_price / prev_price) - 1) * 100, 2)
                elif len(close_series) == 1:
                    last_price = float(close_series.iloc[-1])
                    prev_price = last_price
                    change = 0.0
                else:
                    last_price, prev_price, change = None, None, None
                
                if pd.notna(last_price): prices[t] = {'live': last_price, 'prev': prev_price, 'change': change}
            except: prices[t] = {'live': None, 'prev': None, 'change': None}
    except: pass
    return prices

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
    funds_to_del = st.sidebar.multiselect("Select to remove:", list(delete_dict.keys()), key="del_fund")
    if st.sidebar.button("🗑️ Remove", key="rem_btn"):
        for f in funds_to_del: st.session_state["watchlist"].remove(delete_dict[f])
        save_json(WATCHLIST_FILE, st.session_state["watchlist"])
        st.rerun()
        
    if st.sidebar.button("🚨 Clear Entire Watchlist"):
        st.session_state["watchlist"] = []
        save_json(WATCHLIST_FILE, [])
        st.rerun()

st.markdown("<h1 style='font-weight: 800; font-size: 2.2rem; color: #38bdf8;'>APEX QUANTITATIVE TERMINAL</h1>", unsafe_allow_html=True)
tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard", "🏢 Factsheet & Predictor", "💼 Portfolio", "📈 Advanced Analysis"])

with tab1:
    if st.session_state["watchlist"]:
        with st.spinner("Loading metrics..."):
            valid_m = [m for m in [calculate_fund_metrics(c) for c in st.session_state["watchlist"]] if m]
            if valid_m: 
                st.dataframe(pd.DataFrame(valid_m).drop(columns=["Code"]), use_container_width=True, hide_index=True)
    else: st.info("Watchlist is empty. Add funds from the sidebar.")

with tab2:
    st.markdown("### 📥 Factsheet Parser & Live Prediction Engine")
    
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
            
            top35 = cached.get("top35", pd.DataFrame())
            comp, w, sec, sec_df = cached.get("comp", ""), cached.get("w", ""), cached.get("sec", "None"), cached.get("sec_df", None)
            
            if not top35.empty:
                if 'Ticker' not in top35.columns:
                    top35['Ticker'] = top35[comp].apply(clean_stock_name)
                
                disp_df = top35.copy()
                
                with st.spinner("Fetching Live Market Data & Running Prediction Model..."):
                    tickers_to_fetch = [t for t in disp_df['Ticker'].tolist() if "UNKNOWN" not in str(t).upper()]
                    live_data = fetch_live_prices(tickers_to_fetch)
                    
                    disp_df['Prev Price (₹)'] = disp_df['Ticker'].map(lambda x: live_data.get(x, {}).get('prev') if live_data.get(x) else None).fillna("-")
                    disp_df['Live Price (₹)'] = disp_df['Ticker'].map(lambda x: live_data.get(x, {}).get('live') if live_data.get(x) else None).fillna("Not Traded")
                    disp_df['% Change'] = disp_df['Ticker'].map(lambda x: live_data.get(x, {}).get('change') if live_data.get(x) else None).fillna("-")
                
                m_data = calculate_fund_metrics(curr_code)
                last_official_nav = m_data["Current NAV"] if m_data else 0.0
                
                if last_official_nav > 0:
                    valid_changes = pd.to_numeric(disp_df['% Change'].replace("-", 0), errors='coerce').fillna(0)
                    weights = pd.to_numeric(disp_df[w], errors='coerce').fillna(0) / 100
                    
                    total_tracked_weight = weights.sum()
                    if total_tracked_weight > 0:
                        weighted_sum = (valid_changes * weights).sum()
                        normalized_est_change = weighted_sum / total_tracked_weight
                        predicted_nav = last_official_nav * (1 + (normalized_est_change / 100))
                        expected_pnl = predicted_nav - last_official_nav
                    else:
                        normalized_est_change, predicted_nav, expected_pnl = 0, last_official_nav, 0
                    
                    st.markdown("### 🔮 Alpha Predictive Engine (Live iNAV)")
                    colA, colB, colC = st.columns(3)
                    with colA:
                        st.markdown("<div class='nav-box'><h5>Today's Base NAV (T-1)</h5><h2 style='color:#94a3b8;'>₹ {:.4f}</h2></div>".format(last_official_nav), unsafe_allow_html=True)
                    with colB:
                        pred_color = "#22c55e" if normalized_est_change >= 0 else "#ef4444"
                        st.markdown("<div class='nav-box'><h5>⚡ Predicted Tonight's NAV</h5><h2 style='color:{};'>₹ {:.4f}</h2><span style='color:{}; font-weight:bold;'>{:.2f}%</span></div>".format(pred_color, predicted_nav, pred_color, normalized_est_change), unsafe_allow_html=True)
                    with colC:
                        st.markdown("<div class='nav-box'><h5>Est. Value Change</h5><h2 style='color:{};'>₹ {:+.4f}</h2></div>".format(pred_color, expected_pnl), unsafe_allow_html=True)
                
                st.markdown("#### 🟢 Live Market Heatmap (Top 35 Stocks)")
                
                disabled_cols = [c for c in disp_df.columns if c != 'Ticker']
                edited_df = st.data_editor(
                    disp_df,
                    column_config={
                        w: st.column_config.NumberColumn(format="%.2f%%"),
                        '% Change': st.column_config.NumberColumn(format="%.2f%%")
                    },
                    disabled=disabled_cols,
                    use_container_width=True,
                    hide_index=True,
                    key=f"edit_top35_{curr_code}"
                )
                
                if not edited_df['Ticker'].equals(disp_df['Ticker']):
                    for idx in disp_df.index:
                        old_t = disp_df.at[idx, 'Ticker']
                        new_t = edited_df.at[idx, 'Ticker']
                        if old_t != new_t:
                            raw_name = str(disp_df.at[idx, comp]).lower().strip()
                            st.session_state["custom_tickers"][raw_name] = new_t
                    
                    save_json(CUSTOM_TICKERS_FILE, st.session_state["custom_tickers"])
                    st.session_state["factsheet_cache"][curr_code]["top35"]['Ticker'] = edited_df['Ticker']
                    save_factsheet_cache(st.session_state["factsheet_cache"])
                    st.rerun()

                total_equity_tracked = edited_df[w].sum()
                st.info(f"💡 Tracking Stocks representing **{total_equity_tracked:.2f}%** of the total fund AUM.")

                st.markdown("---")
                t1, t2 = st.columns([1, 1])
                with t1:
                    st.markdown("##### 🏢 Sector Breakdown")
                    if sec != "None" and sec_df is not None:
                        sec_df[sec] = sec_df[sec].fillna("Other").astype(str)
                        st.plotly_chart(px.treemap(sec_df, path=[sec], values=w, color=w, color_continuous_scale='Electric').update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(t=10,b=10,l=10,r=10)), use_container_width=True)
                with t2:
                    st.markdown("##### Holdings Distribution")
                    st.plotly_chart(px.pie(edited_df, values=w, names=comp, hole=0.55).update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(t=0,b=0,l=0,r=0)), use_container_width=True)
                    
            if st.button("🗑️ Delete & Re-upload (Recommended for 35 Stocks)"):
                del st.session_state["factsheet_cache"][curr_code]
                save_factsheet_cache(st.session_state["factsheet_cache"])
                st.rerun()
        else:
            st.info("No data cached. Please upload file below.")
            f_file = st.file_uploader("Upload Official AMC Portfolio File", type=["xlsx", "xls", "csv"], key=f"up_{curr_code}")
            if f_file:
                try:
                    if f_file.name.endswith(".csv"): df_raw = pd.read_csv(f_file)
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
                        
                        comp = c1.selectbox("Company Col:", ["None"] + list(df.columns), index=(["None"] + list(df.columns)).index(def_comp) if def_comp in ["None"] + list(df.columns) else 0)
                        sec = c2.selectbox("Sector Col (Opt):", ["None"] + list(df.columns), index=(["None"] + list(df.columns)).index(def_sec) if def_sec in ["None"] + list(df.columns) else 0)
                        w = c3.selectbox("Weight Col:", ["None"] + list(df.columns), index=(["None"] + list(df.columns)).index(def_w) if def_w in ["None"] + list(df.columns) else 0)
                        
                        if st.button("🚀 Permanently Lock Data", type="primary"):
                            if comp != "None" and w != "None":
                                clean = df[[comp, w] + ([sec] if sec != "None" else [])].dropna(subset=[comp, w]).copy()
                                clean[w] = pd.to_numeric(clean[w].astype(str).str.replace('%', '', regex=False).str.strip(), errors='coerce')
                                clean = clean.dropna(subset=[w])
                                clean = clean[(clean[w] <= 100) & (~clean[comp].astype(str).str.lower().isin(['total','grand total','equity','debt','cash','portfolio']))]
                                
                                # UPGRADE: Ab Top 35 stocks save honge!
                                top35 = clean.sort_values(w, ascending=False).head(35)
                                top35['Ticker'] = top35[comp].apply(clean_stock_name)
                                
                                sec_df = clean.groupby(sec)[w].sum().reset_index() if sec != "None" else None
                                if sec_df is not None: sec_df = sec_df[sec_df[w] > 0]
                                    
                                st.session_state["factsheet_cache"][curr_code] = {"top35": top35, "comp": comp, "w": w, "sec": sec, "sec_df": sec_df}
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
        if code not in holdings: holdings[code] = {'name': t.get('name', 'Unknown Fund'), 'type': t.get('asset_type', '-'), 'sub_type': t.get('sub_type', '-'), 'lots': []}
        t_action = t.get('type', 'Buy')
        t_date = t.get('date', t.get('buy_date', '2026-01-01'))
        t_nav = t.get('nav', t.get('buy_nav', 0.0))
        t_units = t.get('units', 0.0)
        
        if t_action in ['Buy', 'SIP']:
            try: dt_obj = datetime.strptime(t_date, '%Y-%m-%d')
            except: dt_obj = datetime.today()
            holdings[code]['lots'].append({'date': dt_obj, 'units': float(t_units), 'nav': float(t_nav)})
        elif t_action == 'Sell':
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
        min_date = today
        for lot in data['lots']:
            if lot['units'] > 0:
                total_units += lot['units']
                total_inv += lot['units'] * lot['nav']
                if lot['date'] < min_date: min_date = lot['date']
                if (today - lot['date']).days > 365: ltcg_units += lot['units']
                else: stcg_units += lot['units']
                    
        if total_units > 0.001: 
            live_data = calculate_fund_metrics(code)
            if live_data and live_data.get("Current NAV") and live_data["Current NAV"] > 0: current_nav = live_data["Current NAV"]
            else: current_nav = (total_inv / total_units) if total_units > 0 else 0
                
            current_value = total_units * current_nav
            pnl = current_value - total_inv
            abs_ret = round((pnl / total_inv * 100), 2) if total_inv > 0 else 0
            days_invested = max((today - min_date).days, 1)
            ann_ret = round((((current_value / total_inv) ** (365 / days_invested)) - 1) * 100, 2) if days_invested >= 365 and total_inv > 0 else abs_ret
            
            portfolio_rows.append({
                "Scheme": data['name'], "Type": data['type'], "Sub Type": data['sub_type'],
                "No. Of Unit": round(total_units, 3), "Gross Inv Amt.(₹)": round(total_inv, 2),
                "Current NAV(₹)": round(current_nav, 4), "Current Value(₹)": round(current_value, 2),
                "Unrealised Gain /Loss(₹)": round(pnl, 2), "Ann. Return (%)": ann_ret,
                "Abs. Return (%)": abs_ret, "ST Units": round(stcg_units, 3), "LT Units": round(ltcg_units, 3)
            })

    if portfolio_rows:
        df_port = pd.DataFrame(portfolio_rows)
        tot_inv = df_port["Gross Inv Amt.(₹)"].sum()
        tot_cur = df_port["Current Value(₹)"].sum()
        tot_pnl = df_port["Unrealised Gain /Loss(₹)"].sum()
        tot_pnl_pct = (tot_pnl / tot_inv * 100) if tot_inv > 0 else 0
        df_port["% Holding"] = round((df_port["Current Value(₹)"] / tot_cur) * 100, 2) if tot_cur > 0 else 0
        
        cols = ["Scheme", "Type", "Sub Type", "No. Of Unit", "Gross Inv Amt.(₹)", "Current NAV(₹)", "Current Value(₹)", "Unrealised Gain /Loss(₹)", "Ann. Return (%)", "Abs. Return (%)", "% Holding", "ST Units", "LT Units"]
        st.markdown("#### 📊 Overall Portfolio Summary")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Invested", f"₹ {tot_inv:,.2f}")
        c2.metric("Current Value", f"₹ {tot_cur:,.2f}")
        c3.metric("Total Unrealised P&L (₹)", f"₹ {tot_pnl:,.2f}")
        c4.metric("Total Abs. Return (%)", f"{tot_pnl_pct:.2f} %")
        st.markdown("---")
        st.dataframe(df_port[cols], use_container_width=True, hide_index=True)
    else: st.info("No active holdings found in portfolio.")

    st.markdown("---")
    if st.button("🚨 Clear Entire Portfolio JSON Cache"):
        st.session_state["portfolio"] = []
        save_json(PORTFOLIO_FILE, [])
        st.rerun()

    with st.expander("📁 Bulk Import Trades (CSV/Excel)", expanded=False):
        bulk_file = st.file_uploader("Upload Trades File", type=["csv", "xlsx", "xls"], key="bulk_port_up")
        if bulk_file:
            try:
                df_b = pd.read_csv(bulk_file) if bulk_file.name.endswith(".csv") else pd.read_excel(bulk_file)
                df_b.columns = [str(c).strip() for c in df_b.columns]
                with st.form("bulk_map_form"):
                    cols = ["None"] + list(df_b.columns)
                    c1, c2, c3, c4 = st.columns(4)
                    map_name = c1.selectbox("Scheme (Name)", cols, index=cols.index(next((c for c in df_b.columns if any(k in c.lower() for k in ["name", "fund", "scheme"])), "None")) if next((c for c in df_b.columns if any(k in c.lower() for k in ["name", "fund", "scheme"])), "None") in cols else 0)
                    map_asset = c2.selectbox("Type (Equity/Debt)", cols, index=cols.index(next((c for c in df_b.columns if c.lower() == "type" or "asset" in c.lower()), "None")) if next((c for c in df_b.columns if c.lower() == "type" or "asset" in c.lower()), "None") in cols else 0)
                    map_sub = c3.selectbox("Sub Type (Category)", cols, index=cols.index(next((c for c in df_b.columns if "sub" in c.lower() or "category" in c.lower()), "None")) if next((c for c in df_b.columns if "sub" in c.lower() or "category" in c.lower()), "None") in cols else 0)
                    map_type = c4.selectbox("Transaction Type", cols, index=cols.index(next((c for c in df_b.columns if any(k in c.lower() for k in ["tran", "action", "buy"])), "None")) if next((c for c in df_b.columns if any(k in c.lower() for k in ["tran", "action", "buy"])), "None") in cols else 0)
                    
                    c5, c6, c7 = st.columns(3)
                    map_date = c5.selectbox("Date", cols, index=cols.index(next((c for c in df_b.columns if any(k in c.lower() for k in ["date", "time"])), "None")) if next((c for c in df_b.columns if any(k in c.lower() for k in ["date", "time"])), "None") in cols else 0)
                    map_unit = c6.selectbox("No. Of Unit", cols, index=cols.index(next((c for c in df_b.columns if any(k in c.lower() for k in ["unit", "qty", "quantity"])), "None")) if next((c for c in df_b.columns if any(k in c.lower() for k in ["unit", "qty", "quantity"])), "None") in cols else 0)
                    map_nav = c7.selectbox("Inv. Amt.(₹) or NAV", cols, index=cols.index(next((c for c in df_b.columns if any(k in c.lower() for k in ["nav", "price", "rate", "amt", "amount", "inv"])), "None")) if next((c for c in df_b.columns if any(k in c.lower() for k in ["nav", "price", "rate", "amt", "amount", "inv"])), "None") in cols else 0)
                    
                    if st.form_submit_button("🚀 Process & Import"):
                        if "None" in [map_name, map_unit, map_nav]: st.warning("Please map at least Scheme Name, Units, and NAV/Amount to proceed.")
                        else:
                            success_count = 0
                            failed_funds = set()
                            for _, row in df_b.iterrows():
                                raw_name = str(row[map_name]).strip()
                                raw_lower = raw_name.lower()
                                if raw_lower in ["nan", "none", "", "null"] or "total" in raw_lower or "note" in raw_lower: continue
                                clean_name = raw_name.split('-')[0].strip().lower()
                                match = all_schemes[all_schemes['search_term'].str.contains(clean_name, regex=False, na=False)]
                                if not match.empty:
                                    if "idcw" not in raw_lower and "div" not in raw_lower:
                                        no_idcw = match[~match['search_term'].str.contains("idcw|dividend|payout|reinvestment", regex=True)]
                                        if not no_idcw.empty: match = no_idcw
                                    if "gr" in raw_lower or "growth" in raw_lower:
                                        gr_match = match[match['search_term'].str.contains("growth", regex=False)]
                                        if not gr_match.empty: match = gr_match
                                    if "dir" not in raw_lower and "direct" not in raw_lower:
                                        reg_match = match[match['search_term'].str.contains("regular", regex=False)]
                                        if not reg_match.empty: match = reg_match
                                    sc_code = int(match.iloc[0]['schemeCode'])
                                    if sc_code not in st.session_state["watchlist"]: st.session_state["watchlist"].append(sc_code)
                                    try: dt_parsed = pd.to_datetime(row[map_date]).strftime('%Y-%m-%d') if map_date != "None" and pd.notna(row[map_date]) else datetime.today().strftime('%Y-%m-%d')
                                    except: dt_parsed = datetime.today().strftime('%Y-%m-%d')
                                    try:
                                        r_units, r_nav = float(row[map_unit]), float(row[map_nav])
                                        if pd.isna(r_units) or pd.isna(r_nav) or r_units <= 0: continue
                                        if r_nav > 5000 and (r_nav / r_units) < 5000: r_nav = round(r_nav / r_units, 4)
                                        st.session_state["portfolio"].append({
                                            "code": sc_code, "name": match.iloc[0]['schemeName'], 
                                            "asset_type": str(row[map_asset]) if map_asset != "None" else "Equity",
                                            "sub_type": str(row[map_sub]) if map_sub != "None" else "-",
                                            "type": "Sell" if map_type != "None" and "sell" in str(row[map_type]).lower() else "Buy",
                                            "date": dt_parsed, "units": r_units, "nav": r_nav
                                        })
                                        success_count += 1
                                    except: pass
                                else: failed_funds.add(raw_name)
                            save_json(WATCHLIST_FILE, st.session_state["watchlist"])
                            save_json(PORTFOLIO_FILE, st.session_state["portfolio"])
                            if success_count > 0:
                                st.success(f"✅ Imported {success_count} holdings.")
                                st.rerun()
                            else: st.error("No valid trades imported.")
            except Exception as e: st.error(f"Error reading file: {str(e)}")

with tab4:
    st.markdown("### 📈 Institutional Fund Analysis")
    if st.session_state["watchlist"]:
        f_dict = { (all_schemes[all_schemes["schemeCode"] == c]["schemeName"].iloc[0] if not all_schemes[all_schemes["schemeCode"] == c].empty else str(c)) : c for c in st.session_state["watchlist"] }
        compare_funds = st.multiselect("Select Funds for Head-to-Head Comparison:", list(f_dict.keys()), default=list(f_dict.keys())[:2])
        if compare_funds:
            with st.spinner("Crunching historical data..."):
                hist_data = {f_name: get_historical_nav(f_dict[f_name])['data'] for f_name in compare_funds if get_historical_nav(f_dict[f_name])}
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
                            m = calculate_fund_metrics(f_dict[f_name])
                            if m and m["3-Year CAGR (%)"] and m["Volatility (%)"]: scatter_data.append({"Fund": f_name[:25], "CAGR": m["3-Year CAGR (%)"], "Risk (Vol)": m["Volatility (%)"]})
                        if scatter_data:
                            fig_sc = px.scatter(pd.DataFrame(scatter_data), x="Risk (Vol)", y="CAGR", text="Fund", size_max=60, color="Fund")
                            fig_sc.update_traces(textposition='top center')
                            fig_sc.update_layout(template="plotly_dark", margin=dict(l=0, r=0, t=30, b=0))
                            st.plotly_chart(fig_sc, use_container_width=True)
                        else: st.warning("Not enough 3-year data.")
    else: st.info("Watchlist me funds add karein analysis ke liye.")
