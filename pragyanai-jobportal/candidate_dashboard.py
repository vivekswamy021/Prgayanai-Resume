# candidate_dashboard.py
import streamlit as st
import json
import re
from mongodb_manager import DatabaseManager

def candidate_dashboard():
    st.header("👩‍🎓 Candidate Dashboard")
    st.sidebar.button("⬅️ Go Back to Role Selection", on_click=lambda: st.session_state.update(page="role_selection"))

    if 'db' not in st.session_state or not st.session_state.db.is_connected():
        st.error("Database not connected.")
        return

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📄 Resume Parsing", "💬 Resume Q&A", "❓ Interview Prep", "📚 JD Management", "🎯 Batch JD Match"
    ])

    with tab1:
        st.subheader("Resume Parsing")
        st.info("Upload and parse resume using LLM (same as original).")

    with tab2:
        st.subheader("Resume Chatbot (Q&A)")
        st.info("Ask AI questions about your parsed resume.")

    with tab3:
        st.subheader("Interview Preparation")
        st.info("Generate interview questions per section.")

    with tab4:
        st.subheader("Manage JDs")
        st.info("Add and manage your own job descriptions.")

    with tab5:
        st.subheader("Batch JD Match")
        st.info("Match your resume against all saved JDs and store results.")
