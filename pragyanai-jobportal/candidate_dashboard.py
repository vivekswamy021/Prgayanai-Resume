# candidate_app.py - Candidate Dashboard
import streamlit as st
import os
import re
import json
import traceback
from datetime import date

# Simulate importing shared functions and options from ai_core.py
from ai_core import (
    parse_and_store_resume, evaluate_jd_fit, qa_on_resume, qa_on_jd,
    generate_interview_questions, evaluate_interview_answers, extract_jd_metadata,
    extract_jd_from_linkedin_url, question_section_options, IS_AI_ENABLED,
    DEFAULT_JOB_TYPES, DEFAULT_ROLES
)


# -------------------------
# UI PAGES: Authentication & Navigation
# -------------------------
def go_to(page_name):
    """Changes the current page in Streamlit's session state."""
    st.session_state.page = page_name

def login_page():
    st.title("🌐 PragyanAI Job Portal")
    st.header("Login")

    selected_role = st.selectbox(
        "Select Your Role",
        ["Select Role", "Candidate Dashboard", "Admin Dashboard", "Hiring Company Dashboard"],
        key="login_role_select_candidate"
    )
    st.markdown("---")
    email = st.text_input("Email", key="login_email_candidate")
    password = st.text_input("Password", type="password", key="login_password_candidate")

    if st.button("Login", use_container_width=True):
        if selected_role == "Candidate Dashboard" and email and password:
            st.success("Login successful! Redirecting to Candidate Dashboard.")
            go_to("candidate_dashboard")
        elif selected_role == "Select Role":
            st.error("Please select your role before logging in.")
        else:
            st.warning(f"Login simulated for {selected_role} but access denied/redirected.")
    st.markdown("---")
    if st.button("Don't have an account? Sign up here"): go_to("signup")

def signup_page():
    st.header("Create an Account (Candidate)")
    email = st.text_input("Email", key="signup_email_candidate")
    password = st.text_input("Password", type="password", key="signup_password_candidate")
    confirm = st.text_input("Confirm Password", type="password", key="signup_confirm_candidate")

    if st.button("Sign Up", use_container_width=True):
        if password == confirm and email:
            st.success("Signup successful! Please login.")
            go_to("login")
        else:
            st.error("Passwords do not match or email is empty")
    if st.button("Already have an account? Login here"): go_to("login")

# -------------------------
# UTILITY FUNCTIONS
# -------------------------

def clear_interview_state():
    """Clears all generated questions, answers, and the evaluation report."""
    st.session_state.interview_qa = []
    st.session_state.iq_output = ""
    st.session_state.evaluation_report = ""
    st.toast("Practice answers cleared.")

def format_parsed_json_to_markdown(parsed_data):
    """Formats the parsed JSON data into a clean, CV-like Markdown structure."""
    md = ""
    if parsed_data.get('name'):
        md += f"# **{parsed_data['name']}**\n\n"

    contact_info = []
    if parsed_data.get('email'): contact_info.append(parsed_data['email'])
    if parsed_data.get('phone'): contact_info.append(parsed_data['phone'])
    if parsed_data.get('linkedin'): contact_info.append(f"[LinkedIn]({parsed_data['linkedin']})")
    if parsed_data.get('github'): contact_info.append(f"[GitHub]({parsed_data['github']})")

    if contact_info:
        md += f"| {' | '.join(contact_info)} |\n"
        md += "| " + " | ".join(["---"] * len(contact_info)) + " |\n\n"

    section_order = ['personal_details', 'experience', 'projects', 'education', 'certifications', 'skills', 'strength']

    for k in section_order:
        v = parsed_data.get(k)
        if k in ['name', 'email', 'phone', 'linkedin', 'github']: continue

        if v and (isinstance(v, str) and v.strip() or isinstance(v, list) and v):
            md += f"## **{k.replace('_', ' ').upper()}**\n"
            md += "---\n"

            if k == 'personal_details' and isinstance(v, str):
                md += f"{v}\n\n"
            
            # Special handling for structured experience data
            elif k == 'experience' and isinstance(v, list) and all(isinstance(item, dict) for item in v):
                for item in v:
                    title = item.get('title', 'N/A Role')
                    company = item.get('company', 'N/A Company')
                    dates = item.get('dates', 'N/A Dates')
                    responsibilities = item.get('responsibilities', [])
                    
                    md += f"### **{title}** at {company} ({dates})\n"
                    if responsibilities:
                        for resp in responsibilities:
                            md += f"- {resp}\n"
                    md += "\n"
            
            # General list handling
            elif isinstance(v, list):
                for item in v:
                    if item: md += f"- {item}\n"
                md += "\n"
            else:
                md += f"{v}\n\n"
    return md

