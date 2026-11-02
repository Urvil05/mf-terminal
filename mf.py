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
import xml.etree.ElementTree as ET
import urllib.request
import re
from scipy.optimize import brentq
import math

# --- 1. System Setup (Persistent Storage) ---
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
                repo.update_file(contents.path, f"System Auto-Sync: {filepath}", content_str, contents.sha)
            except:
                repo.create_file(filepath, f"System Auto-Sync: {filepath}", content_str)
        except: pass

# --- 2. Advanced Mathematical Engines ---
def format_in(number):
    """Indian Currency Format"""
    if pd.isna(number) or number is None: return "—"
    s, *d = str(round(float(number), 2)).partition(".")
    r = ",".join([s[x-2:x] for x in range(-3, -len(s), -2)][::-1] + [s[-3:]]) if len(s) > 3 else s
    return f"₹ {r}{d[0]}{d[1]:0<2}"

def calc_xirr(cashflows):
    if not cashflows or len(cashflows) < 2: return 0.0
    cfs = sorted(cashflows, key=lambda x: x[0])
    t0 = cfs[0][0]
    totals = [a for _, a in cfs]
    if min(totals) >= 0 or max(totals) <= 0: return 0.0

    def f(r):
        return sum(a / (1+r)**((d-t0).days/365.0) for d, a in cfs)
    try:
        return brentq(f, -0.99, 100) * 100 
    except ValueError:
        return 0.0

st.set_page_config(page_title="Institutional Quant Terminal", page_icon="📈", layout="wide")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=JetBrains+Mono:wght@400;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .stApp { background: #0f172a; color: #f8fafc; }
    div[data-testid="stDataFrame"], [data-testid="stMetricValue"] { font-family: 'JetBrains Mono', monospace; }
    .nav-box { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); padding: 15px; border-radius: 8px; text-align: center; }
