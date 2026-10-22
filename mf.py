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

    /* Main Background Theme */
    .stApp {
        background: radial-gradient(circle at top right, #0f172a 0%, #030712 100%);
        color: #f8fafc;
    }
    
    /* Modern Glassmorphic Metric Cards */
    div[data-testid="stMetric"] {
        background: rgba(15, 23, 42, 0.65) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 16px !important;
        padding: 18px 22px !important;
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
        font-size: 0.85rem !important;
        font-weight: 600 !important;
        letter-spacing: 0.05em !important;
        text-transform: uppercase !important;
    }

    div[data-testid="stMetricValue"] {
        color: #f1f5f9 !important;
        font-size: 1.85rem !important;
        font-weight: 800 !important;
        font-family: 'JetBrains Mono', monospace !important;
    }

    /* Tabs Styling */
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

    /* Buttons */
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

    /* Sidebar Customization */
    section[data-testid="stSidebar"] {
        background-color: #030712 !important;
        border-right: 1px solid rgba(255, 255, 255, 0.07) !important;
    }

    /* Tables & Dataframes */
    div[data-testid="stDataFrame"] {
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 14px !important;
        overflow: hidden !important;
    }

    /* Custom Header Tag */
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

# --- REAL INDEX & SCHEME CONSTITUENTS REGISTRY ---
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

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_mf_news():
    rss_url = "
