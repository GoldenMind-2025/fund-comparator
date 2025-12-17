# app.py
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import json
import os
from datetime import datetime
import streamlit.components.v1 as components

# ==============================================================================
# 1. CONFIGURATION & CONSTANTS
# ==============================================================================
st.set_page_config(page_title="Fund Comparator", layout="wide", page_icon="⚖️")

# AMFI Public API
AMFI_BASE_URL = "https://api.mfapi.in/mf"

# The file you need to copy into the folder
REGISTRY_FILENAME = "scheme_registry.json" 

# ==============================================================================
# 2. DATA ENGINE (Cloud-Ready, Memory Caching)
# ==============================================================================

@st.cache_data(show_spinner=False)
def load_fund_registry():
    """
    Loads the JSON registry from the local folder.
    Returns:
    1. amc_index: Dict for Dropdowns {AMC_Name: [Funds]}
    2. raw_registry: Dict for Lookups {ISIN: Metadata}
    """
    amc_index = {}
    raw_registry = {}
    
    # Check if file exists
    if not os.path.exists(REGISTRY_FILENAME):
        return {}, {}

    try:
        with open(REGISTRY_FILENAME, "r") as f:
            raw_registry = json.load(f)

        for isin, meta in raw_registry.items():
            name = meta.get("scheme", isin)
            amfi = meta.get("amfi")

            # Only add if AMFI code exists (required for fetching data)
            if amfi:
                # Derive Pseudo AMC (First word of the fund name)
                first_word = name.split()[0].upper() if name else "OTHER"
                
                item = {
                    "label": name, 
                    "amfi": str(amfi), 
                    "name": name
                }
                
                # Add to AMC Index
                if first_word not in amc_index:
                    amc_index[first_word] = []
                amc_index[first_word].append(item)

        # Sort lists for UI
        for amc in amc_index:
            amc_index[amc] = sorted(amc_index[amc], key=lambda x: x["label"])
            
        return amc_index, raw_registry

    except Exception as e:
        st.error(f"Error loading registry: {e}")
        return {}, {}

@st.cache_data(ttl=86400, show_spinner=False) # Cache data for 24 hours
def get_nav_history(amfi_code):
    """
    Fetches NAV history from AMFI API. 
    Returns a cleaned DataFrame with 'date' and 'nav'.
    """
    try:
        url = f"{AMFI_BASE_URL}/{amfi_code}"
        response = requests.get(url)
        
        if response.status_code == 200:
            data = response.json()
            nav_list = data.get("data", [])
            
            if not nav_list:
                return pd.DataFrame()

            df = pd.DataFrame(nav_list)
            df["date"] = pd.to_datetime(df["date"], format="%d-%m-%Y")
            df["nav"] = pd.to_numeric(df["nav"])
            return df.sort_values("date")
            
    except Exception:
        return pd.DataFrame()
    
    return pd.DataFrame()


# ==============================================================================
# 3. UI: SIDEBAR (Credits & Settings)
# ==============================================================================

# Load Data
amc_map, raw_registry = load_fund_registry()

with st.sidebar:
    st.header("⚙️ Settings")
    
    # --- Time Period ---
    st.markdown("**Lookback Period**")
    time_map = {
        "3M": 3, "6M": 6, "1Y": 12, "2Y": 24, 
        "3Y": 36, "5Y": 60, "Max": 999
    }
    range_label = st.pills("Lookback", list(time_map.keys()), default="1Y", label_visibility="collapsed")
    
    st.divider()
    
    # --- Guest Fund ---
    st.markdown("**Guest / Benchmark**")
    st.caption("Compare against a fund via ISIN/AMFI code.")
    guest_input = st.text_input("ISIN or AMFI Code", placeholder="e.g. INF209KA1234")
    guest_name = st.text_input("Label", value="Benchmark")




# ==============================================================================
# 4. UI: MAIN PAGE (Instructions & App)
# ==============================================================================

st.title("⚖️ Compare Mutual Funds")

# --- Instructions (Collapsible) ---
with st.expander("ℹ️  **First time user? Click to read the Quick Guide**", expanded=True):
    st.markdown("""
    **How to use this tool:**
    1.  **Select an AMC** (Asset Management Company) from the dropdown below.
    2.  **Pick Funds** you want to compare.
    3.  You can type parts of the words in funds name - i.e. Growth / Direct, select and click **Add**.
    4.  **Analyze** the chart. The graph starts at **100** on the start date, so you can easily compare relative growth.
    5.  You can also add funds that you cannot find in the drop down by adding fund's ISIN code in the Guest Box
    6.  This tool helps to compare returns of the funds over the selected time frame.
    7.  It is also necessary to look at fund metrics such as PE ratio, assests under management (AMU), expense, portfolio, manager, etc.
    8.  **http://valuereseach.com/ is one source of this information

    *Share your comments in the guestbook at the end.*

    *Disclaimer - This does not constitute investement advice or recommendation.*
    *Please consult a qualified finicial adviser.*
    *Note: Data is fetched live from AMFI. The first load for a fund might take a time to load.*
    """)

# --- Missing Registry Warning ---
if not amc_map:
    st.error(f"⚠️ **Registry Missing!** Please ensure `{REGISTRY_FILENAME}` is in the same folder as this script.")
    st.stop()

# --- Initialize Session State ---
if "compare_basket" not in st.session_state:
    st.session_state["compare_basket"] = []

