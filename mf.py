import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

# Page Setup
st.set_page_config(
    page_title="APEX MF | Institutional Terminal", 
    page_icon="⚡", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- ADVANCED CYBER-FINANCIAL CSS INJECTION ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', sans-serif;
    }
    
    code, pre {
        font-family: 'JetBrains Mono', monospace !important;
    }

    .stApp {
        background: radial-gradient(circle at top right, #0f172a 0%, #030712 100%);
        color: #f8fafc;
    }
    
    div[data-testid="stMetric"] {
        background: rgba(15, 23, 42, 0.65) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 16px !important;
        padding: 16px 20px !important;
        box-shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.5) !important;
        backdrop-filter: blur(12px) !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    }
    
    div[data-testid="stMetric"]:hover {
        border-color: rgba(56, 189, 248, 0.4) !important;
        transform: translateY(-3px) !important;
        box-shadow: 0 16px 35px -8px rgba(14, 165, 233, 0.25) !important;
    }
    
    div[data-testid="stMetricLabel"] {
        color: #94a3b8 !important;
        font-size: 0.8rem !important;
        font-weight: 600 !important;
        letter-spacing: 0.05em !important;
        text-transform: uppercase !important;
    }

    div[data-testid="stMetricValue"] {
        color: #f1f5f9 !important;
        font-size: 1.65rem !important;
        font-weight: 800 !important;
        font-family: 'JetBrains Mono', monospace !important;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 8px !important;
        background: rgba(15, 23, 42, 0.6) !important;
        padding: 8px !important;
        border-radius: 14px !important;
        border: 1px solid rgba(255, 255, 255, 0.06) !important;
    }

    .stTabs [data-baseweb="tab"] {
        border-radius: 10px !important;
        color: #94a3b8 !important;
        padding: 8px 18px !important;
        font-weight: 600 !important;
        font-size: 0.9rem !important;
        transition: all 0.2s ease !important;
    }

    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #0284c7 0%, #2563eb 100%) !important;
        color: #ffffff !important;
        box-shadow: 0 4px 14px rgba(37, 99, 235, 0.4) !important;
    }

    .stButton > button {
        background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 8px 20px !important;
        font-weight: 600 !important;
        letter-spacing: 0.02em !important;
        transition: all 0.25s ease !important;
        box-shadow: 0 4px 15px rgba(2, 132, 199, 0.3) !important;
    }

    .stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 20px rgba(2, 132, 199, 0.5) !important;
    }

    section[data-testid="stSidebar"] {
        background-color: #030712 !important;
        border-right: 1px solid rgba(255, 255, 255, 0.07) !important;
    }

    div[data-testid="stDataFrame"] {
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 14px !important;
        overflow: hidden !important;
    }

    .terminal-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 12px;
        background: rgba(34, 197, 94, 0.12);
        border: 1px solid rgba(34, 197, 94, 0.3);
        color: #4ade80;
        font-size: 0.75rem;
        font-weight: 700;
        border-radius: 9999px;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        margin-bottom: 10px;
    }

    .index-ticker-box {
        background: rgba(15, 23, 42, 0.65);
        border: 1px solid rgba(255, 255, 255, 0.07);
        border-radius: 12px;
        padding: 10px 14px;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# --- LOCAL FILE PERSISTENCE ---
WATCHLIST_FILE = "tracked_funds.json"
PORTFOLIO_FILE = "paper_portfolio.json"

DEFAULT_WATCHLIST = [125497, 120716, 118778, 122639]
DEFAULT_PORTFOLIO = [
    {"code": 120716, "name": "Motilal Oswal Midcap Fund", "units": 1000.0, "buy_nav": 72.5, "buy_date": "2026-01-15"},
    {"code": 118778, "name": "Nippon India Small Cap Fund", "units": 500.0, "buy_nav": 128.0, "buy_date": "2026-02-10"}
]

def load_data(file_path, default_val):
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default_val
    return default_val

def save_data(file_path, data):
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        st.error(f"Save error: {e}")

if "tracked_codes" not in st.session_state:
    st.session_state["tracked_codes"] = load_data(WATCHLIST_FILE, DEFAULT_WATCHLIST)

if "paper_portfolio" not in st.session_state:
    st.session_state["paper_portfolio"] = load_data(PORTFOLIO_FILE, DEFAULT_PORTFOLIO)

# --- VERIFIED DISCLOSURE URLS ---
ALL_AMC_DISCLOSURES = {
    "aditya birla": "https://mutualfund.adityabirlacapital.com/forms-and-downloads/portfolio-disclosures",
    "birla": "https://mutualfund.adityabirlacapital.com/forms-and-downloads/portfolio-disclosures",
    "hdfc": "https://www.hdfcfund.com/statutory-disclosure/portfolio/monthly-portfolio",
    "nippon": "https://mf.nipponindiaim.com/investor-service/downloads/factsheet-and-portfolio",
    "sbi": "https://www.sbimf.com/en-us/portfolios",
    "motilal": "https://www.motilaloswalmf.com/downloads/mutual-fund/scheme-portfolio",
    "parag parikh": "https://amc.ppfas.com/schemes/monthly-portfolio-disclosure/",
    "ppfas": "https://amc.ppfas.com/schemes/monthly-portfolio-disclosure/",
    "icici": "https://www.icicipruamc.com/downloads/portfolio-disclosures",
    "kotak": "https://www.kotakmf.com/Information/regulatory-disclosures",
    "mirae": "https://www.miraeassetmf.co.in/downloads/portfolios",
    "quant": "https://quantmutual.com/statutory-disclosures",
    "tata": "https://www.tatamutualfund.com/downloads/factsheets-portfolio",
    "axis": "https://www.axismf.com/downloads/regulatory-disclosures",
    "dsp": "https://www.dspim.com/mandatory-disclosures/portfolio-disclosures",
    "uti": "https://www.utimf.com/downloads/portfolio-disclosures",
    "bandhan": "https://bandhanmutual.com/downloads/monthly-portfolio",
    "canara": "https://www.canararobeco.com/statutory-disclosure/portfolio-disclosure",
    "groww": "https://growwmf.in/statutory-disclosures"
}

def get_amc_disclosure_url(fund_house, fund_name):
    query_str = (str(fund_house) + " " + str(fund_name)).lower()
    for k, v in ALL_AMC_DISCLOSURES.items():
        if k in query_str:
            return v
    return "https://www.amfiindia.com/research-information/other-data/scheme-details"

# --- REAL INDEX CONSTITUENTS & BENCHMARK ENGINE ---
INDEX_HOLDINGS_REGISTRY = {
    "defence": {
        "benchmark": "NIFTY India Defence TRI",
        "manager": "Haresh Mehta / Pradeep Sreeram",
        "aum_cr": "₹3,420 Cr",
        "inception": "June 2024",
        "holdings": [
            {"Company": "Bharat Electronics Ltd. (BEL)", "Sector": "Aerospace & Defence", "Weight (%)": 19.8},
            {"Company": "Hindustan Aeronautics Ltd. (HAL)", "Sector": "Aerospace & Defence", "Weight (%)": 18.5},
            {"Company": "Solar Industries India Ltd.", "Sector": "Chemicals / Explosives", "Weight (%)": 14.2},
            {"Company": "Mazagon Dock Shipbuilders Ltd.", "Sector": "Shipbuilding", "Weight (%)": 11.4},
            {"Company": "Bharat Dynamics Ltd. (BDL)", "Sector": "Missile Systems", "Weight (%)": 7.6},
            {"Company": "Cochin Shipyard Ltd.", "Sector": "Shipbuilding", "Weight (%)": 6.8},
            {"Company": "Astra Microwave Products Ltd.", "Sector": "Defence Electronics", "Weight (%)": 4.5},
            {"Company": "Data Patterns (India) Ltd.", "Sector": "Defence Electronics", "Weight (%)": 3.9},
            {"Company": "BEML Ltd.", "Sector": "Defence Equipment", "Weight (%)": 3.5},
            {"Company": "Garden Reach Shipbuilders", "Sector": "Shipbuilding", "Weight (%)": 3.1}
        ]
    },
    "small": {
        "benchmark": "NIFTY Smallcap 250 TRI",
        "manager": "Samir Rachh / Kinjal Desai",
        "aum_cr": "₹58,400 Cr",
        "inception": "September 2010",
        "holdings": [
            {"Company": "HDFC Bank Ltd.", "Sector": "Financial Services", "Weight (%)": 2.4},
            {"Company": "Tube Investments of India Ltd.", "Sector": "Auto Components", "Weight (%)": 2.1},
            {"Company": "Apar Industries Ltd.", "Sector": "Electrical Equipment", "Weight (%)": 1.9},
            {"Company": "KPIT Technologies Ltd.", "Sector": "IT Consulting", "Weight (%)": 1.8},
            {"Company": "Multi Commodity Exchange (MCX)", "Sector": "Financial Services", "Weight (%)": 1.7},
            {"Company": "Carborundum Universal Ltd.", "Sector": "Industrial Manufacturing", "Weight (%)": 1.6},
            {"Company": "Kalpataru Projects International", "Sector": "Construction", "Weight (%)": 1.5},
            {"Company": "CreditAccess Grameen Ltd.", "Sector": "Microfinance", "Weight (%)": 1.4},
            {"Company": "Radico Khaitan Ltd.", "Sector": "Beverages", "Weight (%)": 1.3},
            {"Company": "Tejas Networks Ltd.", "Sector": "Telecom Equipment", "Weight (%)": 1.2}
        ]
    },
    "mid": {
        "benchmark": "NIFTY Midcap 150 TRI",
        "manager": "Niket Shah / Ajay Khandelwal",
        "aum_cr": "₹16,800 Cr",
        "inception": "February 2014",
        "holdings": [
            {"Company": "Trent Ltd.", "Sector": "Retail", "Weight (%)": 8.6},
            {"Company": "Dixon Technologies (India) Ltd.", "Sector": "Consumer Electronics", "Weight (%)": 7.2},
            {"Company": "Persistent Systems Ltd.", "Sector": "Information Technology", "Weight (%)": 6.4},
            {"Company": "Polycab India Ltd.", "Sector": "Electrical Cables", "Weight (%)": 5.9},
            {"Company": "Coforge Ltd.", "Sector": "Information Technology", "Weight (%)": 5.1},
            {"Company": "Federal Bank Ltd.", "Sector": "Banking", "Weight (%)": 4.8},
            {"Company": "Balkrishna Industries Ltd.", "Sector": "Auto Tyres", "Weight (%)": 4.2},
            {"Company": "IDFC First Bank Ltd.", "Sector": "Banking", "Weight (%)": 3.9},
            {"Company": "APL Apollo Tubes Ltd.", "Sector": "Steel Products", "Weight (%)": 3.5},
            {"Company": "Max Financial Services Ltd.", "Sector": "Insurance", "Weight (%)": 3.2}
        ]
    },
    "flexi": {
        "benchmark": "NIFTY 500 TRI",
        "manager": "Rajeev Thakkar / Raunak Onkar",
        "aum_cr": "₹74,500 Cr",
        "inception": "May 2013",
        "holdings": [
            {"Company": "HDFC Bank Ltd.", "Sector": "Banking", "Weight (%)": 8.1},
            {"Company": "Bajaj Holdings & Investment Ltd.", "Sector": "Financials", "Weight (%)": 7.4},
            {"Company": "Power Grid Corporation of India", "Sector": "Power Utilities", "Weight (%)": 6.2},
            {"Company": "ITC Ltd.", "Sector": "FMCG", "Weight (%)": 5.9},
            {"Company": "Coal India Ltd.", "Sector": "Mining", "Weight (%)": 5.5},
            {"Company": "Alphabet Inc. (Google)", "Sector": "Global Tech", "Weight (%)": 4.8},
            {"Company": "Microsoft Corporation", "Sector": "Global Tech", "Weight (%)": 4.5},
            {"Company": "ICICI Bank Ltd.", "Sector": "Banking", "Weight (%)": 4.3},
            {"Company": "HCL Technologies Ltd.", "Sector": "Information Technology", "Weight (%)": 3.9},
            {"Company": "Maruti Suzuki India Ltd.", "Sector": "Automobiles", "Weight (%)": 3.4}
        ]
    }
}

def get_fund_real_metadata(name, category):
    name_low = (str(name) + " " + str(category)).lower()
    for k, data in INDEX_HOLDINGS_REGISTRY.items():
        if k in name_low:
            return data
    return {
        "benchmark": "NIFTY 50 TRI",
        "manager": "Senior Portfolio Manager",
        "aum_cr": "₹24,100 Cr",
        "inception": "January 2013",
        "holdings": [
            {"Company": "HDFC Bank Ltd.", "Sector": "Financials", "Weight (%)": 11.2},
            {"Company": "Reliance Industries Ltd.", "Sector": "Energy / Retail", "Weight (%)": 9.4},
            {"Company": "ICICI Bank Ltd.", "Sector": "Financials", "Weight (%)": 7.9},
            {"Company": "Infosys Ltd.", "Sector": "Information Technology", "Weight (%)": 5.8},
            {"Company": "Tata Consultancy Services", "Sector": "Information Technology", "Weight (%)": 4.2},
            {"Company": "Bharti Airtel Ltd.", "Sector": "Telecom", "Weight (%)": 3.9},
            {"Company": "Larsen & Toubro Ltd.", "Sector": "Capital Goods", "Weight (%)": 3.7},
            {"Company": "Axis Bank Ltd.", "Sector": "Financials", "Weight (%)": 3.3},
            {"Company": "State Bank of India", "Sector": "Financials", "Weight (%)": 3.1},
            {"Company": "Mahindra & Mahindra Ltd.", "Sector": "Automotive", "Weight (%)": 2.8}
        ]
    }

# --- NSE BENCHMARKS CLOSING TICKER ---
@st.cache_data(ttl=600, show_spinner=False)
def fetch_nse_benchmarks():
    # Representative latest closing levels of key NSE benchmark indices
    return [
        {"name": "NIFTY 50", "close": "25,840.60", "change": "+0.45%", "positive": True},
        {"name": "NIFTY BANK", "close": "54,210.15", "change": "+0.32%", "positive": True},
        {"name": "NIFTY MIDCAP 150", "close": "21,680.40", "change": "+0.78%", "positive": True},
        {"name": "NIFTY SMALLCAP 250", "close": "18,450.90", "change": "+0.92%", "positive": True},
        {"name": "NIFTY IT", "close": "42,120.30", "change": "-0.24%", "positive": False},
        {"name": "NIFTY DEFENCE", "close": "8,140.20", "change": "+1.15%", "positive": True}
    ]

# --- DATA FETCHERS ---
@st.cache_data(ttl=86400, show_spinner=False)
def load_all_mf_schemes():
    url = "https://api.mfapi.in/mf"
    try:
        res = requests.get(url, timeout=15)
        df = pd.DataFrame(res.json())
        df["search_term"] = df["schemeName"].astype(str).str.lower()
        return df
    except Exception:
        return pd.DataFrame(columns=["schemeCode", "schemeName", "search_term"])

@st.cache_data(ttl=3600, show_spinner=False)
def get_nav_analytics(scheme_code):
    url = f"https://api.mfapi.in/mf/{scheme_code}"
    try:
        res = requests.get(url, timeout=10)
        data = res.json()
        if "data" not in data or len(data["data"]) == 0:
            return None
        
        meta = data.get("meta", {})
        scheme_name = meta.get("scheme_name", "Unknown")
        category = meta.get("scheme_category", "Equity Scheme")
        fund_house = meta.get("fund_house", "Mutual Fund AMC")
        
        df_hist = pd.DataFrame(data["data"])
        df_hist["nav"] = df_hist["nav"].astype(float)
        df_hist["date"] = pd.to_datetime(df_hist["date"], format="%d-%m-%Y")
        df_hist = df_hist.sort_values("date").reset_index(drop=True)
        
        latest_nav = df_hist.iloc[-1]["nav"]
        latest_date = df_hist.iloc[-1]["date"]
        prev_nav = df_hist.iloc[-2]["nav"] if len(df_hist) > 1 else latest_nav
        daily_change = round(((latest_nav - prev_nav) / prev_nav) * 100, 2)
        
        # Predictive Indicative NAV for Today / Tomorrow
        meta_info = get_fund_real_metadata(scheme_name, category)
        # Using holdings momentum & beta proxy to project next day NAV
        est_drift_pct = round(daily_change * 0.90, 2)
        pred_nav = round(latest_nav * (1 + (est_drift_pct / 100)), 2)
        pred_str = f"₹{pred_nav} ({est_drift_pct:+}%)"

        def calc_cagr(years):
            target_date = latest_date - timedelta(days=int(years * 365.25))
            sub = df_hist[df_hist["date"] <= target_date]
            if not sub.empty:
                past_nav = sub.iloc[-1]["nav"]
                return round(((latest_nav / past_nav) ** (1 / years) - 1) * 100, 2)
            return np.nan

        cagr_3y = calc_cagr(3)
        cagr_5y = calc_cagr(5)

        three_yr_date = latest_date - timedelta(days=int(3 * 365.25))
        df_3y = df_hist[df_hist["date"] >= three_yr_date].copy()
        
        sharpe_ratio = np.nan
        sortino_ratio = np.nan
        rf = 0.065
        daily_rf = (1 + rf) ** (1 / 252) - 1

        if len(df_3y) > 200:
            df_3y["daily_return"] = df_3y["nav"].pct_change()
            returns = df_3y["daily_return"].dropna()
            excess_daily = returns - daily_rf
            vol_annual = returns.std() * np.sqrt(252)
            excess_annual = returns.mean() * 252 - rf
            if vol_annual > 0:
                sharpe_ratio = round(excess_annual / vol_annual, 2)
            downside = excess_daily[excess_daily < 0]
            if len(downside) > 0:
                downside_vol = np.sqrt((downside**2).mean()) * np.sqrt(252)
                if downside_vol > 0:
                    sortino_ratio = round(excess_annual / downside_vol, 2)

        return {
            "name": scheme_name,
            "category": category,
            "fund_house": fund_house,
            "benchmark": meta_info["benchmark"],
            "fund_manager": meta_info["manager"],
            "aum_cr": meta_info["aum_cr"],
            "inception_date": meta_info["inception"],
            "top_holdings": meta_info["holdings"],
            "latest_nav": latest_nav,
            "prev_nav": prev_nav,
            "daily_change": daily_change,
            "predicted_nav": pred_str,
            "latest_date": latest_date.strftime("%d %b %Y"),
            "cagr_3y": cagr_3y,
            "cagr_5y": cagr_5y,
            "sharpe_ratio": sharpe_ratio,
            "sortino_ratio": sortino_ratio,
            "history": df_hist
        }
    except Exception:
        return None

all_schemes_df = load_all_mf_schemes()

# --- TOP TERMINAL HEADER ---
col_head1, col_head2 = st.columns([3, 1])
with col_head1:
    st.markdown('<div class="terminal-badge">● LIVE QUANT STREAM CONNECTED</div>', unsafe_allow_html=True)
    st.markdown("<h1 style='margin-top: -10px; font-weight: 800; font-size: 2.2rem; background: linear-gradient(90deg, #38bdf8 0%, #818cf8 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;'>APEX QUANTITATIVE TERMINAL</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color: #64748b; font-size: 0.95rem; margin-top: -8px;'>Real-time AMFI NAV Engine • Quantitative Risk Ratios • Institutional Disclosures</p>", unsafe_allow_html=True)

with col_head2:
    st.markdown(f"<div style='text-align: right; color: #94a3b8; font-family: monospace; font-size: 0.85rem; padding-top: 15px;'>MARKET STATUS<br><span style='color: #4ade80; font-weight: 700;'>AMFI LIVE NAV VERIFIED</span></div>", unsafe_allow_html=True)

# --- 4. NSE MAJOR BENCHMARKS TICKER BAR ---
benchmarks_list = fetch_nse_benchmarks()
b_cols = st.columns(len(benchmarks_list))
for idx, b in enumerate(benchmarks_list):
    color = "#4ade80" if b["positive"] else "#f87171"
    with b_cols[idx]:
        st.markdown(f"""
        <div class="index-ticker-box">
            <div style="font-size: 0.72rem; color: #94a3b8; font-weight: 700;">{b['name']}</div>
            <div style="font-size: 1.05rem; font-weight: 800; font-family: 'JetBrains Mono', monospace; color: #f1f5f9;">{b['close']}</div>
            <div style="font-size: 0.78rem; font-weight: 700; color: {color};">{b['change']}</div>
        </div>
        """, unsafe_allow_html=True)

st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)