def generate_cv_html(parsed_data):
    """Generates a simple, print-friendly HTML string from parsed data for PDF conversion."""
    css = """
    <style>
        @page { size: A4; margin: 1cm; }
        body { font-family: 'Arial', sans-serif; line-height: 1.5; margin: 0; padding: 0; font-size: 10pt; }
        .header { text-align: center; border-bottom: 2px solid #333; padding-bottom: 10px; margin-bottom: 20px; }
        .header h1 { margin: 0; font-size: 1.8em; }
        .contact-info { display: flex; justify-content: center; font-size: 0.8em; color: #555; }
        .contact-info span { margin: 0 8px; }
        .section { margin-bottom: 15px; page-break-inside: avoid; }
        .section h2 { border-bottom: 1px solid #999; padding-bottom: 3px; margin-bottom: 8px; font-size: 1.1em; text-transform: uppercase; color: #333; }
        .item-list ul { list-style-type: disc; margin-left: 20px; padding-left: 0; margin-top: 0; }
        .item-list ul li { margin-bottom: 3px; }
        .item-list p { margin: 3px 0 8px 0; }
        .job-entry h3 { font-size: 1.0em; margin-bottom: 2px; }
        .job-entry .job-details { font-style: italic; font-size: 0.9em; margin-bottom: 5px; }
        a { color: #0056b3; text-decoration: none; }
    </style>
    """
    html_content = f"<html><head>{css}<title>{parsed_data.get('name', 'CV')}</title></head><body>"
    html_content += '<div class="header">'
    html_content += f"<h1>{parsed_data.get('name', 'Candidate Name')}</h1>"

    contact_parts = []
    if parsed_data.get('email'): contact_parts.append(f"<span>📧 {parsed_data['email']}</span>")
    if parsed_data.get('phone'): contact_parts.append(f"<span>📱 {parsed_data['phone']}</span>")
    if parsed_data.get('linkedin'): contact_parts.append(f"<span>🔗 <a href='{parsed_data['linkedin']}'>LinkedIn</a></span>")
    if parsed_data.get('github'): contact_parts.append(f"<span>💻 <a href='{parsed_data['github']}'>GitHub</a></span>")
    html_content += f'<div class="contact-info">{" | ".join(contact_parts)}</div>'
    html_content += '</div>'

    section_order = ['personal_details', 'experience', 'projects', 'education', 'certifications', 'skills', 'strength']

    for k in section_order:
        v = parsed_data.get(k)
        if k in ['name', 'email', 'phone', 'linkedin', 'github']: continue

        if v and (isinstance(v, str) and v.strip() or isinstance(v, list) and v):
            html_content += f'<div class="section"><h2>{k.replace("_", " ").title()}</h2>'
            html_content += '<div class="item-list">'

            if k == 'personal_details' and isinstance(v, str): html_content += f"<p>{v}</p>"
            
            # Special HTML handling for structured experience data
            elif k == 'experience' and isinstance(v, list) and all(isinstance(item, dict) for item in v):
                for item in v:
                    title = item.get('title', 'N/A Role')
                    company = item.get('company', 'N/A Company')
                    dates = item.get('dates', 'N/A Dates')
                    responsibilities = item.get('responsibilities', [])

                    html_content += '<div class="job-entry">'
                    html_content += f"<h3>{title}</h3>"
                    html_content += f"<div class='job-details'>{company} | {dates}</div>"
                    if responsibilities:
                        html_content += '<ul>'
                        for resp in responsibilities:
                            if resp: html_content += f"<li>{resp}</li>"
                        html_content += '</ul>'
                    html_content += '</div>'
            
            # General list handling
            elif isinstance(v, list):
                html_content += '<ul>'
                for item in v:
                    if item: html_content += f"<li>{item}</li>"
                html_content += '</ul>'
            else: html_content += f"<p>{v}</p>"

            html_content += '</div></div>'
    html_content += '</body></html>'
    return html_content


# -------------------------
# CANDIDATE DASHBOARD COMPONENTS
# -------------------------

def add_experience_entry():
    """Adds a new experience entry from the input form to the session state list."""
    # Ensure it's a list first, to handle cases where it was previously a string/empty
    if not isinstance(st.session_state.cv_form_data['experience'], list):
         st.session_state.cv_form_data['experience'] = []

    new_entry = {
        'title': st.session_state.new_exp_title,
        'company': st.session_state.new_exp_company,
        'dates': st.session_state.new_exp_dates,
        'responsibilities': [s.strip() for s in st.session_state.new_exp_responsibilities.split('\n') if s.strip()]
    }

    if new_entry['title'] and new_entry['company'] and new_entry['dates']:
        st.session_state.cv_form_data['experience'].append(new_entry)
        
        # Clear inputs after adding
        st.session_state.new_exp_title = ""
        st.session_state.new_exp_company = ""
        st.session_state.new_exp_dates = ""
        st.session_state.new_exp_responsibilities = ""
        st.toast("Professional experience added successfully!")
    else:
        st.error("Please fill in **Role**, **Company**, and **Dates** for the experience entry.")

def remove_experience_entry(index):
    """Removes an experience entry by index."""
    if isinstance(st.session_state.cv_form_data['experience'], list) and 0 <= index < len(st.session_state.cv_form_data['experience']):
        st.session_state.cv_form_data['experience'].pop(index)
        st.toast("Experience removed.")