# --- A. Selection Controls ---
st.markdown("##### 1. Select Funds")
col_amc, col_fund, col_btn = st.columns([1.5, 3, 0.8], gap="medium")

with col_amc:
    amc_list = sorted(list(amc_map.keys()))
    selected_amc = st.selectbox("Filter by AMC", ["Select AMC..."] + amc_list)

with col_fund:
    fund_options = []
    if selected_amc != "Select AMC...":
        fund_options = amc_map.get(selected_amc, [])
    
    funds_to_add = st.multiselect(
        "Select Funds",
        options=fund_options,
        format_func=lambda x: x["label"],
        key="temp_selector",
        label_visibility="visible"
    )

with col_btn:
    st.write("") # Alignment spacer
    st.write("")
    if st.button("➕ Add", use_container_width=True):
        count = 0
        for fund in funds_to_add:
            if fund not in st.session_state["compare_basket"]:
                st.session_state["compare_basket"].append(fund)
                count += 1
        if count > 0:
            st.success(f"+{count}")

# --- B. Active List ---
if st.session_state["compare_basket"]:
    st.markdown("##### 2. Active Comparison List")
    current_basket = st.session_state["compare_basket"]
    
    updated_basket = st.multiselect(
        "Current Compare List",
        options=current_basket,
        default=current_basket,
        format_func=lambda x: x["label"],
        label_visibility="collapsed",
        help="Uncheck to remove"
    )
    
    # State update if removed
    if len(updated_basket) != len(current_basket):
        st.session_state["compare_basket"] = updated_basket
        st.rerun()
    
    # Clear Button
    if st.button("Clear List"):
        st.session_state["compare_basket"] = []
        st.rerun()

elif not guest_input:
    st.info("👇 Add funds above to start the comparison.")

st.divider()

# ==============================================================================
# 5. CHART ENGINE
# ==============================================================================

final_targets = []

# 1. Process Basket
for item in st.session_state["compare_basket"]:
    final_targets.append({
        "code": item["amfi"],
        "name": item["name"],
        "is_guest": False
    })

# 2. Process Guest
if guest_input:
    clean_input = guest_input.strip().upper()
    resolved_amfi = clean_input # Default assumption: input is AMFI code
    
    # Try resolving via Registry if it looks like an ISIN
    if clean_input in raw_registry:
        meta = raw_registry[clean_input]
        if meta.get("amfi"):
            resolved_amfi = str(meta["amfi"])
            
    final_targets.append({
        "code": resolved_amfi,
        "name": guest_name,
        "is_guest": True
    })

# 3. Fetch & Plot
if final_targets:
    fig = go.Figure()
    has_data = False
    
    # Progress Bar for UX
    progress_bar = st.progress(0, text="Fetching Data...")
    total_targets = len(final_targets)

    for i, t in enumerate(final_targets):
        # Fetch Data (Using the cached internal function)
        df = get_nav_history(t["code"])
        
        progress_bar.progress((i + 1) / total_targets)
        
        if not df.empty:
            # Filter Date Range
            months = time_map[range_label]
            end_date = df["date"].max()
            
            if months != 999:
                start_date = end_date - pd.DateOffset(months=months)
                df = df[df["date"] >= start_date]
            
            if not df.empty:
                # Normalization (Rebase to 100)
                start_val = df.iloc[0]["nav"]
                df["normalized"] = (df["nav"] / start_val) * 100
                
                # Plot
                line_props = dict(dash='dash', width=2) if t["is_guest"] else dict(width=2)
                
                fig.add_trace(go.Scatter(
                    x=df["date"],
                    y=df["normalized"],
                    mode='lines',
                    name=t["name"],
                    line=line_props,
                    hovertemplate=f"<b>{t['name']}</b><br>%{{x|%d-%b-%Y}}<br>Value: %{{y:.1f}}<extra></extra>"
                ))
                has_data = True

    progress_bar.empty()

    if has_data:
        fig.update_layout(
            title=dict(text=f"Relative Performance (Base 100) - {range_label}", x=0),
            xaxis_title="Date",
            yaxis_title="Growth (Starts at 100)",
            template="plotly_white",
            hovermode="x unified",
            height=600,
            legend=dict(
                orientation="h",
                y=1.1,
                xanchor="left",
                x=0
            ),
            margin=dict(l=20, r=20, t=80, b=20)
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("No data found for the selected funds/dates.")


####last section - guestbook - credits

# ==============================================================================
# 3. UI: SIDEBAR (Credits & Settings)
# ==============================================================================

# ... (Previous settings code remains the same) ...

# --- GUESTBOOK / FEEDBACK ---
st.divider()
st.header("💌 Guestbook")

# Create an Expander so it doesn't take up space until clicked
with st.expander("✍️ Leave a note"):
    st.write("Say hi or leave feedback!")
    
    # METHOD A: Simple Link Button (Easiest)
    # st.link_button("Open Guestbook", "YOUR_PADLET_OR_GOOGLE_FORM_URL")
    
    # METHOD B: Embedded Wall (Coolest)
    # Replace the URL below with your specific Padlet URL
    # You can get this URL from Padlet -> Share -> Embed -> Copy link
    components.iframe("https://padlet.com/goldenrockbest/write-your-discussion-question-here-5envw9ygey4ydvji", height=400, scrolling=True)

st.markdown("---")
st.caption(
    "**Credits**\n\n"
    "Created by [Golden_Mind]\n"
    "Data Source: AMFI (Public API)\n"
    "Ver: 1.0-17 Dec 25(Standalone)"
)
