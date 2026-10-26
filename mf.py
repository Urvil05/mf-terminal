import streamlit as st
import pandas as pd
import plotly.express as px
import os

# --- 1. PAGE SETUP & CSS ---
st.set_page_config(page_title="APEX MF | Institutional Terminal", page_icon="⚡", layout="wide")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;800&family=JetBrains+Mono:wght@400;700&display=swap');
    html, body, [class*="css"] { font-family: 'Plus Jakarta Sans', sans-serif; }
    .stApp { background: radial-gradient(circle at top right, #0f172a 0%, #030712 100%); color: #f8fafc; }
    .terminal-badge { display: inline-flex; align-items: center; gap: 6px; padding: 4px 12px; background: rgba(34, 197, 94, 0.12); border: 1px solid rgba(34, 197, 94, 0.3); color: #4ade80; font-size: 0.75rem; font-weight: 700; border-radius: 9999px; }
</style>
""", unsafe_allow_html=True)

# --- 2. PERMANENT 25 FUNDS (CRASH PROOF) ---
# Ye 25 codes top schemes ke hain (Parag, Nippon, Motilal, Quant etc.) 
# Ye kabhi delete nahi honge chahe server reboot ho jaye.
PERMANENT_25_FUNDS = [
    122639, 118778, 120716, 108466, 119062, 119598, 125497, 120586, 118989, 119800, 
    120465, 118756, 120505, 120821, 118764, 118985, 120173, 119775, 119286, 119106,
    118925, 119642, 118967, 120092, 120140
]

if "watchlist" not in st.session_state:
    st.session_state["watchlist"] = PERMANENT_25_FUNDS.copy()

# --- 3. HEADER ---
st.markdown('<div class="terminal-badge">● APEX CORE V2.0 ACTIVE</div>', unsafe_allow_html=True)
st.markdown("<h1 style='margin-top: -10px; font-weight: 800; font-size: 2.2rem; background: linear-gradient(90deg, #38bdf8 0%, #818cf8 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;'>APEX QUANTITATIVE TERMINAL</h1>", unsafe_allow_html=True)
st.markdown("---")

# --- 4. TABS SETUP ---
tab1, tab2, tab3 = st.tabs([
    "📊 Quant Dashboard", 
    "🏢 Institutional Factsheet Parser", 
    "💼 Paper Portfolio"
])

with tab1:
    st.info(f"🟢 System Active. Tracking {len(st.session_state['watchlist'])} Core Funds permanently.")
    st.write("*(Live AMFI Data Engine yahan aayega Phase 2 mein)*")

with tab2:
    st.markdown("### 📥 100% Accurate Factsheet Parser")
    st.caption("No dummy data. Upload official AMC .xlsx files here for pitching.")
    # Factsheet logic aage add karenge

with tab3:
    st.markdown("### 💼 Virtual Portfolio & PNL")
    st.write("*(Tax Planning and Portfolio Engine yahan aayega)*")