def cv_management_tab_content():
    st.header("📝 Prepare Your CV")
    st.info("Fill the form, or parse a resume first. The loaded data is used for all analysis tabs.")

    default_parsed = {
        "name": "", "email": "", "phone": "", "linkedin": "", "github": "",
        "skills": [], "experience": [], "education": [], "certifications": [],
        "projects": [], "strength": [], "personal_details": ""
    }
    # Load from current parsed data if available, otherwise use default
    if "cv_form_data" not in st.session_state:
        st.session_state.cv_form_data = st.session_state.get('parsed', default_parsed).copy()
    
    # Ensure experience is a list of dicts for structured input
    if not isinstance(st.session_state.cv_form_data['experience'], list):
        # Attempt to convert simple list/string to list of dicts for backward compatibility/initial load
        if isinstance(st.session_state.cv_form_data['experience'], str):
             exp_list = [e.strip() for e in st.session_state.cv_form_data['experience'].split('\n') if e.strip()]
        elif isinstance(st.session_state.cv_form_data['experience'], list) and not all(isinstance(i, dict) for i in st.session_state.cv_form_data['experience']):
             exp_list = [str(e) for e in st.session_state.cv_form_data['experience'] if e]
        else:
             exp_list = []
        
        # If we found simple text entries, wrap them into a single entry for editing flexibility
        if exp_list:
            st.session_state.cv_form_data['experience'] = [{
                'title': 'Past Experience (Parsed/Text)',
                'company': 'Various',
                'dates': 'See Details',
                'responsibilities': exp_list
            }]
        else:
            st.session_state.cv_form_data['experience'] = []


    st.subheader("1. Form Based CV Builder")
    with st.form("cv_builder_form"):
        col1, col2, col3 = st.columns(3)
        with col1: st.session_state.cv_form_data['name'] = st.text_input("Full Name", value=st.session_state.cv_form_data['name'], key="cv_name_f")
        with col2: st.session_state.cv_form_data['email'] = st.text_input("Email Address", value=st.session_state.cv_form_data['email'], key="cv_email_f")
        with col3: st.session_state.cv_form_data['phone'] = st.text_input("Phone Number", value=st.session_state.cv_form_data['phone'], key="cv_phone_f")

        col4, col5 = st.columns(2)
        with col4: st.session_state.cv_form_data['linkedin'] = st.text_input("LinkedIn Profile URL", value=st.session_state.cv_form_data.get('linkedin', ''), key="cv_linkedin_f")
        with col5: st.session_state.cv_form_data['github'] = st.text_input("GitHub Profile URL", value=st.session_state.cv_form_data.get('github', ''), key="cv_github_f")

        st.markdown("---")
        st.session_state.cv_form_data['personal_details'] = st.text_area("Professional Summary", value=st.session_state.cv_form_data.get('personal_details', ''), height=100, key="cv_personal_details_f")
        st.markdown("---")
        
        # --- NEW PROFESSIONAL EXPERIENCE INPUT ---
        st.subheader("Professional Experience (Add Entries Below)")
        
        # Input form for a single experience entry
        with st.container(border=True):
            st.markdown("##### Add New Experience Entry")
            col_exp1, col_exp2 = st.columns(2)
            with col_exp1:
                st.text_input("Role Worked On", key="new_exp_title")
            with col_exp2:
                st.text_input("Company Name", key="new_exp_company")

            col_exp3, col_exp4 = st.columns([1, 2])
            with col_exp3:
                st.text_input("Dates (e.g., Jan 2020 - Dec 2023)", key="new_exp_dates")
            with col_exp4:
                # Add a dummy input for the role worked on, though we will get the actual data from the keys in add_experience_entry
                st.markdown("---", help="This is a placeholder for the role list input in your original request, simplifying to a text input for Streamlit form compatibility.")
            
            st.text_area("Key Responsibilities (One item per line)", key="new_exp_responsibilities", height=100)
            
            # The button to add the experience entry, outside the main form for immediate update
            if st.form_submit_button("➕ Add Experience Entry", type="secondary", use_container_width=False, on_click=add_experience_entry):
                 # Form submit is already handled by on_click, no need for redundant action here
                 pass
        
        st.markdown("---")
        
        # Display current experience list
        st.markdown("##### Current Professional Experience Entries:")
        if st.session_state.cv_form_data['experience']:
            for i, exp in enumerate(st.session_state.cv_form_data['experience']):
                with st.container(border=True):
                    col_disp1, col_disp2 = st.columns([4, 1])
                    with col_disp1:
                        st.markdown(f"**{exp.get('title', 'N/A Role')}** at *{exp.get('company', 'N/A Company')}* ({exp.get('dates', 'N/A Dates')})")
                        if exp.get('responsibilities'):
                            st.markdown("Key Responsibilities:")
                            st.markdown("\n".join([f"- {r}" for r in exp['responsibilities']]))
                    with col_disp2:
                        st.button("❌ Remove", key=f"remove_exp_{i}", on_click=remove_experience_entry, args=(i,), type="secondary")
        else:
            st.info("No professional experience entries added yet.")
        
        st.markdown("---")
        
        # --- OTHER SECTIONS (KEPT AS TEXT AREAS) ---

        section_keys = ['skills', 'projects', 'education', 'certifications', 'strength']
        st.subheader("Other Sections (List Input)")
        
        for key in section_keys:
            title = key.replace("_", " ").title()
            current_text = "\n".join(st.session_state.cv_form_data.get(key, []))
            new_text = st.text_area(f"{title} (One item/entry per line)", value=current_text, height=120, key=f"cv_{key}_f")
            st.session_state.cv_form_data[key] = [s.strip() for s in new_text.split('\n') if s.strip()]

        submit_form_button = st.form_submit_button("Generate and Load CV Data", use_container_width=True, type="primary")

    if submit_form_button:
        if not st.session_state.cv_form_data['name'] or not st.session_state.cv_form_data['email']:
            st.error("Please fill in at least your **Full Name** and **Email Address**.")
            return

        # Update core session state with form data
        st.session_state.parsed = st.session_state.cv_form_data.copy()
        st.session_state.parsed['name'] = st.session_state.cv_form_data['name']

        # Create a simple full_text version from the form data for LLM context
        compiled_parts = []
        for k, v in st.session_state.cv_form_data.items():
             if k in ['name', 'email', 'phone', 'linkedin', 'github']: continue
             title = k.replace('_', ' ').title()
             if k == 'experience' and isinstance(v, list) and all(isinstance(item, dict) for item in v):
                 exp_text = []
                 for item in v:
                     details = f"Role: {item.get('title', 'N/A')} at {item.get('company', 'N/A')} ({item.get('dates', 'N/A')})\n"
                     resp_text = "\n".join([f"  - {r}" for r in item.get('responsibilities', [])])
                     exp_text.append(details + resp_text)
                 compiled_parts.append(f"{title}:\n\n" + "\n\n".join(exp_text))
             elif v and (isinstance(v, str) and v.strip() or isinstance(v, list) and v):
                compiled_text = "\n".join([f"- {item}" for item in v]) if isinstance(v, list) else str(v)
                compiled_parts.append(f"{title}:\n" + compiled_text)

        st.session_state.full_text = "\n\n".join(compiled_parts)

        st.session_state.candidate_match_results = []
        clear_interview_state()

        st.success(f"✅ CV data for **{st.session_state.parsed['name']}** successfully generated and loaded!")

    st.markdown("---")
    st.subheader("2. Loaded CV Data Preview and Download")

    if st.session_state.get('parsed', {}).get('name'):
        filled_data_for_preview = {
            k: v for k, v in st.session_state.parsed.items()
            if v and (isinstance(v, str) and v.strip() or isinstance(v, list) and v)
        }

        tab_markdown, tab_json, tab_pdf = st.tabs(["📝 Markdown View", "💾 JSON View", "⬇️ PDF/HTML Download"])

        with tab_markdown:
            cv_markdown_preview = format_parsed_json_to_markdown(filled_data_for_preview)
            st.markdown(cv_markdown_preview)
            st.download_button(
                label="⬇️ Download CV as Markdown (.md)", data=cv_markdown_preview,
                file_name=f"{st.session_state.parsed.get('name', 'Generated_CV').replace(' ', '_')}_CV_Document.md",
                mime="text/markdown", key="download_cv_markdown_final"
            )

        with tab_json:
            json_output = json.dumps(st.session_state.parsed, indent=2)
            st.json(st.session_state.parsed)
            st.download_button(
                label="⬇️ Download CV as JSON File", data=json_output,
                file_name=f"{st.session_state.parsed.get('name', 'Generated_CV').replace(' ', '_')}_CV_Data.json",
                mime="application/json", key="download_cv_json_final"
            )

        with tab_pdf:
            st.info("Download the HTML file, open it in your browser, and use **'Print'** (Ctrl/Cmd + P) to **'Save as PDF'**.")
            html_output = generate_cv_html(filled_data_for_preview)
            st.download_button(
                label="⬇️ Download CV as Print-Ready HTML File", data=html_output,
                file_name=f"{st.session_state.parsed.get('name', 'Generated_CV').replace(' ', '_')}_CV_Document.html",
                mime="text/html", key="download_cv_html"
            )
    else:
        st.info("Please fill out the form or parse a resume to see the preview and download options.")

