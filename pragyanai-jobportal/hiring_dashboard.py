# hiring_dashboard.py
import streamlit as st

def hiring_dashboard():
    st.header("🏢 Hiring Company Dashboard")
    st.write("Manage job postings, view applicants, and monitor recruitment stats. (Coming soon!)")
    st.sidebar.button("⬅️ Go Back to Role Selection", on_click=lambda: st.session_state.update(page="role_selection"))
