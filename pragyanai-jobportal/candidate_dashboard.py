import streamlit as st
import re
import json
import traceback
import tempfile
from datetime import date 

# =========================================================================
# NOTE: YOU MUST ENSURE THESE FUNCTIONS AND VARIABLES ARE CORRECTLY DEFINED
# AND IMPORTED FROM YOUR main application file (e.g., app.py).
# Failure to define these will result in the ModuleNotFoundError you saw.
# =========================================================================

try:
    # Attempt to import all necessary functions and clients from the main app file
    from app import (
        go_to, 
        clear_interview_state, 
        parse_and_store_resume, 
        qa_on_resume, 
        generate_interview_questions, 
        evaluate_interview_answers, 
        evaluate_jd_fit, 
        extract_jd_metadata, 
        extract_jd_from_linkedin_url, 
        DEFAULT_JOB_TYPES, 
        DEFAULT_ROLES
    )
    # Ensure the Groq/LLM client and config are imported for the new JD Chatbot
    from app import client, GROQ_MODEL, GROQ_API_KEY 
except ImportError as e:
    st.error(f"FATAL ERROR: Could not import necessary components from 'app.py'. Please ensure 'app.py' exists and defines all required functions/variables. Error: {e}")
    # Define placeholder functions/variables to prevent immediate crash if app.py is missing/empty
    go_to = lambda x: st.warning("Navigation function 'go_to' not imported.")
    clear_interview_state = lambda: st.session_state.update(interview_qa=[], evaluation_report="")
    DEFAULT_JOB_TYPES = ["Full-time", "Part-time", "Contract"]
    DEFAULT_ROLES = ["Software Engineer", "Data Analyst", "Project Manager"]
    # Placeholder for LLM client if import fails
    client = None 
    GROQ_MODEL = "mixtral-8x7b-32768"
    GROQ_API_KEY = None


# --- NEW JD Chatbot Function (Relies on client and keys from app.py) ---

def jd_qa_on_jd(question, jd_content):
    """Chatbot for Job Description (Q&A) using LLM."""
    global client
    
    if not GROQ_API_KEY or not client:
        return "AI Chatbot Disabled: GROQ_API_KEY is not set or LLM client not initialized."
        
    prompt = f"""Given the following Job Description (JD):
    JD Content: {jd_content}
    
    Answer the following question about the JD concisely and directly.
    If the information is not present in the JD, state that clearly (e.g., "The JD does not specify the salary range.").
    
    Question: {question}
    """
    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL, 
            messages=[{"role": "user", "content": prompt}], 
            temperature=0.4
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Error communicating with LLM API: {e}. Check GROQ_API_KEY and network connection."

# --- Candidate Helper Functions ---