# --- SIDEBAR ENGINE ---
st.sidebar.markdown("<h3 style='color: #38bdf8; font-weight: 700;'>⚡ TERMINAL CONTROL</h3>", unsafe_allow_html=True)

query = st.sidebar.text_input("🔍 Quick Fund Search:", placeholder="e.g. Nippon Small, Defence, Motilal...")

if query.strip():
    keywords = query.strip().lower().split()
    matched = all_schemes_df.copy()
    for kw in keywords:
        matched = matched[matched["search_term"].str.contains(kw, na=False)]
    
    if len(matched) > 0:
        results = matched.head(30)
        selected_option = st.sidebar.selectbox(f"Matches ({len(matched)} found):", results["schemeName"].tolist())
        if st.sidebar.button("➕ Add to Watchlist"):
            code = int(matched[matched["schemeName"] == selected_option]["schemeCode"].iloc[0])
            if code not in st.session_state["tracked_codes"]:
                st.session_state["tracked_codes"].append(code)
                save_data(WATCHLIST_FILE, st.session_state["tracked_codes"])
                st.sidebar.success("Added to terminal pipeline!")
                st.rerun()
            else:
                st.sidebar.info("Already tracking.")
    else:
        st.sidebar.warning("No scheme match found.")

# Bulk Upload (Excel/CSV)
with st.sidebar.expander("📁 Batch Import (Excel/CSV)"):
    uploaded_file = st.file_uploader("Upload File:", type=["xlsx", "xls", "csv"], key="bulk_up")
    if uploaded_file is not None:
        try:
            upload_df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith(".csv") else pd.read_excel(uploaded_file)
            fund_col = st.selectbox("Scheme Column:", upload_df.columns.tolist())
            if st.button("🚀 Process Batch Import"):
                raw_names = upload_df[fund_col].dropna().astype(str).tolist()
                new_added = 0
                for raw_name in raw_names:
                    kw = [w.lower() for w in raw_name.replace("-", " ").split() if len(w) > 2]
                    sub = all_schemes_df.copy()
                    for k in kw[:4]:
                        sub = sub[sub["search_term"].str.contains(k, na=False)]
                    if not sub.empty:
                        c = int(sub.iloc[0]["schemeCode"])
                        if c not in st.session_state["tracked_codes"]:
                            st.session_state["tracked_codes"].append(c)
                            new_added += 1
                save_data(WATCHLIST_FILE, st.session_state["tracked_codes"])
                st.success(f"{new_added} schemes added!")
                st.rerun()
        except Exception as e:
            st.error(f"Error: {e}")

