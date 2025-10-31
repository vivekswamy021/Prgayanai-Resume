# hiring_dashboard.py

import streamlit as st
from utils import go_to

def hiring_dashboard():
    st.header("🏢 Hiring Company Dashboard")
    st.write("Manage job postings and view candidate applications. (Placeholder for future features)")
    
    # --- MODIFIED NAVIGATION BLOCK ---
    nav_col, _ = st.columns([1, 1]) 

    with nav_col:
        if st.button("🚪 Log Out", key="hiring_logout_btn", use_container_width=True):
            go_to("login") 
    # --- END MODIFIED NAVIGATION BLOCK ---
