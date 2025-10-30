# admin_dashboard.py
import streamlit as st
from bson.objectid import ObjectId
from datetime import datetime
import tempfile
import os
import re
import traceback
from mongodb_manager import DatabaseManager

def admin_dashboard():
    st.header("🧑‍💼 Admin Dashboard")
    st.sidebar.button("⬅️ Go Back to Role Selection", on_click=lambda: st.session_state.update(page="role_selection"))

    if 'db' not in st.session_state or not st.session_state.db.is_connected():
        st.error("🚨 Cannot proceed: MongoDB is not connected.")
        return

    st.session_state.setdefault("admin_jd_list", st.session_state.db.get_jds("admin"))
    st.session_state.setdefault("resumes_to_analyze", st.session_state.db.get_resumes())
    st.session_state.setdefault("vendor_list", st.session_state.db.get_vendors())
    st.session_state.setdefault("admin_match_results", st.session_state.db.get_match_results("admin"))

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["📄 JD Management", "📊 Resume Analysis", "✅ Candidate Approval", "🤝 Vendors", "📈 Metrics"]
    )

    with tab1:
        st.subheader("JD Management")
        st.write("Upload, paste or import JDs from LinkedIn URLs.")
        st.info("Full logic same as before — truncated here for brevity.")
        # Keep your JD CRUD logic from your original code here

    with tab2:
        st.subheader("Resume Analysis")
        st.info("Upload resumes and match them against JDs.")
        # Insert resume analysis logic here

    with tab3:
        st.subheader("Candidate Approval")
        st.info("Change candidate status between Pending, Approved, Rejected, etc.")
        # Keep status update logic here

    with tab4:
        st.subheader("Vendors Approval")
        st.info("Manage vendor onboarding and approval.")
        # Vendor CRUD logic here

    with tab5:
        st.subheader("Platform Metrics")
        metrics = st.session_state.db.get_platform_metrics()
        st.metric("Total Candidates", metrics["total_candidates"])
        st.metric("Total JDs", metrics["total_jds"])
        st.metric("Total Vendors", metrics["total_vendors"])
        st.metric("Total Applications", metrics["no_of_applications"])
