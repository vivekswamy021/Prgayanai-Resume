# main_app.py
import streamlit as st
from mongodb_manager import DatabaseManager
from admin_dashboard import admin_dashboard
from candidate_dashboard import candidate_dashboard
from hiring_dashboard import hiring_dashboard

def go_to(page_name):
    st.session_state.page = page_name

def login_page():
    st.title("🌐 PragyanAI Job Portal")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        st.success("Login successful!")
        go_to("role_selection")

def signup_page():
    st.header("Sign Up")
    st.text_input("Email")
    st.text_input("Password", type="password")
    st.button("Create Account", on_click=lambda: go_to("login"))

def role_selection_page():
    st.header("Select Your Role")
    role = st.selectbox("Choose a Dashboard", ["Admin", "Candidate", "Hiring"])
    if st.button("Continue"):
        if role == "Admin":
            go_to("admin_dashboard")
        elif role == "Candidate":
            go_to("candidate_dashboard")
        elif role == "Hiring":
            go_to("hiring_dashboard")

def main():
    st.set_page_config(layout="wide", page_title="PragyanAI Job Portal")
    if "page" not in st.session_state:
        st.session_state.page = "login"
    if "db" not in st.session_state:
        from mongodb_manager import MONGODB_URI
        st.session_state.db = DatabaseManager(MONGODB_URI)

    page = st.session_state.page
    if page == "login": login_page()
    elif page == "signup": signup_page()
    elif page == "role_selection": role_selection_page()
    elif page == "admin_dashboard": admin_dashboard()
    elif page == "candidate_dashboard": candidate_dashboard()
    elif page == "hiring_dashboard": hiring_dashboard()

if __name__ == "__main__":
    main()