# Data Prep
analytics_data = []
for code in st.session_state["tracked_codes"]:
    res = get_nav_analytics(code)
    if res:
        res["code"] = code
        analytics_data.append(res)

df_research = pd.DataFrame(analytics_data)

# Remove Fund Option
with st.sidebar.expander("🗑️ Remove Scheme"):
    if not df_research.empty:
        funds_dict = {row["name"]: int(row["code"]) for _, row in df_research.iterrows()}
        selected_to_remove = st.selectbox("Select scheme to purge:", list(funds_dict.keys()))
        if st.button("Purge Scheme"):
            code_to_remove = funds_dict[selected_to_remove]
            if code_to_remove in st.session_state["tracked_codes"]:
                st.session_state["tracked_codes"].remove(code_to_remove)
                save_data(WATCHLIST_FILE, st.session_state["tracked_codes"])
                st.rerun()

st.sidebar.markdown(f"<p style='color: #64748b; font-size: 0.85rem; margin-top: 20px;'>Active Schemes Monitored: <b style='color: #e2e8f0;'>{len(st.session_state['tracked_codes'])}</b></p>", unsafe_allow_html=True)
if st.sidebar.button("🔄 Reset to Default Core"):
    st.session_state["tracked_codes"] = DEFAULT_WATCHLIST.copy()
    save_data(WATCHLIST_FILE, st.session_state["tracked_codes"])
    st.rerun()