def generate_cv_html(parsed_data):
    """Generates a simple, print-friendly HTML string from parsed data for PDF conversion."""
    
    # Simple CSS for a clean, print-friendly CV look
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
        a { color: #0056b3; text-decoration: none; }
    </style>
    """
    
    # --- HTML Structure ---
    html_content = f"<html><head>{css}<title>{parsed_data.get('name', 'CV')}</title></head><body>"
    
    # 1. Header and Contact Info
    html_content += '<div class="header">'
    html_content += f"<h1>{parsed_data.get('name', 'Candidate Name')}</h1>"
    
    contact_parts = []
    if parsed_data.get('email'): contact_parts.append(f"<span>📧 {parsed_data['email']}</span>")
    if parsed_data.get('phone'): contact_parts.append(f"<span>📱 {parsed_data['phone']}</span>")
    if parsed_data.get('linkedin'): contact_parts.append(f"<span>🔗 <a href='{parsed_data['linkedin']}'>{parsed_data.get('linkedin', 'LinkedIn').split('/')[-1] if parsed_data.get('linkedin') else 'LinkedIn'}</a></span>")
    if parsed_data.get('github'): contact_parts.append(f"<span>💻 <a href='{parsed_data['github']}'>{parsed_data.get('github', 'GitHub').split('/')[-1] if parsed_data.get('github') else 'GitHub'}</a></span>")
    
    html_content += f'<div class="contact-info">{" | ".join(contact_parts)}</div>'
    html_content += '</div>'
    
    # 2. Sections
    section_order = ['personal_details', 'experience', 'projects', 'education', 'certifications', 'skills', 'strength']
    
    for k in section_order:
        v = parsed_data.get(k)
        
        if k in ['name', 'email', 'phone', 'linkedin', 'github']: continue 

        if v and (isinstance(v, str) and v.strip() or isinstance(v, list) and v):
            
            html_content += f'<div class="section"><h2>{k.replace("_", " ").title()}</h2>'
            html_content += '<div class="item-list">'
            
            if k == 'personal_details' and isinstance(v, str):
                html_content += f"<p>{v}</p>"
            elif isinstance(v, list):
                html_content += '<ul>'
                for item in v:
                    if item: 
                        html_content += f"<li>{item}</li>"
                html_content += '</ul>'
            else:
                html_content += f"<p>{v}</p>"
                
            html_content += '</div></div>'

    html_content += '</body></html>'
    return html_content


def cv_management_tab_content():
    st.header("📝 Prepare Your CV")
    st.markdown("### 1. Form Based CV Builder")

    default_parsed = {
        "name": "", "email": "", "phone": "", "linkedin": "", "github": "",
        "skills": [], "experience": [], "education": [], "certifications": [], 
        "projects": [], "strength": [], "personal_details": ""
    }
    
    if "cv_form_data" not in st.session_state:
        # Load existing parsed data if available
        if st.session_state.get('parsed', {}).get('name'):
            st.session_state.cv_form_data = st.session_state.parsed.copy()
        else:
            st.session_state.cv_form_data = default_parsed
    
    # --- CV Builder Form ---
    with st.form("cv_builder_form"):
        st.subheader("Personal & Contact Details")
        
        # Row 1: Name, Email, Phone
        col1, col2, col3 = st.columns(3)
        with col1: st.session_state.cv_form_data['name'] = st.text_input("Full Name", value=st.session_state.cv_form_data['name'], key="cv_name")
        with col2: st.session_state.cv_form_data['email'] = st.text_input("Email Address", value=st.session_state.cv_form_data['email'], key="cv_email")
        with col3: st.session_state.cv_form_data['phone'] = st.text_input("Phone Number", value=st.session_state.cv_form_data['phone'], key="cv_phone")
        
        # Row 2: LinkedIn, GitHub
        col4, col5 = st.columns(2)
        with col4: st.session_state.cv_form_data['linkedin'] = st.text_input("LinkedIn Profile URL", value=st.session_state.cv_form_data.get('linkedin', ''), key="cv_linkedin")
        with col5: st.session_state.cv_form_data['github'] = st.text_input("GitHub Profile URL", value=st.session_state.cv_form_data.get('github', ''), key="cv_github")
        
        # Row 3: Summary/Personal Details 
        st.markdown("---")
        st.subheader("Summary / Personal Details")
        st.session_state.cv_form_data['personal_details'] = st.text_area("Professional Summary or Personal Details", value=st.session_state.cv_form_data.get('personal_details', ''), height=100, key="cv_personal_details")
        
        st.markdown("---")
        st.subheader("Technical Sections (One Item per Line)")

        # Skills
        skills_text = "\n".join(st.session_state.cv_form_data.get('skills', []))
        new_skills_text = st.text_area("Key Skills (Technical and Soft)", value=skills_text, height=150, key="cv_skills")
        st.session_state.cv_form_data['skills'] = [s.strip() for s in new_skills_text.split('\n') if s.strip()]
        
        # Experience
        experience_text = "\n".join(st.session_state.cv_form_data.get('experience', []))
        new_experience_text = st.text_area("Professional Experience (Job Roles, Companies, Dates, Key Responsibilities)", value=experience_text, height=150, key="cv_experience")
        st.session_state.cv_form_data['experience'] = [e.strip() for e in new_experience_text.split('\n') if e.strip()]

        # Education
        education_text = "\n".join(st.session_state.cv_form_data.get('education', []))
        new_education_text = st.text_area("Education (Degrees, Institutions, Dates)", value=education_text, height=100, key="cv_education")
        st.session_state.cv_form_data['education'] = [d.strip() for d in new_education_text.split('\n') if d.strip()]
        
        # Certifications
        certifications_text = "\n".join(st.session_state.cv_form_data.get('certifications', []))
        new_certifications_text = st.text_area("Certifications (Name, Issuing Body, Date)", value=certifications_text, height=100, key="cv_certifications")
        st.session_state.cv_form_data['certifications'] = [c.strip() for c in new_certifications_text.split('\n') if c.strip()]
        
        # Projects
        projects_text = "\n".join(st.session_state.cv_form_data.get('projects', []))
        new_projects_text = st.text_area("Projects (Name, Description, Technologies)", value=projects_text, height=150, key="cv_projects")
        st.session_state.cv_form_data['projects'] = [p.strip() for p in new_projects_text.split('\n') if p.strip()]
        
        # Strengths
        strength_text = "\n".join(st.session_state.cv_form_data.get('strength', []))
        new_strength_text = st.text_area("Strengths / Key Personal Qualities (One per line)", value=strength_text, height=100, key="cv_strength")
        st.session_state.cv_form_data['strength'] = [s.strip() for s in new_strength_text.split('\n') if s.strip()]


        submit_form_button = st.form_submit_button("Generate and Load CV Data", use_container_width=True)

    if submit_form_button:
        if not st.session_state.cv_form_data['name'] or not st.session_state.cv_form_data['email']:
            st.error("Please fill in at least your **Full Name** and **Email Address**.")
            return

        st.session_state.parsed = st.session_state.cv_form_data.copy()
        st.session_state.parsed['name'] = st.session_state.cv_form_data['name']
        
        # Compile a raw text version for utility and parsing functions
        compiled_text = ""
        for k, v in st.session_state.cv_form_data.items():
            if v:
                compiled_text += f"{k.replace('_', ' ').title()}:\n"
                if isinstance(v, list):
                    compiled_text += "\n".join([f"- {item}" for item in v]) + "\n\n"
                else:
                    compiled_text += str(v) + "\n\n"
        st.session_state.full_text = compiled_text
        
        clear_interview_state()
        st.session_state.candidate_match_results = []
        st.success(f"✅ CV data for **{st.session_state.parsed['name']}** successfully generated and loaded!")
        
    st.markdown("---")
    st.subheader("2. Loaded CV Data Preview and Download")
    
    if st.session_state.get('parsed', {}).get('name'):
        
        filled_data_for_preview = {
            k: v for k, v in st.session_state.parsed.items() 
            if v and (isinstance(v, str) and v.strip() or isinstance(v, list) and v)
        }
        
        def format_parsed_json_to_markdown(parsed_data):
            """Formats the parsed JSON data into a clean, CV-like Markdown structure."""
            md = ""
            if parsed_data.get('name'): md += f"# **{parsed_data['name']}**\n\n"
            contact_info = []
            if parsed_data.get('email'): contact_info.append(parsed_data['email'])
            if parsed_data.get('phone'): contact_info.append(parsed_data['phone'])
            if contact_info: md += f"| {' | '.join(contact_info)} |\n| " + " | ".join(["---"] * len(contact_info)) + " |\n\n"
            
            section_order = ['personal_details', 'experience', 'projects', 'education', 'certifications', 'skills', 'strength']
            for k in section_order:
                v = parsed_data.get(k)
                if k in ['name', 'email', 'phone', 'linkedin', 'github']: continue 
                if v and (isinstance(v, str) and v.strip() or isinstance(v, list) and v):
                    md += f"## **{k.replace('_', ' ').upper()}**\n---\n"
                    if k == 'personal_details' and isinstance(v, str): md += f"{v}\n\n"
                    elif isinstance(v, list):
                        for item in v:
                            if item: md += f"- {item}\n"
                        md += "\n"
                    else: md += f"{v}\n\n"
            return md


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
            st.json(st.session_state.parsed)
            json_output = json.dumps(st.session_state.parsed, indent=2)
            st.download_button(
                label="⬇️ Download CV as JSON File", data=json_output,
                file_name=f"{st.session_state.parsed.get('name', 'Generated_CV').replace(' ', '_')}_CV_Data.json",
                mime="application/json", key="download_cv_json_final"
            )

        with tab_pdf:
            st.markdown("### Download CV as HTML (Print-to-PDF)")
            html_output = generate_cv_html(filled_data_for_preview)
            st.download_button(
                label="⬇️ Download CV as Print-Ready HTML File (for PDF conversion)", data=html_output,
                file_name=f"{st.session_state.parsed.get('name', 'Generated_CV').replace(' ', '_')}_CV_Document.html",
                mime="text/html", key="download_cv_html"
            )
            st.markdown("---")
            st.markdown("### Raw Text Data Download (for utility)")
            st.download_button(
                label="⬇️ Download All CV Data as Raw Text (.txt)", data=st.session_state.full_text,
                file_name=f"{st.session_state.parsed.get('name', 'Generated_CV').replace(' ', '_')}_Raw_Data.txt",
                mime="text/plain", key="download_cv_txt_final"
            )
            
    else:
        st.info("Please fill out the form above and click 'Generate and Load CV Data' or parse a resume in the 'Resume Parsing' tab to see the preview and download options.")


def filter_jd_tab_content():
    st.header("🔍 Filter Job Descriptions by Criteria")
    st.markdown("Use the filters below to narrow down your saved Job Descriptions.")

    if not st.session_state.get('candidate_jd_list'):
        st.info("No Job Descriptions are currently loaded. Please add JDs in the 'JD Management' tab (Tab 4).")
        if 'filtered_jds_display' not in st.session_state: st.session_state.filtered_jds_display = []
        return
    
    # --- Skill and Role Extraction ---
    unique_roles = sorted(list(set(
        [item.get('role', 'General Analyst') for item in st.session_state.candidate_jd_list] + DEFAULT_ROLES
    )))
    unique_job_types = sorted(list(set(
        [item.get('job_type', 'Full-time') for item in st.session_state.candidate_jd_list] + DEFAULT_JOB_TYPES
    )))
    
    STARTER_KEYWORDS = {"Python", "MySQL", "GCP", "cloud computing", "ML", "API services", "LLM integration", "JavaScript", "SQL", "AWS"}
    all_unique_skills = set(STARTER_KEYWORDS)
    for jd in st.session_state.candidate_jd_list:
        valid_skills = [skill.strip() for skill in jd.get('key_skills', []) if isinstance(skill, str) and skill.strip()]
        all_unique_skills.update(valid_skills)
    unique_skills_list = sorted(list(all_unique_skills))
    if not unique_skills_list: unique_skills_list = ["No skills extracted from current JDs"]

    all_jd_data = st.session_state.candidate_jd_list
    # --- End Extraction ---

    # --- Start Filter Form ---
    with st.form(key="jd_filter_form"):
        st.markdown("### Select Filters")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            selected_skills = st.multiselect(
                "Skills Keywords (Select multiple)",
                options=unique_skills_list,
                default=st.session_state.get('last_selected_skills', []),
                key="candidate_filter_skills_multiselect", 
                help="Select one or more skills. JDs containing ANY of the selected skills will be shown."
            )
            
        with col2:
            selected_job_type = st.selectbox(
                "Job Type",
                options=["All Job Types"] + unique_job_types,
                index=0, key="filter_job_type_select"
            )
            
        with col3:
            selected_role = st.selectbox(
                "Role Title",
                options=["All Roles"] + unique_roles,
                index=0, key="filter_role_select"
            )

        apply_filters_button = st.form_submit_button("✅ Apply Filters", type="primary", use_container_width=True)

    # --- Start Filtering Logic ---
    if apply_filters_button:
        
        st.session_state.last_selected_skills = selected_skills

        filtered_jds = []
        selected_skills_lower = [k.strip().lower() for k in selected_skills]
        
        for jd in all_jd_data:
            jd_role = jd.get('role', 'General Analyst')
            jd_job_type = jd.get('job_type', 'Full-time')
            jd_key_skills = [s.lower() for s in jd.get('key_skills', []) if isinstance(s, str) and s.strip()]
            
            role_match = (selected_role == "All Roles") or (selected_role == jd_role)
            job_type_match = (selected_job_type == "All Job Types") or (selected_job_type == jd_job_type)
            
            skill_match = True
            if selected_skills_lower:
                if not any(k in jd_key_skills for k in selected_skills_lower):
                    skill_match = False
            
            if role_match and job_type_match and skill_match:
                filtered_jds.append(jd)
                
        st.session_state.filtered_jds_display = filtered_jds
        st.success(f"Filter applied! Found {len(filtered_jds)} matching Job Descriptions.")

    # --- Display Results ---
    st.markdown("---")
    
    if 'filtered_jds_display' not in st.session_state: st.session_state.filtered_jds_display = []
        
    filtered_jds = st.session_state.filtered_jds_display
    
    st.subheader(f"Matching Job Descriptions ({len(filtered_jds)} found)")
    
    if filtered_jds:
        display_data = []
        for jd in filtered_jds:
            display_data.append({
                "Job Description Title": jd['name'].replace("--- Simulated JD for: ", ""),
                "Role": jd.get('role', 'N/A'),
                "Job Type": jd.get('job_type', 'N/A'),
                "Key Skills": ", ".join(jd.get('key_skills', ['N/A'])[:5]) + "...",
            })
            
        st.dataframe(display_data, use_container_width=True)

        st.markdown("##### Detailed View")
        for idx, jd in enumerate(filtered_jds, 1):
            with st.expander(f"JD {idx}: {jd['name'].replace('--- Simulated JD for: ', '')} - ({jd.get('role', 'N/A')})"):
                st.markdown(f"**Job Type:** {jd.get('job_type', 'N/A')}")
                st.markdown(f"**Extracted Skills:** {', '.join(jd.get('key_skills', ['N/A']))}")
                st.markdown("---")
                st.text(jd['content'])
    elif st.session_state.get('candidate_jd_list') and apply_filters_button:
        st.info("No Job Descriptions match the selected criteria. Try broadening your filter selections.")
    elif st.session_state.get('candidate_jd_list') and not apply_filters_button:
        st.info("Use the filters above and click **'Apply Filters'** to view matching Job Descriptions.")


# --- Sub-Tab Content Functions ---

def resume_chatbot_content(is_resume_parsed):
    st.header("💬 Resume Chatbot (Q&A)")
    st.markdown("### Ask any question about the currently loaded resume.")
    if not is_resume_parsed:
        st.warning("Please upload and parse a resume in the 'Resume Parsing' tab first.")
    elif "error" in st.session_state.get('parsed', {}):
         st.error("Cannot use Resume Chatbot: Resume data has parsing errors.")
    else:
        if 'qa_answer' not in st.session_state: st.session_state.qa_answer = ""
        
        question = st.text_input("Your Question", placeholder="e.g., What are the candidate's key skills?", key="resume_qa_question")
        
        if st.button("Get Answer", key="resume_qa_btn"):
            with st.spinner("Generating answer..."):
                try:
                    answer = qa_on_resume(question)
                    st.session_state.qa_answer = answer
                except NameError:
                    st.error("Function 'qa_on_resume' not imported from 'app.py'. Check your setup.")
                    st.session_state.qa_answer = "Could not generate an answer (Function Missing)."
                except Exception as e:
                    st.error(f"Error during Q&A: {e}")
                    st.session_state.qa_answer = "Could not generate an answer."

        if st.session_state.get('qa_answer'):
            st.text_area("Answer", st.session_state.qa_answer, height=150, key="resume_qa_answer_display")

def jd_chatbot_content():
    st.header("🏢 JD Chatbot (Q&A)")
    st.markdown("### Ask questions about any saved Job Description.")
    
    if not st.session_state.get('candidate_jd_list'):
        st.error("No Job Descriptions are currently loaded. Please add JDs in the 'JD Management' tab (Tab 4).")
        return

    # 1. Select JD
    jd_options = {item['name']: item['content'] for item in st.session_state.candidate_jd_list}
    selected_jd_name = st.selectbox(
        "Select Job Description to Query", 
        list(jd_options.keys()), 
        key="jd_chatbot_select"
    )
    selected_jd_content = jd_options.get(selected_jd_name, "")
    
    if not selected_jd_content:
        st.warning("Selected JD content is empty or could not be loaded.")
        return
        
    st.markdown("---")
    st.markdown("### 2. Ask Your Question")

    # Initialize JD Chatbot state
    if 'jd_qa_answer' not in st.session_state: st.session_state.jd_qa_answer = ""

    question = st.text_input("Your Question", placeholder="e.g., What are the minimum years of experience required?", key="jd_qa_question")
    
    if st.button("Get JD Answer", key="jd_qa_btn"):
        if not question.strip():
            st.error("Please enter a question.")
            return

        with st.spinner(f"Generating answer about {selected_jd_name}..."):
            try:
                answer = jd_qa_on_jd(question, selected_jd_content)
                st.session_state.jd_qa_answer = answer
            except Exception as e:
                st.error(f"Error during JD Q&A: {e}")
                st.session_state.jd_qa_answer = "Could not generate an answer due to an error."

    if st.session_state.get('jd_qa_answer'):
        st.text_area("Answer", st.session_state.jd_qa_answer, height=150, key="jd_qa_answer_display")


# --- MAIN CANDIDATE DASHBOARD FUNCTION ---

def candidate_dashboard():
    # Initialize necessary session state variables if they don't exist
    if 'parsed' not in st.session_state: st.session_state.parsed = {}
    if 'full_text' not in st.session_state: st.session_state.full_text = ""
    if 'candidate_jd_list' not in st.session_state: st.session_state.candidate_jd_list = []
    if 'candidate_match_results' not in st.session_state: st.session_state.candidate_match_results = []
    if 'filtered_jds_display' not in st.session_state: st.session_state.filtered_jds_display = []
    if 'candidate_uploaded_resumes' not in st.session_state: st.session_state.candidate_uploaded_resumes = []
    if 'pasted_cv_text' not in st.session_state: st.session_state.pasted_cv_text = ""


    st.header("👩‍🎓 Candidate Dashboard")
    st.markdown("Welcome! Use the tabs below to manage your CV and access AI preparation tools.")

    nav_col, _ = st.columns([1, 1]) 
    with nav_col:
        if st.button("🚪 Log Out", key="candidate_logout_btn", use_container_width=True):
            go_to("login") 
    
    # Sidebar for Status Only
    with st.sidebar:
        st.header("Resume/CV Status")
        is_parsed_ok = st.session_state.parsed.get("name") and "error" not in st.session_state.parsed
        if is_parsed_ok:
            st.success(f"Currently loaded: **{st.session_state.parsed['name']}**")
        elif st.session_state.full_text:
            st.warning("Resume content is loaded, but parsing may have errors.")
        else:
            st.info("Please upload a file or use the CV builder in 'CV Management' to begin.")

    # Main Content Tabs
    tab_cv_mgmt, tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "✍️ CV Management", 
        "📄 Resume Parsing", 
        "💬 AI Chatbots", 
        "❓ Interview Prep", 
        "📚 JD Management", 
        "🎯 Batch JD Match",
        "🔍 Filter JD"
    ])
    
    is_resume_parsed = bool(st.session_state.get('parsed', {}).get('name')) or bool(st.session_state.get('full_text'))
    
    # --- TAB 0: CV Management ---
    with tab_cv_mgmt:
        cv_management_tab_content()

    # --- TAB 1: Resume Parsing ---
    with tab1:
        st.header("Resume Upload and Parsing")
        
        input_method = st.radio("Select Input Method", ["Upload File", "Paste Text"], key="parsing_input_method")
        st.markdown("---")

        if input_method == "Upload File":
            st.markdown("### 1. Upload Resume File") 
            uploaded_file = st.file_uploader( 
                "Choose PDF, DOCX, TXT, JSON, MD, CSV, XLSX file", 
                type=["pdf", "docx", "txt", "json", "md", "csv", "xlsx", "markdown", "rtf"], 
                accept_multiple_files=False, key='candidate_file_upload_main'
            )
            
            # Handle uploaded file change logic
            if uploaded_file is not None:
                st.session_state.candidate_uploaded_resumes = [uploaded_file] 
                st.session_state.pasted_cv_text = ""
            elif st.session_state.candidate_uploaded_resumes and uploaded_file is None:
                # File was previously uploaded but removed
                st.session_state.candidate_uploaded_resumes = []
                # Don't clear parsed data immediately unless user clicks parse
            
            file_to_parse = st.session_state.candidate_uploaded_resumes[0] if st.session_state.candidate_uploaded_resumes else None
            
            st.markdown("### 2. Parse Uploaded File")
            
            if file_to_parse:
                if st.button(f"Parse and Load: **{file_to_parse.name}**", use_container_width=True):
                    with st.spinner(f"Parsing {file_to_parse.name}..."):
                        try:
                            result = parse_and_store_resume(file_to_parse, file_name_key='single_resume_candidate', source_type='file')
                            
                            if "error" not in result:
                                st.session_state.parsed = result.get('parsed', {})
                                st.session_state.full_text = result.get('full_text', "")
                                st.session_state.excel_data = result.get('excel_data', None) 
                                st.session_state.parsed['name'] = result.get('name', file_to_parse.name)
                                clear_interview_state()
                                st.success(f"✅ Successfully loaded and parsed **{st.session_state.parsed['name']}**.")
                            else:
                                st.error(f"Parsing failed for {file_to_parse.name}: {result['error']}")
                                st.session_state.parsed = {"error": result['error'], "name": result.get('name', file_to_parse.name)}
                                st.session_state.full_text = result.get('full_text', "")
                        except NameError:
                            st.error("Function 'parse_and_store_resume' not imported from 'app.py'. Check your setup.")
                        except Exception as e:
                            st.error(f"An unexpected error occurred during parsing: {e}")
            else:
                st.info("No resume file is currently uploaded. Please upload a file above.")

        elif input_method == "Paste Text":
            st.markdown("### 1. Paste Your CV Text")
            
            pasted_text = st.text_area(
                "Copy and paste your entire CV or resume text here.",
                value=st.session_state.get('pasted_cv_text', ''),
                height=300, key='pasted_cv_text_input'
            )
            st.session_state.pasted_cv_text = pasted_text
            
            st.markdown("---")
            st.markdown("### 2. Parse Pasted Text")
            
            if pasted_text.strip():
                if st.button("Parse and Load Pasted Text", use_container_width=True):
                    with st.spinner("Parsing pasted text..."):
                        st.session_state.candidate_uploaded_resumes = []
                        
                        try:
                            result = parse_and_store_resume(pasted_text, file_name_key='single_resume_candidate', source_type='text')
                            
                            if "error" not in result:
                                st.session_state.parsed = result.get('parsed', {})
                                st.session_state.full_text = result.get('full_text', "")
                                st.session_state.excel_data = result.get('excel_data', None) 
                                st.session_state.parsed['name'] = result.get('name', 'Pasted CV')
                                clear_interview_state()
                                st.success(f"✅ Successfully loaded and parsed **{st.session_state.parsed['name']}**.")
                            else:
                                st.error(f"Parsing failed: {result['error']}")
                                st.session_state.parsed = {"error": result['error'], "name": result.get('name', 'Pasted CV')}
                                st.session_state.full_text = result.get('full_text', "")
                        except NameError:
                            st.error("Function 'parse_and_store_resume' not imported from 'app.py'. Check your setup.")
                        except Exception as e:
                            st.error(f"An unexpected error occurred during parsing: {e}")
            else:
                st.info("Please paste your CV text into the box above.")


    # --- TAB 2: AI Chatbots (New Sub-Tabs) ---
    with tab2:
        st.title("🤖 AI Chatbots")
        
        # New sub-tabs for Chatbots
        sub_tab_resume, sub_tab_jd = st.tabs(["📄 Resume Chatbot (Q&A)", "🏢 JD Chatbot (Q&A)"])
        
        with sub_tab_resume:
            resume_chatbot_content(is_resume_parsed)

        with sub_tab_jd:
            jd_chatbot_content()


    # --- TAB 3: Interview Prep ---
    with tab3:
        st.header("Interview Preparation Tools")
        if not is_resume_parsed or "error" in st.session_state.get('parsed', {}):
            st.warning("Please upload and successfully parse a resume first.")
        else:
            if 'iq_output' not in st.session_state: st.session_state.iq_output = ""
            if 'interview_qa' not in st.session_state: st.session_state.interview_qa = [] 
            if 'evaluation_report' not in st.session_state: st.session_state.evaluation_report = "" 
            
            st.subheader("1. Generate Interview Questions")
            
            question_section_options = ["skills","experience", "certifications", "projects", "education"]
            section_choice = st.selectbox(
                "Select Section", 
                question_section_options, 
                key='iq_section_c',
                on_change=clear_interview_state 
            )
            
            if st.button("Generate Interview Questions", key='iq_btn_c'):
                with st.spinner("Generating questions..."):
                    try:
                        raw_questions_response = generate_interview_questions(st.session_state.parsed, section_choice)
                        st.session_state.iq_output = raw_questions_response
                        
                        st.session_state.interview_qa = [] 
                        st.session_state.evaluation_report = "" 
                        
                        # Simple parsing of question response
                        q_list = []
                        current_level = ""
                        for line in raw_questions_response.splitlines():
                            line = line.strip()
                            if line.startswith('[') and line.endswith(']'):
                                current_level = line.strip('[]')
                            elif line.lower().startswith('q') and ':' in line:
                                question_text = line[line.find(':') + 1:].strip()
                                q_list.append({
                                    "question": f"({current_level}) {question_text}",
                                    "answer": "", "level": current_level
                                })
                                
                        st.session_state.interview_qa = q_list
                        st.success(f"Generated {len(q_list)} questions based on your **{section_choice}** section.")
                        
                    except NameError:
                        st.error("Function 'generate_interview_questions' not imported from 'app.py'. Check your setup.")
                        st.session_state.iq_output = "Error generating questions (Function Missing)."
                        st.session_state.interview_qa = []
                    except Exception as e:
                        st.error(f"Error generating questions: {e}")
                        st.session_state.iq_output = "Error generating questions."
                        st.session_state.interview_qa = []

            if st.session_state.get('interview_qa'):
                st.markdown("---")
                st.subheader("2. Practice and Record Answers")
                
                with st.form("interview_practice_form"):
                    
                    for i, qa_item in enumerate(st.session_state.interview_qa):
                        st.markdown(f"**Question {i+1}:** {qa_item['question']}")
                        answer = st.text_area(f"Your Answer for Q{i+1}", value=st.session_state.interview_qa[i]['answer'], height=100, key=f'answer_q_{i}', label_visibility='collapsed')
                        st.session_state.interview_qa[i]['answer'] = answer 
                        st.markdown("---") 
                        
                    submit_button = st.form_submit_button("Submit & Evaluate Answers", use_container_width=True)

                    if submit_button:
                        
                        if all(item['answer'].strip() for item in st.session_state.interview_qa):
                            with st.spinner("Sending answers to AI Evaluator..."):
                                try:
                                    report = evaluate_interview_answers(st.session_state.interview_qa, st.session_state.parsed)
                                    st.session_state.evaluation_report = report
                                    st.success("Evaluation complete! See the report below.")
                                except NameError:
                                    st.error("Function 'evaluate_interview_answers' not imported from 'app.py'. Check your setup.")
                                    st.session_state.evaluation_report = "Evaluation failed (Function Missing)."
                                except Exception as e:
                                    st.error(f"Evaluation failed: {e}")
                                    st.session_state.evaluation_report = f"Evaluation failed: {e}\n{traceback.format_exc()}"
                        else:
                            st.error("Please answer all generated questions before submitting.")
                
                if st.session_state.get('evaluation_report'):
                    st.markdown("---")
                    st.subheader("3. AI Evaluation Report")
                    st.markdown(st.session_state.evaluation_report)

    # --- TAB 4: JD Management (Candidate) ---
    with tab4:
        st.header("📚 Manage Job Descriptions for Matching")
        
        jd_type = st.radio("Select JD Type", ["Single JD", "Multiple JD"], key="jd_type_candidate")
        st.markdown("### Add JD by:")
        
        method = st.radio("Choose Method", ["Upload File", "Paste Text", "LinkedIn URL"], key="jd_add_method_candidate") 

        # URL
        if method == "LinkedIn URL":
            url_list = st.text_area("Enter one or more URLs (comma separated)" if jd_type == "Multiple JD" else "Enter URL", key="url_list_candidate")
            if st.button("Add JD(s) from URL", key="add_jd_url_btn_candidate"):
                if url_list:
                    urls = [u.strip() for u in url_list.split(",")] if jd_type == "Multiple JD" else [url_list.strip()]
                    count = 0
                    for url in urls:
                        if not url: continue
                        with st.spinner(f"Attempting JD extraction and metadata analysis for: {url}"):
                            try:
                                jd_text = extract_jd_from_linkedin_url(url)
                                metadata = extract_jd_metadata(jd_text)
                            except NameError:
                                st.error("JD extraction functions not imported from 'app.py'. Check your setup.")
                                break

                        
                        name_base = url.split('/jobs/view/')[-1].split('/')[0] if '/jobs/view/' in url else f"URL {count+1}"
                        name = f"JD from URL: {name_base}" 
                        if name in [item['name'] for item in st.session_state.candidate_jd_list]:
                            name = f"JD from URL: {name_base} ({len(st.session_state.candidate_jd_list) + 1})" 

                        st.session_state.candidate_jd_list.append({"name": name, "content": jd_text, **metadata})
                        if not jd_text.startswith("[Error"): count += 1
                                
                    if count > 0: st.success(f"✅ {count} JD(s) added successfully!")
                    elif urls: st.error("No JDs were added successfully. Check if the URL is valid and the extraction function is working.")

        # Paste Text
        elif method == "Paste Text":
            text_list = st.text_area("Paste one or more JD texts (separate by '---')" if jd_type == "Multiple JD" else "Paste JD text here", key="text_list_candidate")
            if st.button("Add JD(s) from Text", key="add_jd_text_btn_candidate"):
                if text_list:
                    texts = [t.strip() for t in text_list.split("---")] if jd_type == "Multiple JD" else [text_list.strip()]
                    try:
                        for i, text in enumerate(texts):
                             if text:
                                name_base = text.splitlines()[0].strip()
                                if len(name_base) > 30: name_base = f"{name_base[:27]}..."
                                if not name_base: name_base = f"Pasted JD {len(st.session_state.candidate_jd_list) + i + 1}"
                                metadata = extract_jd_metadata(text)
                                st.session_state.candidate_jd_list.append({"name": name_base, "content": text, **metadata})
                        st.success(f"✅ {len(texts)} JD(s) added successfully!")
                    except NameError:
                        st.error("Function 'extract_jd_metadata' not imported from 'app.py'. Check your setup.")

        # Upload File
        elif method == "Upload File":
            uploaded_files = st.file_uploader("Upload JD file(s)", type=["pdf", "txt", "docx"], accept_multiple_files=(jd_type == "Multiple JD"), key="jd_file_uploader_candidate")
            if st.button("Add JD(s) from File", key="add_jd_file_btn_candidate"):
                if uploaded_files is None: st.warning("Please upload file(s).")
                files_to_process = uploaded_files if isinstance(uploaded_files, list) else ([uploaded_files] if uploaded_files else [])
                count = 0
                for file in files_to_process:
                    if file:
                        try:
                            result = parse_and_store_resume(file, file_name_key='candidate_jd_temp', source_type='file')
                            jd_text = result.get('full_text', "")
                            if not jd_text.startswith("Error"):
                                metadata = extract_jd_metadata(jd_text)
                                st.session_state.candidate_jd_list.append({"name": file.name, "content": jd_text, **metadata})
                                count += 1
                            else: st.error(f"Error extracting content from {file.name}: {jd_text}")
                        except NameError:
                            st.error("Parsing/Metadata functions not imported from 'app.py'. Check your setup.")
                            break
                            
                if count > 0: st.success(f"✅ {count} JD(s) added successfully!")
                elif uploaded_files: st.error("No valid JD files were uploaded or content extraction failed.")


        # Display Added JDs
        if st.session_state.candidate_jd_list:
            col_display_header, col_clear_button = st.columns([3, 1])
            with col_display_header: st.markdown("### ✅ Current JDs Added:")
            with col_clear_button:
                if st.button("🗑️ Clear All JDs", key="clear_jds_candidate", use_container_width=True, help="Removes all currently loaded JDs."):
                    st.session_state.candidate_jd_list = []
                    st.session_state.candidate_match_results = []
                    st.session_state.filtered_jds_display = [] 
                    st.rerun() 

            for idx, jd_item in enumerate(st.session_state.candidate_jd_list, 1):
                title = jd_item['name']
                display_title = title.replace("--- Simulated JD for: ", "")
                with st.expander(f"JD {idx}: {display_title} | Role: {jd_item.get('role', 'N/A')}"):
                    st.markdown(f"**Job Type:** {jd_item.get('job_type', 'N/A')} | **Key Skills:** {', '.join(jd_item.get('key_skills', ['N/A']))}")
                    st.markdown("---")
                    st.text(jd_item['content'])
        else: st.info("No Job Descriptions added yet.")

    # --- TAB 5: Batch JD Match (Candidate) ---
    with tab5:
        st.header("🎯 Batch JD Match: Best Matches")
        st.markdown("Compare your current resume against all saved job descriptions.")

        if not is_resume_parsed:
            st.warning("Please **upload and parse your resume** or **build your CV** first.")
        elif not st.session_state.candidate_jd_list:
            st.error("Please **add Job Descriptions** in the 'JD Management' tab before running batch analysis.")
        else:

            all_jd_names = [item['name'] for item in st.session_state.candidate_jd_list]
            selected_jd_names = st.multiselect("Select Job Descriptions to Match Against", options=all_jd_names, default=all_jd_names, key='candidate_batch_jd_select')
            jds_to_match = [jd_item for jd_item in st.session_state.candidate_jd_list if jd_item['name'] in selected_jd_names]
            
            if st.button(f"Run Match Analysis on {len(jds_to_match)} Selected JD(s)"):
                st.session_state.candidate_match_results = []
                if not jds_to_match:
                    st.warning("Please select at least one Job Description to run the analysis.")
                else:
                    resume_name = st.session_state.parsed.get('name', 'Uploaded Resume')
                    parsed_json = st.session_state.parsed
                    results_with_score = []

                    with st.spinner(f"Matching {resume_name}'s resume against {len(jds_to_match)} selected JD(s)..."):
                        for jd_item in jds_to_match:
                            jd_name = jd_item['name']
                            jd_content = jd_item['content']
                            try:
                                fit_output = evaluate_jd_fit(jd_content, parsed_json)
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
                                    "jd_name": jd_name, "overall_score": overall_score,
                                    "numeric_score": int(overall_score) if overall_score.isdigit() else -1,
                                    "skills_percent": skills_percent, "experience_percent": experience_percent, 
                                    "education_percent": education_percent, "full_analysis": fit_output
                                })
                            except NameError:
                                st.error("Function 'evaluate_jd_fit' not imported from 'app.py'. Check your setup.")
                                results_with_score.append({"jd_name": jd_name, "overall_score": "Error", "numeric_score": -1, "full_analysis": f"Error running analysis (Function Missing)"})
                                break
                            except Exception as e:
                                results_with_score.append({"jd_name": jd_name, "overall_score": "Error", "numeric_score": -1, "full_analysis": f"Error running analysis: {e}\n{traceback.format_exc()}"})
                                
                        results_with_score.sort(key=lambda x: x['numeric_score'], reverse=True)
                        current_rank = 1
                        current_score = -1 
                        for i, item in enumerate(results_with_score):
                            if item['numeric_score'] > current_score:
                                current_rank = i + 1
                                current_score = item['numeric_score']
                            item['rank'] = current_rank
                            del item['numeric_score']
                            
                        st.session_state.candidate_match_results = results_with_score
                        st.success("Batch analysis complete!")

            if st.session_state.get('candidate_match_results'):
                st.markdown("#### Match Results for Your Resume")
                results_df = st.session_state.candidate_match_results
                
                display_data = []
                for item in results_df:
                    full_jd_item = next((jd for jd in st.session_state.candidate_jd_list if jd['name'] == item['jd_name']), {})
                    display_data.append({
                        "Rank": item.get("rank", "N/A"),
                        "Job Description (Ranked)": item["jd_name"].replace("--- Simulated JD for: ", ""),
                        "Role": full_jd_item.get('role', 'N/A'),
                        "Job Type": full_jd_item.get('job_type', 'N/A'),
                        "Fit Score (out of 10)": item["overall_score"],
                        "Skills (%)": item.get("skills_percent", "N/A"),
                        "Experience (%)": item.get("experience_percent", "N/A"), 
                        "Education (%)": item.get("education_percent", "N/A"),   
                    })

                st.dataframe(display_data, use_container_width=True)

                st.markdown("##### Detailed Reports")
                for item in results_df:
                    rank_display = f"Rank {item.get('rank', 'N/A')} | "
                    header_text = f"{rank_display}Report for **{item['jd_name'].replace('--- Simulated JD for: ', '')}** (Score: **{item['overall_score']}/10** | S: **{item.get('skills_percent', 'N/A')}%** | E: **{item.get('experience_percent', 'N/A')}%** | Edu: **{item.get('education_percent', 'N/A')}%**)"
                    with st.expander(header_text):
                        st.markdown(item['full_analysis'])

    # --- TAB 6: Filter JD ---
    with tab6:
        filter_jd_tab_content()