def filter_jd_tab_content():
    st.header("🔍 Filter Job Descriptions by Criteria")

    if not st.session_state.candidate_jd_list:
        st.info("No Job Descriptions are currently loaded. Please add JDs in the 'JD Management' tab.")
        return

    # Extract unique filter options
    unique_roles = sorted(list(set([item.get('role', 'General Analyst') for item in st.session_state.candidate_jd_list] + DEFAULT_ROLES)))
    unique_job_types = sorted(list(set([item.get('job_type', 'Full-time') for item in st.session_state.candidate_jd_list] + DEFAULT_JOB_TYPES)))
    all_unique_skills = set()
    for jd in st.session_state.candidate_jd_list:
        valid_skills = [skill.strip() for skill in jd.get('key_skills', []) if isinstance(skill, str) and skill.strip()]
        all_unique_skills.update(valid_skills)
    unique_skills_list = sorted(list(all_unique_skills))
    if not unique_skills_list: unique_skills_list = ["No skills extracted from current JDs"]

    with st.form(key="jd_filter_form"):
        st.subheader("Select Filters")
        col1, col2, col3 = st.columns(3)

        with col1:
            selected_skills = st.multiselect(
                "Skills Keywords", options=unique_skills_list,
                default=st.session_state.get('last_selected_skills', []), key="candidate_filter_skills_multiselect",
                help="JDs containing ANY of the selected skills will be shown."
            )
        with col2:
            selected_job_type = st.selectbox("Job Type", options=["All Job Types"] + unique_job_types, index=0, key="filter_job_type_select")
        with col3:
            selected_role = st.selectbox("Role Title", options=["All Roles"] + unique_roles, index=0, key="filter_role_select")

        apply_filters_button = st.form_submit_button("✅ Apply Filters", type="primary", use_container_width=True)

    if apply_filters_button:
        st.session_state.last_selected_skills = selected_skills

        filtered_jds = []
        selected_skills_lower = [k.strip().lower() for k in selected_skills]

        for jd in st.session_state.candidate_jd_list:
            role_match = (selected_role == "All Roles") or (selected_role == jd.get('role', ''))
            job_type_match = (selected_job_type == "All Job Types") or (selected_job_type == jd.get('job_type', ''))
            skill_match = True
            if selected_skills_lower:
                jd_key_skills_lower = [s.lower() for s in jd.get('key_skills', []) if isinstance(s, str) and s.strip()]
                if not any(k in jd_key_skills_lower for k in selected_skills_lower):
                    skill_match = False

            if role_match and job_type_match and skill_match:
                filtered_jds.append(jd)

        st.session_state.filtered_jds_display = filtered_jds
        st.success(f"Filter applied! Found **{len(filtered_jds)}** matching Job Descriptions.")

    # Display Results
    st.markdown("---")
    filtered_jds = st.session_state.get('filtered_jds_display', [])
    st.subheader(f"Matching Job Descriptions ({len(filtered_jds)} found)")

    if filtered_jds:
        display_data = [{
            "Job Description Title": jd['name'].replace("--- Simulated JD for: ", ""),
            "Role": jd.get('role', 'N/A'),
            "Job Type": jd.get('job_type', 'N/A'),
            "Key Skills": ", ".join(jd.get('key_skills', ['N/A'])[:5]) + "...",
        } for jd in filtered_jds]

        st.dataframe(display_data, use_container_width=True)

        st.markdown("##### Detailed View")
        for idx, jd in enumerate(filtered_jds, 1):
            with st.expander(f"JD {idx}: {jd['name'].replace('--- Simulated JD for: ', '')} - ({jd.get('role', 'N/A')})"):
                st.markdown(f"**Job Type:** {jd.get('job_type', 'N/A')}")
                st.markdown(f"**Extracted Skills:** {', '.join(jd.get('key_skills', ['N/A']))}")
                st.markdown("---")
                st.text(jd['content'])
    elif st.session_state.candidate_jd_list and apply_filters_button:
        st.info("No Job Descriptions match the selected criteria.")
    elif st.session_state.candidate_jd_list and not apply_filters_button:
        st.info("Use the filters above and click **'Apply Filters'** to view matching Job Descriptions.")