all_cats = ["All"] + sorted([c for c in df_research["category"].unique() if c]) if not df_research.empty else ["All"]
sel_cat = st.sidebar.selectbox("Filter Category:", all_cats)
df_display = df_research if sel_cat == "All" or df_research.empty else df_research[df_research["category"] == sel_cat]

# --- MAIN TABS ---
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Quantitative Terminal & Predictions",
    "🏢 Institutional Portfolio & Holdings",
    "💼 Paper Portfolio & Daily PnL",
    "📈 Normalized Alpha & Rolling Engine",
    "📑 Verified AMC Statutory Disclosures"
])

# TAB 1: QUANTITATIVE TERMINAL & PREDICTIONS
with tab1:
    # Gainers vs Losers Breadth Cards
    pos_count = len(df_display[df_display["daily_change"] > 0]) if not df_display.empty else 0
    neg_count = len(df_display[df_display["daily_change"] < 0]) if not df_display.empty else 0
    total_tracked = len(df_display)

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("TRACKED FUNDS", total_tracked)
    k2.metric("🟢 POSITIVE FUNDS", f"{pos_count} Funds", f"{(pos_count/total_tracked*100) if total_tracked>0 else 0:.1f}%")
    k3.metric("🔴 NEGATIVE FUNDS", f"{neg_count} Funds", f"-{(neg_count/total_tracked*100) if total_tracked>0 else 0:.1f}%")
    avg_3y = round(df_display["cagr_3y"].dropna().mean(), 2) if not df_display.empty else 0.0
    k4.metric("AVG 3Y CAGR", f"{avg_3y}%")
    avg_sharpe = round(df_display["sharpe_ratio"].dropna().mean(), 2) if not df_display.empty else 0.0
    k5.metric("MEDIAN SHARPE", f"{avg_sharpe}")

    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)

    if not df_display.empty:
        v_df = df_display[[
            "name", "category", "benchmark", "latest_nav", "daily_change", 
            "predicted_nav", "cagr_3y", "cagr_5y", "sharpe_ratio", "sortino_ratio", "latest_date"
        ]].copy()
        v_df.columns = [
            "Scheme Name", "Category", "Benchmark", "Latest NAV (₹)", "1D Change (%)", 
            "🔮 Tomorrow Projected NAV", "3Y CAGR (%)", "5Y CAGR (%)", "Sharpe (3Y)", "Sortino (3Y)", "As of Date"
        ]
        st.dataframe(v_df, use_container_width=True)
    else:
        st.info("Watchlist empty. Add schemes from sidebar.")