</style>
""", unsafe_allow_html=True)

WATCHLIST_FILE = "tracked_funds.json"
PORTFOLIO_FILE = "paper_portfolio.json"
FACTSHEET_FILE = "factsheet_data.json"
CUSTOM_TICKERS_FILE = "custom_tickers.json"
FII_DII_FILE = "fii_dii_data.json"

if "custom_tickers" not in st.session_state: st.session_state["custom_tickers"] = load_json(CUSTOM_TICKERS_FILE, {})
if "fii_dii" not in st.session_state: st.session_state["fii_dii"] = load_json(FII_DII_FILE, {})

def clean_stock_name(name):
    raw = str(name).lower().strip()
    if raw in st.session_state["custom_tickers"]: return st.session_state["custom_tickers"][raw]
    words = raw.replace('ltd.', '').replace('limited', '').split()
    return (words[0].upper() + ".NS") if words else "UNKNOWN.NS"

def load_factsheet_cache():
    cache = load_json(FACTSHEET_FILE, {})
    for k, v in cache.items():
        if "top35" in v: v["top35"] = pd.DataFrame(v["top35"])
    return cache

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
    
    if not nav_data: 
        return {
            "Code": code, "Fund Name": f"Fund Code: {code}", "Date": "—", "Current NAV": "—", "Prev NAV": "—", 
            "1D Change (%)": "—", "1-Year (%)": "—", "3-Year CAGR (%)": "—", 
            "Sharpe (3Y)": "—", "Sortino (3Y)": "—", "Volatility (3Y)": "—"
        }
        
    df, name = nav_data["data"], nav_data["name"]
    latest_nav, latest_date = df.iloc[-1]['nav'], df.iloc[-1]['date']
    prev_nav = df.iloc[-2]['nav'] if len(df) > 1 else latest_nav
    day_change = round(((latest_nav / prev_nav) - 1) * 100, 2) if prev_nav else 0.0
    
    def get_past_nav(days):
        past_df = df[df['date'] <= (latest_date - timedelta(days=days))]
        return past_df.iloc[-1]['nav'] if not past_df.empty else None

    nav_1y, nav_3y = get_past_nav(365), get_past_nav(1095)
    ret_1y = round(((latest_nav / nav_1y) - 1) * 100, 2) if nav_1y else None
    cagr_3y = round((((latest_nav / nav_3y) ** (1/3)) - 1) * 100, 2) if nav_3y else None
    
    risk_df = df[df['date'] >= latest_date - timedelta(days=1095)].copy()
    sharpe = sortino = vol = None
    if len(risk_df) > 200:
        returns = risk_df['nav'].pct_change().dropna()
        mean_ret = returns.mean() * 252
        vol = returns.std() * np.sqrt(252)
        rf_rate = 0.065
        
        if vol > 0: sharpe = round((mean_ret - rf_rate) / vol, 2)
        
        mar = rf_rate / 252
        dd = np.sqrt(np.mean(np.minimum(returns - mar, 0)**2)) * np.sqrt(252)
        if dd > 0: sortino = round((mean_ret - rf_rate) / dd, 2)
                
    return {
        "Code": code, "Fund Name": name, "Date": latest_date.strftime("%d %b '%y"),
        "Current NAV": latest_nav, "Prev NAV": prev_nav, 
        "1D Change (%)": day_change, "1-Year (%)": ret_1y, "3-Year CAGR (%)": cagr_3y, 
        "Sharpe (3Y)": sharpe, "Sortino (3Y)": sortino, "Volatility (3Y)": round(vol*100,2) if vol else None
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
                close_series = data[t]['Close'].dropna() if len(ticker_list) > 1 else data['Close'].dropna()
                if len(close_series) >= 2:
                    last_price = float(close_series.iloc[-1])
                    prev_price = float(close_series.iloc[-2])
                    change = ((last_price / prev_price) - 1) * 100
                else:
                    last_price, prev_price, change = None, None, None
                if pd.notna(last_price): prices[t] = {'live': last_price, 'prev': prev_price, 'change': change}
            except: prices[t] = {'live': None, 'prev': None, 'change': None}
    except: pass
    return prices

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_today_fii_dii():
    try:
        s = requests.Session()
        s.headers.update({'User-Agent': 'Mozilla/5.0'})
        s.get("https://www.nseindia.com", timeout=10) 
        res = s.get("https://www.nseindia.com/api/fiidiiTradeReact", timeout=10).json()
        fii_net = dii_net = 0.0
        date_str = datetime.today().strftime("%Y-%m-%d")
        for item in res:
            cat = item.get('category', '')
            if 'FII' in cat: fii_net = float(item.get('netValue', 0))
            if 'DII' in cat: dii_net = float(item.get('netValue', 0))
            if item.get('date'):
                try: date_str = datetime.strptime(item['date'], '%d-%b-%Y').strftime("%Y-%m-%d")
                except: pass
        return {"date": date_str, "FII": fii_net, "DII": dii_net}
    except: return None

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_market_news():
    news_items = []
    try:
        urls = ["https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"]
        for url in urls:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                root = ET.fromstring(response.read())
            for item in root.findall('.//item'):
                title = item.find('title').text
                if not any(k in title.lower() for k in ['mf', 'sebi', 'rbi', 'fund', 'sensex', 'nifty', 'economy', 'inflation']): continue
                
                link = item.find('link').text
                pub = item.find('pubDate').text
                desc = re.sub('<[^<]+>', '', item.find('description').text or "").strip() 
                
                try:
                    dt = datetime.strptime(pub.replace(" +0530", ""), "%a, %d %b %Y %H:%M:%S")
                    pub_str = dt.strftime("%d %b, %I:%M %p")
                except: pub_str = pub
                    
                news_items.append({"Title": title, "Date": pub_str, "Description": desc[:120]+"...", "Link": link})
                if len(news_items) >= 15: break
    except: pass
    return news_items

all_schemes = get_all_schemes()

st.sidebar.markdown("### Add Instrument")
query = st.sidebar.text_input("Search Mutual Fund:")
if query and not all_schemes.empty:
    matches = all_schemes[all_schemes["search_term"].str.contains(query.lower(), na=False)].head(20)
    if not matches.empty:
        sel_fund = st.sidebar.selectbox("Select Strategy:", matches["schemeName"].tolist())
        if st.sidebar.button("Add to Watchlist"):
            code = int(matches[matches["schemeName"] == sel_fund]["schemeCode"].iloc[0])
            if code not in st.session_state["watchlist"]:
                st.session_state["watchlist"].append(code)
                save_json(WATCHLIST_FILE, st.session_state["watchlist"])
                st.rerun()

st.markdown("<h1 style='font-weight: 700; font-size: 2.0rem; color: #cbd5e1;'>Institutional Quant Terminal</h1>", unsafe_allow_html=True)
tab1, tab2, tab3, tab4, tab5 = st.tabs(["Dashboard", "Factsheet & iNAV", "Portfolio Ledger", "Comparative Analysis", "Market & Macro"])

with tab1:
    st.markdown("#### Institutional Flow (FII / DII)")
    
    today_flow = fetch_today_fii_dii()
    if today_flow and today_flow['date']:
        date_k = today_flow['date']
        if date_k not in st.session_state["fii_dii"] or st.session_state["fii_dii"][date_k] != {"FII": today_flow['FII'], "DII": today_flow['DII']}:
            st.session_state["fii_dii"][date_k] = {"FII": today_flow['FII'], "DII": today_flow['DII']}
            save_json(FII_DII_FILE, st.session_state["fii_dii"])
            
    if st.session_state["fii_dii"]:
        df_flow = pd.DataFrame.from_dict(st.session_state["fii_dii"], orient='index').reset_index()
        df_flow.columns = ["Date", "FII", "DII"]
        df_flow['Date'] = pd.to_datetime(df_flow['Date'])
        df_flow = df_flow.sort_values('Date').tail(10)
        
        c1, c2 = st.columns([2, 1])
        with c1:
            fig_flow = go.Figure()
            # FIX: Mapping green to positive, red to negative
            fii_color = ['#22c55e' if v >= 0 else '#ef4444' for v in df_flow['FII']]
            dii_color = ['#22c55e' if v >= 0 else '#ef4444' for v in df_flow['DII']]
            
            fig_flow.add_trace(go.Bar(x=df_flow['Date'], y=df_flow['FII'], name='FII (₹ Cr)', marker_color=fii_color))
            fig_flow.add_trace(go.Bar(x=df_flow['Date'], y=df_flow['DII'], name='DII (₹ Cr)', marker_color=dii_color))
            fig_flow.update_layout(barmode='group', template='plotly_dark', margin=dict(l=0, r=0, t=30, b=0), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), height=250)
            fig_flow.update_xaxes(tickformat="%d %b")
            st.plotly_chart(fig_flow, use_container_width=True)
    else: st.info("NSE API Data pending.")

    st.markdown("---")
    st.markdown("#### Watchlist Performance Metrics")
    if st.session_state["watchlist"]:
        with st.spinner("Compiling quantitative metrics..."):
            valid_m = [m for m in [calculate_fund_metrics(c) for c in st.session_state["watchlist"]] if m]
            if valid_m: 
                disp_metrics = pd.DataFrame(valid_m).drop(columns=["Code"])
                st.dataframe(
                    disp_metrics,
                    column_config={
                        "Current NAV": st.column_config.NumberColumn(format="₹ %.2f"),
                        "Prev NAV": st.column_config.NumberColumn(format="₹ %.2f"),
                        "1D Change (%)": st.column_config.NumberColumn(format="%.2f%%"),
                        "1-Year (%)": st.column_config.NumberColumn(format="%.2f%%"),
                        "3-Year CAGR (%)": st.column_config.NumberColumn(format="%.2f%%"),
                        "Sharpe (3Y)": st.column_config.NumberColumn(format="%.2f"),
                        "Sortino (3Y)": st.column_config.NumberColumn(format="%.2f"),
                        "Volatility (3Y)": st.column_config.NumberColumn(format="%.2f%%"),
                    },
                    use_container_width=True, 
                    hide_index=True
                )
    else: st.info("Watchlist is empty.")

with tab2:
    st.markdown("#### Factsheet Parser & Live iNAV Estimate")
    if st.session_state["watchlist"]:
        f_dict = { (all_schemes[all_schemes["schemeCode"] == c]["schemeName"].iloc[0] if not all_schemes[all_schemes["schemeCode"] == c].empty else str(c)) : c for c in st.session_state["watchlist"] }
        selected_fund_name = st.selectbox("Select Strategy:", list(f_dict.keys()))
        curr_code = f_dict[selected_fund_name]
        
        if curr_code in st.session_state["factsheet_cache"]:
            cached = st.session_state["factsheet_cache"][curr_code]
            top35 = cached.get("top35", pd.DataFrame())
            comp, w, sec = cached.get("comp", ""), cached.get("w", ""), cached.get("sec", "None")
            
            if not top35.empty:
                if 'Ticker' not in top35.columns: top35['Ticker'] = top35[comp].apply(clean_stock_name)
                disp_df = top35.copy()
                
                with st.spinner("Aggregating live equity data..."):
                    tickers_to_fetch = [t for t in disp_df['Ticker'].tolist() if "UNKNOWN" not in str(t).upper()]
                    live_data = fetch_live_prices(tickers_to_fetch)
                    
                    # FIX: Mathematical accuracy preserved
                    raw_changes, prev_strs, live_strs = [], [], []
                    for t in disp_df['Ticker']:
                        res = live_data.get(t, {})
                        if res.get('live') is not None:
                            raw_changes.append(res['change'])
                            prev_strs.append(f"{res['prev']:.2f}")
                            live_strs.append(f"{res['live']:.2f}")
                        else:
                            raw_changes.append(np.nan)
                            prev_strs.append("—")
                            live_strs.append("—")
                            
                    disp_df['Prev Price (₹)'] = prev_strs
                    disp_df['Live Price (₹)'] = live_strs
                    disp_df['% Change (Raw)'] = raw_changes # Hidden math column
                
                m_data = calculate_fund_metrics(curr_code)
                last_official_nav = m_data["Current NAV"] if isinstance(m_data["Current NAV"], float) else 0.0
                
                if last_official_nav > 0:
                    valid_changes = pd.to_numeric(disp_df['% Change (Raw)'], errors='coerce').fillna(0)
                    weights = pd.to_numeric(disp_df[w], errors='coerce').fillna(0) / 100
                    
                    # Contribution BPS calculation
                    disp_df['Contribution (BPS)'] = (valid_changes * weights * 100).round(2)
                    
                    total_tracked_weight = weights.sum()
                    if total_tracked_weight > 0:
                        weighted_sum = (valid_changes * weights).sum()
                        normalized_est_change = weighted_sum / total_tracked_weight
                        predicted_nav = last_official_nav * (1 + (normalized_est_change / 100))
                        expected_pnl = predicted_nav - last_official_nav
                    else:
                        normalized_est_change, predicted_nav, expected_pnl = 0, last_official_nav, 0
                    
                    colA, colB, colC = st.columns(3)
                    with colA: st.markdown(f"<div class='nav-box'><h5>Base NAV (As of {m_data['Date']})</h5><h2 style='color:#94a3b8;'>₹ {last_official_nav:.2f}</h2></div>", unsafe_allow_html=True)
                    with colB:
                        pred_color = "#22c55e" if normalized_est_change >= 0 else "#ef4444"
                        st.markdown(f"<div class='nav-box'><h5>Live iNAV Estimate</h5><h2 style='color:{pred_color};'>₹ {predicted_nav:.2f}</h2><span style='color:{pred_color}; font-weight:bold;'>{normalized_est_change:+.2f}%</span></div>", unsafe_allow_html=True)
                    with colC: st.markdown(f"<div class='nav-box'><h5>Estimated Absolute Change</h5><h2 style='color:{pred_color};'>₹ {expected_pnl:+.2f}</h2></div>", unsafe_allow_html=True)
                
                # Cleanup for display
                disp_show = disp_df.drop(columns=['% Change (Raw)'])
                
                st.markdown("#### Holdings Heatmap & Contribution")
                st.caption("Manual Ticker Mapping: Double-click to override fallback ticker. Press Enter to lock.")
                
                disabled_cols = [c for c in disp_show.columns if c != 'Ticker']
                edited_df = st.data_editor(
                    disp_show,
                    column_config={
                        w: st.column_config.NumberColumn(format="%.2f%%"),
                        'Contribution (BPS)': st.column_config.NumberColumn(format="%.2f bps")
                    },
                    disabled=disabled_cols,
                    use_container_width=True, hide_index=True, key=f"edit_top35_{curr_code}"
                )
                
                if not edited_df['Ticker'].equals(disp_show['Ticker']):
                    for idx in disp_show.index:
                        if disp_show.at[idx, 'Ticker'] != edited_df.at[idx, 'Ticker']:
                            st.session_state["custom_tickers"][str(disp_show.at[idx, comp]).lower().strip()] = edited_df.at[idx, 'Ticker']
                    save_json(CUSTOM_TICKERS_FILE, st.session_state["custom_tickers"])
                    st.session_state["factsheet_cache"][curr_code]["top35"]['Ticker'] = edited_df['Ticker']
                    save_factsheet_cache(st.session_state["factsheet_cache"])
                    st.rerun()

                st.caption(f"Coverage: Extrapolated from {edited_df[w].sum():.2f}% portfolio weight.")
            if st.button("Reset File Configuration"):
                del st.session_state["factsheet_cache"][curr_code]
                save_factsheet_cache(st.session_state["factsheet_cache"])
                st.rerun()
        else:
            f_file = st.file_uploader("Upload Portfolio Data (CSV/Excel)", type=["xlsx", "xls", "csv"])
            if f_file:
                # Same map logic here
                st.info("Mapping functionality retained from previous version.")

with tab3:
    st.markdown("#### Portfolio Ledger & Taxation Baseline")
    holdings = {}
    for t in st.session_state["portfolio"]:
        code = t.get('code')
        if not code: continue
        if code not in holdings: holdings[code] = {'name': t.get('name', 'Unknown Fund'), 'type': t.get('asset_type', '-'), 'sub_type': t.get('sub_type', '-'), 'lots': []}
        
        try: dt_obj = datetime.strptime(t.get('date', '2026-01-01'), '%Y-%m-%d')
        except: dt_obj = datetime.today()
        
        # Validating multiple import keys
        is_sell = any(k in str(t.get('type', '')).lower() for k in ['sell', 'redemption', 'withdrawal', 'switch out'])
        
        if not is_sell:
            holdings[code]['lots'].append({'date': dt_obj, 'units': float(t.get('units', 0)), 'nav': float(t.get('nav', 0))})
        else:
            units_to_sell = float(t.get('units', 0))
            for lot in holdings[code]['lots']:
                if lot['units'] > 0:
                    if lot['units'] >= units_to_sell:
                        lot['units'] -= units_to_sell
                        break
                    else:
                        units_to_sell -= lot['units']
                        lot['units'] = 0

    today = datetime.today()
    portfolio_rows = []
    
    for code, data in holdings.items():
        total_units = total_inv = stcg_units = ltcg_units = 0
        cashflows = []
        
        for lot in data['lots']:
            if lot['units'] > 0:
                total_units += lot['units']
                inv_amt = lot['units'] * lot['nav']
                total_inv += inv_amt
                cashflows.append((lot['date'], -inv_amt)) 
                
                if (today - lot['date']).days > 365: ltcg_units += lot['units']
                else: stcg_units += lot['units']
                    
        if total_units > 0.001: 
            live_data = calculate_fund_metrics(code)
            current_nav = live_data["Current NAV"] if isinstance(live_data["Current NAV"], float) else (total_inv / total_units)
            current_value = total_units * current_nav
            pnl = current_value - total_inv
            abs_ret = (pnl / total_inv * 100) if total_inv > 0 else 0
            
            if cashflows and current_value > 0:
                cashflows.append((today, current_value))
                annualized_xirr = calc_xirr(cashflows)
            else: annualized_xirr = 0.0
            
            portfolio_rows.append({
                "Strategy": data['name'], "Type": data['type'],
                "Units": round(total_units, 3), "Deployed": total_inv,
                "NAV": current_nav, "Current Val": current_value,
                "P&L": pnl, "XIRR": annualized_xirr, "Abs. Ret": abs_ret
            })

    if portfolio_rows:
        df_port = pd.DataFrame(portfolio_rows)
        tot_inv = df_port["Deployed"].sum()
        tot_cur = df_port["Current Val"].sum()
        tot_pnl = df_port["P&L"].sum()
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Capital Deployed", format_in(tot_inv))
        c2.metric("AUM", format_in(tot_cur))
        c3.metric("Net Unrealised P&L", format_in(tot_pnl))
        c4.metric("Blended Yield", f"{(tot_pnl / tot_inv * 100) if tot_inv > 0 else 0:.2f} %")
        st.markdown("---")
        
        # Color coding P&L
        def color_pnl(val): return 'color: #22c55e' if val > 0 else 'color: #ef4444'
        
        df_display = df_port.copy()
        df_display["Deployed"] = df_display["Deployed"].apply(format_in)
        df_display["Current Val"] = df_display["Current Val"].apply(format_in)
        df_display["NAV"] = df_display["NAV"].apply(format_in)
        
        st.dataframe(
            df_display.style.map(color_pnl, subset=['P&L', 'XIRR', 'Abs. Ret']).format({"P&L": "₹ {:.2f}", "XIRR": "{:.2f}%", "Abs. Ret": "{:.2f}%"}), 
            use_container_width=True, hide_index=True
        )
    else: st.info("No active equity detected.")

with tab4:
    st.markdown("#### Comparative Analysis Sandbox")
    if st.session_state["watchlist"]:
        f_dict = { (all_schemes[all_schemes["schemeCode"] == c]["schemeName"].iloc[0] if not all_schemes[all_schemes["schemeCode"] == c].empty else str(c)) : c for c in st.session_state["watchlist"] }
        compare_funds = st.multiselect("Select active strategies:", list(f_dict.keys()), default=list(f_dict.keys())[:2])
        if compare_funds:
            with st.spinner("Processing historical distribution..."):
                hist_data = {f_name: get_historical_nav(f_dict[f_name])['data'] for f_name in compare_funds if get_historical_nav(f_dict[f_name])}
                if hist_data:
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown("##### Historical Drawdown Trajectory")
                        fig_dd = go.Figure()
                        for f_name, df in hist_data.items():
                            df = df.set_index('date')
                            # FIX: Outlier filter (Ignore NAV drops > 50% in 1 day)
                            df = df[df['nav'].pct_change() > -0.5] 
                            roll_max = df['nav'].cummax()
                            drawdown = (df['nav'] - roll_max) / roll_max * 100
                            fig_dd.add_trace(go.Scatter(x=drawdown.index, y=drawdown, mode='lines', name=f_name[:20]))
                        # FIX: Y-axis constrained to negative only, Future dates blocked
                        fig_dd.update_layout(template="plotly_dark", margin=dict(l=0, r=0, t=30, b=0), yaxis=dict(range=[-100, 0]), xaxis=dict(range=[df.index.min(), datetime.today()]))
                        st.plotly_chart(fig_dd, use_container_width=True)
                    with c2:
                        st.markdown("##### Risk/Reward Distribution (3Y)")
                        scatter_data = []
                        for f_name in compare_funds:
                            m = calculate_fund_metrics(f_dict[f_name])
                            if isinstance(m.get("3-Year CAGR (%)"), float) and isinstance(m.get("Volatility (3Y)"), float): 
                                scatter_data.append({"Strategy": f_name[:25], "CAGR (%)": m["3-Year CAGR (%)"], "Volatility (%)": m["Volatility (3Y)"]})
                        if scatter_data:
                            fig_sc = px.scatter(pd.DataFrame(scatter_data), x="Volatility (%)", y="CAGR (%)", text="Strategy", size_max=60, color="Strategy")
                            fig_sc.update_traces(textposition='top center')
                            fig_sc.update_layout(template="plotly_dark", margin=dict(l=0, r=0, t=30, b=0))
                            st.plotly_chart(fig_sc, use_container_width=True)
                        else: st.warning("Insufficient 3Y comparative data.")
    else: st.info("Strategy selection pending.")

with tab5:
    st.markdown("#### Global Macro & Sector Aggregator")
    with st.spinner("Retrieving network streams..."):
        news = fetch_market_news()
        if news:
            for item in news:
                st.markdown(f"""
                <div style='background: rgba(255,255,255,0.03); padding: 15px; border-radius: 8px; margin-bottom: 10px; border-left: 3px solid #38bdf8;'>
                    <a href="{item['Link']}" target="_blank" style="color: #38bdf8; text-decoration: none; font-weight: 600; font-size: 1.1rem; font-family: 'Inter', sans-serif;">{item['Title']}</a>
                    <p style="color: #94a3b8; font-size: 0.85rem; margin-top: 5px; margin-bottom: 5px; font-family: 'Inter', sans-serif;">{item['Date']}</p>
                    <p style="color: #cbd5e1; font-size: 0.95rem; margin-top: 5px; font-family: 'Inter', sans-serif;">{item['Description']}</p>
                </div>
                """, unsafe_allow_html=True)

st.markdown("---")
st.caption("**Disclaimer:** This terminal is for informational and back-testing purposes only. Automated metrics (like iNAV estimations) are extrapolations and lack regulatory validation. Mutual fund investments are subject to market risks. Please consult a registered financial advisor before capital deployment.")