def candidate_dashboard():
    st.title("👩‍🎓 Candidate Dashboard")

    nav_col, _ = st.columns([1, 1])
    with nav_col:
        if st.button("🚪 Log Out", key="candidate_logout_btn", use_container_width=True):
            go_to("login")

    # Sidebar for Status
    with st.sidebar:
        st.header("Resume/CV Status")
        if st.session_state.parsed.get("name"):
            st.success(f"Currently loaded: **{st.session_state.parsed['name']}**")
        else:
            st.info("Please upload a file or use the CV builder to begin.")
            
    is_resume_parsed = bool(st.session_state.get('parsed', {}).get('name')) or bool(st.session_state.get('full_text'))

    # Main Content Tabs
    tab_cv_mgmt, tab_parsing, tab_jd_mgmt, tab_batch_match, tab_filter_jd, tab_chatbot, tab_interview_prep = st.tabs([
        "✍️ CV Management", "📄 Resume Parsing", "📚 JD Management", "🎯 Batch JD Match",
        "🔍 Filter JD", "💬 Resume/JD Chatbot (Q&A)", "❓ Interview Prep"
    ])

    # --- TAB 1: CV Management ---
    with tab_cv_mgmt:
        cv_management_tab_content()

    # --- TAB 2: Resume Parsing ---
    with tab_parsing:
        st.header("📄 Resume Upload and Parsing")
        input_method = st.radio("Select Input Method", ["Upload File", "Paste Text"], key="parsing_input_method")
        st.markdown("---")

        file_to_parse = None
        if input_method == "Upload File":
            st.subheader("1. Upload Resume File")
            uploaded_file = st.file_uploader(
                "Choose PDF, DOCX, TXT, JSON, etc.", type=["pdf", "docx", "txt", "json", "md", "csv", "xlsx", "markdown", "rtf"],
                accept_multiple_files=False, key='candidate_file_upload_main'
            )
            file_to_parse = uploaded_file
            st.subheader("2. Parse Uploaded File")
            
        else: # input_method == "Paste Text"
            st.subheader("1. Paste Your CV Text")
            pasted_text = st.text_area("Copy and paste your entire CV or resume text here.", height=300, key='pasted_cv_text_input')
            file_to_parse = pasted_text
            st.subheader("2. Parse Pasted Text")


        if file_to_parse and (input_method == "Upload File" or (input_method == "Paste Text" and file_to_parse.strip())):
            file_name_display = file_to_parse.name if input_method == "Upload File" else "Pasted Text"
            source_type = 'file' if input_method == "Upload File" else 'text'

            if st.button(f"Parse and Load: **{file_name_display}**", key="parse_file_btn", use_container_width=True, type="primary"):
                with st.spinner(f"Parsing {file_name_display}..."):
                    result = parse_and_store_resume(file_to_parse, file_name_key='single_resume_candidate', source_type=source_type)
                    if "error" not in result:
                        st.session_state.parsed = result['parsed']
                        st.session_state.full_text = result['full_text']
                        st.session_state.parsed['name'] = result['name']
                        clear_interview_state()
                        st.success(f"✅ Successfully loaded and parsed **{result['name']}**.")
                        st.info("View, edit, and download the parsed data in the **CV Management** tab.")
                    else:
                        st.error(f"Parsing failed for {file_name_display}: {result['error']}")
                        st.session_state.parsed = {"error": result['error'], "name": result['name']}
                        st.session_state.full_text = result['full_text'] or ""
        else:
            st.info("Please provide a file or paste text to enable parsing.")

    # --- TAB 3: JD Management (Candidate) ---
    with tab_jd_mgmt:
        st.header("📚 Manage Job Descriptions for Matching")

        jd_type = st.radio("Select JD Type", ["Single JD", "Multiple JD"], key="jd_type_candidate", horizontal=True)
        method = st.radio("Choose Method", ["Upload File", "Paste Text", "LinkedIn URL"], key="jd_add_method_candidate", horizontal=True)
        st.markdown("---")

        if method == "LinkedIn URL":
            input_data = st.text_area("Enter URL(s) (comma separated)", key="url_list_candidate", height=100)
            data_list = [u.strip() for u in input_data.split(",")] if jd_type == "Multiple JD" else [input_data.strip()]
            
            if st.button("Add JD(s) from URL", key="add_jd_url_btn_candidate") and input_data:
                count = 0
                for url in data_list:
                    if not url: continue
                    with st.spinner(f"Extracting JD for: {url}"):
                        jd_text = extract_jd_from_linkedin_url(url)
                        metadata = extract_jd_metadata(jd_text)
                    name = f"JD from URL: {metadata.get('role', 'N/A')}"
                    st.session_state.candidate_jd_list.append({"name": name, "content": jd_text, **metadata})
                    if not jd_text.startswith("[Error"): count += 1
                if count > 0: st.success(f"✅ {count} JD(s) added successfully!")
                else: st.error("No JDs were added successfully.")

        elif method == "Paste Text":
            input_data = st.text_area("Paste JD text(s) (separate by '---' for multiple)", key="text_list_candidate", height=200)
            data_list = [t.strip() for t in input_data.split("---")] if jd_type == "Multiple JD" else [input_data.strip()]

            if st.button("Add JD(s) from Text", key="add_jd_text_btn_candidate") and input_data:
                for text in data_list:
                     if text:
                        metadata = extract_jd_metadata(text)
                        name = metadata.get('role', f"Pasted JD {len(st.session_state.candidate_jd_list) + 1}")
                        st.session_state.candidate_jd_list.append({"name": name, "content": text, **metadata})
                st.success(f"✅ {len(data_list)} JD(s) added successfully!")

        elif method == "Upload File":
            uploaded_files = st.file_uploader(
                "Upload JD file(s)", type=["pdf", "txt", "docx"], accept_multiple_files=(jd_type == "Multiple JD"), key="jd_file_uploader_candidate"
            )
            if st.button("Add JD(s) from File", key="add_jd_file_btn_candidate"):
                files_to_process = uploaded_files if isinstance(uploaded_files, list) else ([uploaded_files] if uploaded_files else [])
                count = 0
                for file in files_to_process:
                    if file:
                        result = parse_and_store_resume(file, file_name_key='jd_file_candidate', source_type='file')
                        if "error" not in result:
                            jd_text = result['full_text']
                            metadata = extract_jd_metadata(jd_text)
                            st.session_state.candidate_jd_list.append({"name": file.name, "content": jd_text, **metadata})
                            count += 1
                        else: st.error(f"Error extracting content from {file.name}: {result['error']}")
                if count > 0: st.success(f"✅ {count} JD(s) added successfully!")
                elif uploaded_files: st.error("No valid JD files were uploaded.")

        st.markdown("---")
        # Display/Clear JDs
        if st.session_state.candidate_jd_list:
            col_display_header, col_clear_button = st.columns([3, 1])
            with col_display_header: st.markdown("### ✅ Current JDs Added:")
            with col_clear_button:
                if st.button("🗑️ Clear All JDs", key="clear_jds_candidate", use_container_width=True, type="secondary"):
                    st.session_state.candidate_jd_list = []
                    st.session_state.candidate_match_results = []
                    st.session_state.filtered_jds_display = []
                    st.success("All JDs cleared.")
                    st.rerun()

            for idx, jd_item in enumerate(st.session_state.candidate_jd_list, 1):
                display_title = jd_item['name'].replace("--- Simulated JD for: ", "")
                with st.expander(f"JD {idx}: {display_title} | Role: {jd_item.get('role', 'N/A')}"):
                    st.markdown(f"**Job Type:** {jd_item.get('job_type', 'N/A')} | **Key Skills:** {', '.join(jd_item.get('key_skills', ['N/A']))}")
                    st.markdown("---")
                    st.text(jd_item['content'])
        else: st.info("No Job Descriptions added yet.")

    # --- TAB 4: Batch JD Match (Candidate) ---
    with tab_batch_match:
        st.header("🎯 Batch JD Match: Best Matches")
        if not is_resume_parsed: st.warning("Please **upload and parse your resume** or **build your CV** first.")
        elif not st.session_state.candidate_jd_list: st.error("Please **add Job Descriptions** in the 'JD Management' tab.")
        elif not IS_AI_ENABLED: st.error("Cannot use JD Match: AI is not configured.")
        else:
            all_jd_names = [item['name'] for item in st.session_state.candidate_jd_list]
            selected_jd_names = st.multiselect("Select Job Descriptions to Match Against", options=all_jd_names, default=all_jd_names, key='candidate_batch_jd_select')
            jds_to_match = [jd_item for jd_item in st.session_state.candidate_jd_list if jd_item['name'] in selected_jd_names]

            if st.button(f"Run Match Analysis on {len(jds_to_match)} Selected JD(s)", key="run_match_btn", type="primary"):
                st.session_state.candidate_match_results = []
                if not jds_to_match: st.warning("Please select at least one Job Description.")
                else:
                    results_with_score = []
                    with st.spinner(f"Matching resume against {len(jds_to_match)} selected JD(s)..."):
                        for jd_item in jds_to_match:
                            try:
                                fit_output = evaluate_jd_fit(jd_item['content'], st.session_state.parsed)
                                overall_score_match = re.search(r'Overall Fit Score:\s*[^\d]*(\d+)\s*/10', fit_output, re.IGNORECASE)
                                section_analysis_match = re.search(r'--- Section Match Analysis ---\s*(.*?)\s*Strengths/Matches:', fit_output, re.DOTALL)

                                skills_percent, experience_percent, education_percent = 'N/A', 'N/A', 'N/A'
                                if section_analysis_match:
                                    section_text = section_analysis_match.group(1)
                                    skills_match = re.search(r'Skills Match:\s*\[?(\d+)%\]?', section_text, re.IGNORECASE)
                                    experience_match = re.search(r'Experience Match:\s*\[?(\d+)%\]?', section_text, re.IGNORECASE)
                                    education_match = re.search(r'Education Match:\s*\[?(\d+)%\]?', section_text, re.IGNORECASE)

                                    if skills_match: skills_percent = skills_match.group(1)
                                    if experience_match: experience_percent = experience_match.group(1)
                                    if education_match: education_percent = education_match.group(1)

                                overall_score = overall_score_match.group(1) if overall_score_match else 'N/A'
                                results_with_score.append({
                                    "jd_name": jd_item['name'], "overall_score": overall_score,
                                    "numeric_score": int(overall_score) if overall_score.isdigit() else -1,
                                    "skills_percent": skills_percent, "experience_percent": experience_percent,
                                    "education_percent": education_percent, "full_analysis": fit_output
                                })
                            except Exception as e: results_with_score.append({"jd_name": jd_item['name'], "overall_score": "Error", "numeric_score": -1, "full_analysis": f"Error: {e}"})

                        results_with_score.sort(key=lambda x: x['numeric_score'], reverse=True)
                        current_rank = 1; current_score = -1
                        for i, item in enumerate(results_with_score):
                            if item['numeric_score'] > current_score: current_rank = i + 1; current_score = item['numeric_score']
                            item['rank'] = current_rank
                            del item['numeric_score']
                        st.session_state.candidate_match_results = results_with_score
                    st.success("Batch analysis complete!")

            if st.session_state.get('candidate_match_results'):
                st.markdown("#### Match Results for Your Resume")
                display_data = []
                for item in st.session_state.candidate_match_results:
                    full_jd_item = next((jd for jd in st.session_state.candidate_jd_list if jd['name'] == item['jd_name']), {})
                    display_data.append({
                        "Rank": item.get("rank", "N/A"),
                        "Job Description (Ranked)": item["jd_name"].replace("--- Simulated JD for: ", ""),
                        "Role": full_jd_item.get('role', 'N/A'), "Job Type": full_jd_item.get('job_type', 'N/A'),
                        "Fit Score (out of 10)": item["overall_score"],
                        "Skills (%)": item.get("skills_percent", "N/A"), "Experience (%)": item.get("experience_percent", "N/A"),
                        "Education (%)": item.get("education_percent", "N/A"),
                    })
                st.dataframe(display_data, use_container_width=True)

                st.markdown("##### Detailed Reports")
                for item in st.session_state.candidate_match_results:
                    header_text = f"Rank {item.get('rank', 'N/A')} | Report for **{item['jd_name'].replace('--- Simulated JD for: ', '')}** (Score: **{item['overall_score']}/10**)"
                    with st.expander(header_text): st.markdown(item['full_analysis'])

    # --- TAB 5: Filter JD ---
    with tab_filter_jd:
        filter_jd_tab_content()

    # --- TAB 6: Resume/JD Chatbot (Q&A) ---
    with tab_chatbot:
        st.header("💬 Resume/JD Chatbot (Q&A)")
        sub_tab_resume, sub_tab_jd = st.tabs(["👤 Chat about Your Resume", "📄 Chat about Saved JDs"])

        if not IS_AI_ENABLED: st.error("Cannot use Chatbot: AI is not configured.")
        else:
            with sub_tab_resume:
                st.markdown("### Ask any question about the currently loaded resume.")
                if not is_resume_parsed: st.warning("Please upload and parse a resume first.")
                else:
                    question = st.text_input("Your Question (about Resume)", placeholder="e.g., What are the candidate's key skills?", key="resume_qa_question")
                    if st.button("Get Answer (Resume)", key="qa_btn_resume"):
                        with st.spinner("Generating answer..."):
                            try:
                                answer = qa_on_resume(st.session_state.parsed, st.session_state.full_text, question)
                                st.session_state.qa_answer_resume = answer
                            except Exception as e: st.error(f"Error: {e}"); st.session_state.qa_answer_resume = "Could not generate an answer."
                    if st.session_state.get('qa_answer_resume'): st.text_area("Answer (Resume)", st.session_state.qa_answer_resume, height=150)

            with sub_tab_jd:
                st.markdown("### Ask any question about a saved Job Description.")
                if not st.session_state.candidate_jd_list: st.warning("Please add Job Descriptions in the 'JD Management' tab first.")
                else:
                    jd_names = [jd['name'] for jd in st.session_state.candidate_jd_list]
                    selected_jd_name = st.selectbox("Select Job Description to Query", options=jd_names, key="jd_qa_select")
                    question = st.text_input("Your Question (about JD)", placeholder="e.g., What is the minimum experience required for this role?", key="jd_qa_question")
                    if st.button("Get Answer (JD)", key="qa_btn_jd"):
                        if selected_jd_name and question.strip():
                            with st.spinner(f"Generating answer for {selected_jd_name}..."):
                                try:
                                    jd_item = next((jd for jd in st.session_state.candidate_jd_list if jd['name'] == selected_jd_name), None)
                                    answer = qa_on_jd(jd_item, question)
                                    st.session_state.qa_answer_jd = answer
                                except Exception as e: st.error(f"Error: {e}"); st.session_state.qa_answer_jd = "Could not generate an answer."
                        else: st.error("Please select a JD and enter a question.")
                    if st.session_state.get('qa_answer_jd'): st.text_area("Answer (JD)", st.session_state.qa_answer_jd, height=150)

    # --- TAB 7: Interview Prep ---
    with tab_interview_prep:
        st.header("❓ Interview Preparation Tools")

        if not is_resume_parsed: st.warning("Please upload and successfully parse a resume first.")
        elif not IS_AI_ENABLED: st.error("Cannot use Interview Prep: AI is not configured.")
        else:
            st.subheader("1. Generate Interview Questions")
            section_choice = st.selectbox("Select Resume Section to Base Questions On", question_section_options, key='iq_section_c', on_change=clear_interview_state)

            if st.button("Generate Interview Questions", key='iq_btn_c', type="secondary"):
                with st.spinner("Generating questions..."):
                    try:
                        raw_questions_response = generate_interview_questions(st.session_state.parsed, section_choice)
                        st.session_state.iq_output = raw_questions_response
                        st.session_state.interview_qa = []
                        st.session_state.evaluation_report = ""
                        q_list = []
                        current_level = ""
                        for line in raw_questions_response.splitlines():
                            line = line.strip()
                            if line.startswith('[') and line.endswith(']'): current_level = line.strip('[]')
                            elif line.lower().startswith('q') and ':' in line:
                                question_text = line[line.find(':') + 1:].strip()
                                q_list.append({"question": f"({current_level}) {question_text}", "answer": "", "level": current_level})
                        st.session_state.interview_qa = q_list
                        st.success(f"Generated {len(q_list)} questions.")
                    except Exception as e: st.error(f"Error generating questions: {e}"); st.session_state.iq_output = "Error generating questions."

            if st.session_state.get('interview_qa'):
                st.markdown("---")
                st.subheader("2. Practice and Record Answers")
                with st.form("interview_practice_form"):
                    for i, qa_item in enumerate(st.session_state.interview_qa):
                        st.markdown(f"**Question {i+1}:** {qa_item['question']}")
                        answer = st.text_area(f"Your Answer for Q{i+1}", value=st.session_state.interview_qa[i]['answer'], height=100, key=f'answer_q_{i}', label_visibility='collapsed')
                        st.session_state.interview_qa[i]['answer'] = answer
                    submit_button = st.form_submit_button("Submit & Evaluate Answers", use_container_width=True, type="primary")

                    if submit_button:
                        if all(item['answer'].strip() for item in st.session_state.interview_qa):
                            with st.spinner("Sending answers to AI Evaluator..."):
                                try:
                                    report = evaluate_interview_answers(st.session_state.interview_qa, st.session_state.parsed)
                                    st.session_state.evaluation_report = report
                                    st.success("Evaluation complete!")
                                except Exception as e: st.error(f"Evaluation failed: {e}"); st.session_state.evaluation_report = f"Evaluation failed: {e}\n{traceback.format_exc()}"
                        else: st.error("Please answer all generated questions before submitting.")

                if st.session_state.get('evaluation_report'):
                    st.markdown("---")
                    st.subheader("3. AI Evaluation Report")
                    st.markdown(st.session_state.evaluation_report)