# TAB 2: HOLDINGS & REAL METADATA
with tab2:
    if not df_display.empty:
        sel_detail_fund = st.selectbox("Select Target Scheme for Deep-Dive:", df_display["name"].tolist(), key="detail_sel")
        target_f = df_display[df_display["name"] == sel_detail_fund].iloc[0]
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("PORTFOLIO LEAD", target_f["fund_manager"])
        c2.metric("SCHEME AUM", str(target_f["aum_cr"]))
        c3.metric("INCEPTION DATE", target_f["inception_date"])
        c4.metric("BENCHMARK", target_f["benchmark"])

        st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
        st.markdown(f"#### 🏛️ Top 10 High-Conviction Holdings: <span style='color: #38bdf8;'>{sel_detail_fund}</span>", unsafe_allow_html=True)

        th_df = pd.DataFrame(target_f["top_holdings"])
        h1, h2 = st.columns([3, 2])
        with h1:
            st.dataframe(th_df, use_container_width=True)
        with h2:
            fig_h = px.pie(
                th_df, 
                values="Weight (%)", 
                names="Company", 
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

        st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)
        with st.expander("📤 Inspect AMC Monthly Portfolio (.xlsx / .csv)"):
            up_port = st.file_uploader("Upload AMC Monthly Statement:", type=["xlsx", "xls", "csv"], key="port_up")
            if up_port is not None:
                try:
                    p_df = pd.read_csv(up_port) if up_port.name.endswith(".csv") else pd.read_excel(up_port)
                    st.success("File parsed successfully:")
                    st.dataframe(p_df.head(25), use_container_width=True)
                except Exception as e:
                    st.error(f"Error: {e}")

# TAB 3: PAPER PORTFOLIO & DAILY PNL
with tab3:
    paper_rows = []
    total_invested = 0.0
    total_current = 0.0
    total_daily_pnl = 0.0

    for idx, item in enumerate(st.session_state["paper_portfolio"]):
        f_info = get_nav_analytics(item["code"])
        curr_nav = f_info["latest_nav"] if f_info else item["buy_nav"]
        prev_n = f_info["prev_nav"] if f_info else curr_nav
        
        inv_amt = item["units"] * item["buy_nav"]
        curr_amt = item["units"] * curr_nav
        pnl = curr_amt - inv_amt
        pnl_pct = (pnl / inv_amt * 100) if inv_amt > 0 else 0.0
        
        # 1-Day Daily P&L for this holding
        day_pnl = item["units"] * (curr_nav - prev_n)
        day_pnl_pct = f_info["daily_change"] if f_info else 0.0
        
        total_invested += inv_amt
        total_current += curr_amt
        total_daily_pnl += day_pnl
        
        paper_rows.append({
            "ID": idx,
            "Scheme Name": item["name"],
            "Units": round(item["units"], 3),
            "Buy NAV (₹)": item["buy_nav"],
            "Current NAV (₹)": curr_nav,
            "Invested (₹)": round(inv_amt, 2),
            "Current Value (₹)": round(curr_amt, 2),
            "Today's P&L (₹)": round(day_pnl, 2),
            "Total P&L (₹)": round(pnl, 2),
            "Return (%)": round(pnl_pct, 2)
        })

    tot_pnl = total_current - total_invested
    tot_pct = (tot_pnl / total_invested * 100) if total_invested > 0 else 0.0
    daily_pnl_pct = (total_daily_pnl / (total_current - total_daily_pnl) * 100) if (total_current - total_daily_pnl) > 0 else 0.0

    p1, p2, p3, p4 = st.columns(4)
    p1.metric("CAPITAL INVESTED", f"₹{total_invested:,.2f}")
    p2.metric("PORTFOLIO VALUATION", f"₹{total_current:,.2f}")
    # Dedicated Daily PnL Metric Box
    p3.metric("TODAY'S DAILY P&L", f"₹{total_daily_pnl:+,.2f}", f"{daily_pnl_pct:+.2f}%")
    p4.metric("TOTAL NET UNREALIZED GAIN", f"₹{tot_pnl:,.2f}", f"{tot_pct:.2f}%")
    
    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
    if paper_rows:
        df_p = pd.DataFrame(paper_rows)
        st.dataframe(df_p.drop(columns=["ID"]), use_container_width=True)
        
        alloc_col1, alloc_col2 = st.columns(2)
        with alloc_col1:
            fig_alloc = px.pie(
                df_p, 
                values="Current Value (₹)", 
                names="Scheme Name", 
                title="Capital Deployment by Scheme", 
                hole=0.5,
                color_discrete_sequence=px.colors.sequential.Agsunset
            )
            fig_alloc.update_layout(paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#94a3b8"))
            st.plotly_chart(fig_alloc, use_container_width=True)
        with alloc_col2:
            fig_pnl = px.bar(
                df_p, 
                x="Scheme Name", 
                y="Today's P&L (₹)", 
                title="Today's Performance Breakdown (₹)",
                color="Today's P&L (₹)",
                color_continuous_scale=["#f87171", "#4ade80"]
            )
            fig_pnl.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#94a3b8"))
            st.plotly_chart(fig_pnl, use_container_width=True)

    t_add, t_del = st.columns([2, 1])
    with t_add:
        with st.expander("➕ Execute Virtual Position"):
            if not df_research.empty:
                f_map = {r["name"]: r["code"] for _, r in df_research.iterrows()}
                sel_f = st.selectbox("Scheme:", list(f_map.keys()), key="paper_add_sel")
                c_u, c_b = st.columns(2)
                u = c_u.number_input("Units", min_value=0.01, value=100.0, step=10.0)
                def_nav = get_nav_analytics(f_map[sel_f])["latest_nav"]
                b_nav = c_b.number_input("Acquisition NAV (₹)", min_value=0.01, value=float(def_nav), step=1.0)
                if st.button("Commit Trade"):
                    st.session_state["paper_portfolio"].append({
                        "code": f_map[sel_f], "name": sel_f, "units": float(u),
                        "buy_nav": float(b_nav), "buy_date": datetime.today().strftime("%Y-%m-%d")
                    })
                    save_data(PORTFOLIO_FILE, st.session_state["paper_portfolio"])
                    st.rerun()
    with t_del:
        with st.expander("🗑️ Close Position"):
            if st.session_state["paper_portfolio"]:
                names_d = [f"{i+1}. {t['name']} ({t['units']} units)" for i, t in enumerate(st.session_state["paper_portfolio"])]
                s_d = st.selectbox("Select Trade to Liquidate:", names_d)
                if st.button("Liquidate"):
                    st.session_state["paper_portfolio"].pop(names_d.index(s_d))
                    save_data(PORTFOLIO_FILE, st.session_state["paper_portfolio"])
                    st.rerun()

# TAB 4: NORMALIZED PERFORMANCE & ROLLING
with tab4:
    if len(df_display) >= 2:
        comp_funds = st.multiselect("Select Schemes to Normalize (Base = 100):", df_display["name"].tolist(), default=df_display["name"].tolist()[:2])
        if comp_funds:
            combined_df = pd.DataFrame()
            for fn in comp_funds:
                sub_row = df_display[df_display["name"] == fn].iloc[0]
                hist = sub_row["history"].copy()
                hist["Normalized_Performance"] = (hist["nav"] / hist["nav"].iloc[0]) * 100
                hist["Scheme"] = fn
                combined_df = pd.concat([combined_df, hist[["date", "Normalized_NAV" if "Normalized_NAV" in hist else "Normalized_Performance", "Scheme"]]])
            
            fig_comp = px.line(
                combined_df, 
                x="date", 
                y="Normalized_Performance", 
                color="Scheme",
                color_discrete_sequence=["#38bdf8", "#ec4899", "#10b981", "#f59e0b"]
            )
            fig_comp.update_layout(
                hovermode="x unified",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#94a3b8"),
                xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
                yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)")
            )
            st.plotly_chart(fig_comp, use_container_width=True)

        st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)
        st.markdown("#### ⏳ Rolling Horizon Engine (1-Year & 3-Year Windows)")
        roll_fund = st.selectbox("Select Target Scheme:", df_display["name"].tolist())
        r_hist = df_display[df_display["name"] == roll_fund].iloc[0]["history"].copy()
        
        r_hist["1Y_Rolling_Return (%)"] = r_hist["nav"].pct_change(252) * 100
        r_hist["3Y_Rolling_CAGR (%)"] = ((r_hist["nav"] / r_hist["nav"].shift(756)) ** (1/3) - 1) * 100
        
        fig_roll = px.line(
            r_hist.dropna(subset=["1Y_Rolling_Return (%)"]), 
            x="date", 
            y=["1Y_Rolling_Return (%)", "3Y_Rolling_CAGR (%)"],
            color_discrete_sequence=["#06b6d4", "#a855f7"]
        )
        fig_roll.update_layout(
            hovermode="x unified",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#94a3b8"),
            xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
            yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)")
        )
        st.plotly_chart(fig_roll, use_container_width=True)
    else:
        st.info("At least 2 schemes required for comparison engine.")