# -------------------------
# Main App Execution for Candidate
# -------------------------
def main():
    st.set_page_config(layout="wide", page_title="Candidate Portal")

    # --- Session State Initialization (Streamlined) ---
    if 'page' not in st.session_state: st.session_state.page = "login"
    if 'parsed' not in st.session_state: st.session_state.parsed = {}
    if 'full_text' not in st.session_state: st.session_state.full_text = ""
    if 'candidate_jd_list' not in st.session_state: st.session_state.candidate_jd_list = []
    if 'candidate_match_results' not in st.session_state: st.session_state.candidate_match_results = []
    if 'interview_qa' not in st.session_state: st.session_state.interview_qa = []
    if 'evaluation_report' not in st.session_state: st.session_state.evaluation_report = ""
    if 'qa_answer_resume' not in st.session_state: st.session_state.qa_answer_resume = ""
    if 'qa_answer_jd' not in st.session_state: st.session_state.qa_answer_jd = ""
    if "filtered_jds_display" not in st.session_state: st.session_state.filtered_jds_display = []
    if "last_selected_skills" not in st.session_state: st.session_state.last_selected_skills = []
    
    # New state vars for CV Management Form Inputs
    if "cv_form_data" not in st.session_state: st.session_state.cv_form_data = {}
    if "new_exp_title" not in st.session_state: st.session_state.new_exp_title = ""
    if "new_exp_company" not in st.session_state: st.session_state.new_exp_company = ""
    if "new_exp_dates" not in st.session_state: st.session_state.new_exp_dates = ""
    if "new_exp_responsibilities" not in st.session_state: st.session_state.new_exp_responsibilities = ""


    # --- Page Routing ---
    if st.session_state.page == "login":
        login_page()
    elif st.session_state.page == "signup":
        signup_page()
    elif st.session_state.page == "candidate_dashboard":
        candidate_dashboard()


if __name__ == '__main__':
    main()