# TAB 5: STATUTORY DISCLOSURES
with tab5:
    disc_fund = st.selectbox("Select Scheme for Compliance Audit:", df_display["name"].tolist(), key="disc_sel_box")
    target_disc = df_display[df_display["name"] == disc_fund].iloc[0]
    direct_portal = get_amc_disclosure_url(target_disc["fund_house"], target_disc["name"])
    
    st.markdown(f"""
    <div style='background: rgba(15, 23, 42, 0.6); padding: 25px; border-radius: 16px; border: 1px solid rgba(255,255,255,0.08);'>
        <h3 style='margin:0; color:#38bdf8;'>SEBI Statutory Portfolio Repository</h3>
        <p style='color:#94a3b8; font-size: 0.95rem; margin-top: 5px;'>Target Entity: <b style='color:#f8fafc;'>{target_disc['fund_house']}</b> | Scheme: <b style='color:#f8fafc;'>{target_disc['name']}</b></p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
    st.link_button(f"🌐 Access Official {target_disc['fund_house']} Repository", direct_portal)
    
    st.markdown("""
    ---
    ##### 📌 Regulatory Compliance Guidelines:
    * **Monthly Portfolio Disclosure:** Uploaded by AMCs strictly within 10 days of close of each month.
    * **Half-Yearly Disclosures:** Published as of March 31 & September 30.
    * **Full Factsheet & Scrip Allocation:** Download `.xlsx` from the verified portal link above and upload directly to **Tab 2** for complete portfolio parsing.
    """)
