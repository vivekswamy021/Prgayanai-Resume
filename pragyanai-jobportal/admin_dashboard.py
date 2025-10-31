# admin_dashboard.py

import streamlit as st
from utils import go_to, extract_content, get_file_type, parse_and_store_resume, evaluate_jd_fit, extract_jd_from_linkedin_url
import tempfile
import os
import re
from datetime import date
import traceback
import json

# Helper function specific to Admin Dashboard
def update_resume_status(resume_name, new_status, applied_jd, submitted_date, resume_list_index):
    """
    Callback function to update the status and metadata of a specific resume.
    """
    st.session_state.resume_statuses[resume_name] = new_status
    
    if 0 <= resume_list_index < len(st.session_state.resumes_to_analyze):
        st.session_state.resumes_to_analyze[resume_list_index]['applied_jd'] = applied_jd
        st.session_state.resumes_to_analyze[resume_list_index]['submitted_date'] = submitted_date
        st.success(f"Status and metadata for **{resume_name}** updated to **{new_status}**.")
    else:
        st.error(f"Error: Could not find resume index {resume_list_index} for update.")
        
# --- NEWLY ISOLATED FUNCTIONS FOR APPROVAL TABS ---

def candidate_approval_tab_content():
    st.header("👤 Candidate Approval")
    st.markdown("### Resume Status List")
    
    if "resumes_to_analyze" not in st.session_state or not st.session_state.resumes_to_analyze:
        st.info("No resumes have been uploaded and parsed in the 'Resume Analysis' tab yet.")
        return
        
    jd_options = [item['name'].replace("--- Simulated JD for: ", "") for item in st.session_state.admin_jd_list]
    jd_options.insert(0, "Select JD") 

    for idx, resume_data in enumerate(st.session_state.resumes_to_analyze):
        resume_name = resume_data['name']
        current_status = st.session_state.resume_statuses.get(resume_name, "Pending")
        
        current_applied_jd = resume_data.get('applied_jd', 'N/A (Pending Assignment)')
        current_submitted_date = resume_data.get('submitted_date', date.today().strftime("%Y-%m-%d"))

        with st.container(border=True):
            st.markdown(f"**Resume:** **{resume_name}**")
            
            col_jd_input, col_date_input = st.columns(2)
            
            with col_jd_input:
                try:
                    default_value = current_applied_jd if current_applied_jd != "N/A (Pending Assignment)" else "Select JD"
                    jd_default_index = jd_options.index(default_value)
                except ValueError:
                    jd_default_index = 0
                    
                new_applied_jd = st.selectbox(
                    "Applied for JD Title", 
                    options=jd_options,
                    index=jd_default_index,
                    key=f"jd_select_{resume_name}_{idx}",
                )
                
            with col_date_input:
                try:
                    date_obj = date.fromisoformat(current_submitted_date)
                except (ValueError, TypeError):
                    date_obj = date.today()
                    
                new_submitted_date = st.date_input(
                    "Submitted Date", 
                    value=date_obj,
                    key=f"date_input_{resume_name}_{idx}"
                )
                
            st.markdown(f"**Current Status:** **{current_status}**")
            
            st.markdown("---")
            
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.markdown("Set Status:")
                new_status = st.selectbox(
                    "Set Status",
                    ["Pending", "Approved", "Rejected", "Shortlisted"],
                    index=["Pending", "Approved", "Rejected", "Shortlisted"].index(current_status),
                    key=f"status_select_{resume_name}_{idx}",
                    label_visibility="collapsed"
                )

            with col2:
                if st.button("Update", key=f"update_btn_{resume_name}_{idx}"):
                    
                    if new_applied_jd == "Select JD" and len(jd_options) > 1:
                        jd_to_save = "N/A (Pending Assignment)"
                    else:
                        jd_to_save = new_applied_jd
                        
                    update_resume_status(
                        resume_name, 
                        new_status, 
                        jd_to_save, 
                        new_submitted_date.strftime("%Y-%m-%d"),
                        idx
                    )
                    st.rerun() 
            
    st.markdown("---")
            
    summary_data = []
    for resume_data in st.session_state.resumes_to_analyze:
        name = resume_data['name']
        summary_data.append({
            "Resume": name, 
            "Applied JD": resume_data.get('applied_jd', 'N/A'),
            "Submitted Date": resume_data.get('submitted_date', 'N/A'),
            "Status": st.session_state.resume_statuses.get(name, "Pending")
        })
        
    st.subheader("Summary of All Resumes")
    st.dataframe(summary_data, use_container_width=True)


def vendor_approval_tab_content():
    st.header("🤝 Vendor Approval") 
    
    st.markdown("### 1. Add New Vendor")
    if "vendors" not in st.session_state:
        st.session_state.vendors = []
    if "vendor_statuses" not in st.session_state:
        st.session_state.vendor_statuses = {}
        
    with st.form("add_vendor_form"):
        col1, col2 = st.columns(2)
        with col1:
            vendor_name = st.text_input("Vendor Name", key="new_vendor_name")
        with col2:
            vendor_domain = st.text_input("Service / Domain Name", key="new_vendor_domain")
            
        col3, col4 = st.columns(2)
        with col3:
            submitted_date = st.date_input("Submitted Date", value=date.today(), key="new_vendor_date")
        with col4:
            initial_status = st.selectbox(
                "Set Status", 
                ["Pending Review", "Approved", "Rejected"],
                key="new_vendor_status"
            )
        
        add_vendor_button = st.form_submit_button("Add Vendor", use_container_width=True)

        if add_vendor_button:
            if vendor_name and vendor_domain:
                vendor_id = vendor_name.strip() 
                
                if vendor_id in st.session_state.vendor_statuses:
                    st.warning(f"Vendor '{vendor_name}' already exists.")
                else:
                    new_vendor = {
                        'name': vendor_name.strip(),
                        'domain': vendor_domain.strip(),
                        'submitted_date': submitted_date.strftime("%Y-%m-%d")
                    }
                    st.session_state.vendors.append(new_vendor)
                    st.session_state.vendor_statuses[vendor_id] = initial_status
                    st.success(f"Vendor **{vendor_name}** added successfully with status **{initial_status}**.")
                    st.rerun() 
            else:
                st.error("Please fill in both Vendor Name and Service / Domain Name.")

    st.markdown("---")
    
    st.markdown("### 2. Update Existing Vendor Status")
    
    if not st.session_state.vendors:
        st.info("No vendors have been added yet.")
    else:
        for idx, vendor in enumerate(st.session_state.vendors):
            vendor_name = vendor['name']
            vendor_id = vendor_name 
            current_status = st.session_state.vendor_statuses.get(vendor_id, "Unknown")
            
            with st.container(border=True):
                
                col_info, col_status_input, col_update_btn = st.columns([3, 2, 1])
                
                with col_info:
                    st.markdown(f"**Vendor:** {vendor_name} (`{vendor['domain']}`) - *Submitted: {vendor['submitted_date']}*")
                    st.markdown(f"**Current Status:** **{current_status}**")
                    
                with col_status_input:
                    new_status = st.selectbox(
                        "Set Status",
                        ["Pending Review", "Approved", "Rejected"],
                        index=["Pending Review", "Approved", "Rejected"].index(current_status),
                        key=f"vendor_status_select_{idx}",
                        label_visibility="collapsed"
                    )

                with col_update_btn:
                    st.markdown("##") 
                    if st.button("Update", key=f"vendor_update_btn_{idx}", use_container_width=True):
                        
                        st.session_state.vendor_statuses[vendor_id] = new_status
                        
                        st.success(f"Status for **{vendor_name}** updated to **{new_status}**.")
                        st.rerun()
                        
        st.markdown("---")
        
        summary_data = []
        for vendor in st.session_state.vendors:
            name = vendor['name']
            summary_data.append({
                "Vendor Name": name,
                "Domain": vendor['domain'],
                "Submitted Date": vendor['submitted_date'],
                "Status": st.session_state.vendor_statuses.get(name, "Unknown")
            })
        
        st.subheader("Summary of All Vendors")
        st.dataframe(summary_data, use_container_width=True)


def admin_dashboard():
    st.header("🧑‍💼 Admin Dashboard")
    
    # --- NAVIGATION BLOCK (MODIFIED) ---
    nav_col, _ = st.columns([1, 1]) 

    with nav_col:
        if st.button("🚪 Log Out", use_container_width=True):
            go_to("login") 
    # --- END NAVIGATION BLOCK ---
    
    # Initialize Admin session state variables (Defensive check)
    if "admin_jd_list" not in st.session_state: st.session_state.admin_jd_list = []
    if "resumes_to_analyze" not in st.session_state: st.session_state.resumes_to_analyze = []
    if "admin_match_results" not in st.session_state: st.session_state.admin_match_results = []
    if "resume_statuses" not in st.session_state: st.session_state.resume_statuses = {}
    if "vendors" not in st.session_state: st.session_state.vendors = []
    if "vendor_statuses" not in st.session_state: st.session_state.vendor_statuses = {}
        
    
    # --- TAB ORDER ---
    tab_jd, tab_analysis, tab_user_mgmt, tab_statistics = st.tabs([
        "📄 JD Management", 
        "📊 Resume Analysis", 
        "🛠️ User Management", 
        "📈 Statistics" 
    ])
    # -------------------------

    # --- TAB 1: JD Management ---
    with tab_jd:
        st.subheader("Add and Manage Job Descriptions (JD)")
        
        jd_type = st.radio("Select JD Type", ["Single JD", "Multiple JD"], key="jd_type_admin")
        st.markdown("### Add JD by:")
        
        method = st.radio("Choose Method", ["Upload File", "Paste Text", "LinkedIn URL"], key="jd_add_method_admin") 

        # URL
        if method == "LinkedIn URL":
            url_list = st.text_area(
                "Enter one or more URLs (comma separated)" if jd_type == "Multiple JD" else "Enter URL", key="url_list_admin"
            )
            if st.button("Add JD(s) from URL", key="add_jd_url_btn_admin"):
                if url_list:
                    urls = [u.strip() for u in url_list.split(",")] if jd_type == "Multiple JD" else [url_list.strip()]
                    
                    count = 0
                    for url in urls:
                        if not url: continue
                        
                        with st.spinner(f"Attempting JD extraction for: {url}"):
                            jd_text = extract_jd_from_linkedin_url(url)
                        
                        name_base = url.split('/jobs/view/')[-1].split('/')[0] if '/jobs/view/' in url else f"URL {count+1}"
                        st.session_state.admin_jd_list.append({"name": f"JD from URL: {name_base}", "content": jd_text})
                        if not jd_text.startswith("[Error"):
                            count += 1
                            
                    if count > 0:
                        st.success(f"✅ {count} JD(s) added successfully! Check the display below for the extracted content.")
                    else:
                        st.error("No JDs were added successfully.")


        # Paste Text
        elif method == "Paste Text":
            text_list = st.text_area(
                "Paste one or more JD texts (separate by '---')" if jd_type == "Multiple JD" else "Paste JD text here", key="text_list_admin"
            )
            if st.button("Add JD(s) from Text", key="add_jd_text_btn_admin"):
                if text_list:
                    texts = [t.strip() for t in text_list.split("---")] if jd_type == "Multiple JD" else [text_list.strip()]
                    for i, text in enumerate(texts):
                         if text:
                            name_base = text.splitlines()[0].strip()
                            if len(name_base) > 30: name_base = f"{name_base[:27]}..."
                            if not name_base: name_base = f"Pasted JD {len(st.session_state.admin_jd_list) + i + 1}"
                            
                            st.session_state.admin_jd_list.append({"name": name_base, "content": text})
                    st.success(f"✅ {len(texts)} JD(s) added successfully!")

        # Upload File
        elif method == "Upload File":
            uploaded_files = st.file_uploader(
                "Upload JD file(s)",
                type=["pdf", "txt", "docx"],
                accept_multiple_files=(jd_type == "Multiple JD"), # Dynamically set
                key="jd_file_uploader_admin"
            )
            
            if st.button("Add JD(s) from File", key="add_jd_file_btn_admin"):
                if uploaded_files is None:
                    st.warning("Please upload file(s).")
                    
                files_to_process = uploaded_files if isinstance(uploaded_files, list) else ([uploaded_files] if uploaded_files else [])
                
                count = 0
                for file in files_to_process:
                    if file: 
                        temp_dir = tempfile.mkdtemp()
                        temp_path = os.path.join(temp_dir, file.name)
                        with open(temp_path, "wb") as f:
                            f.write(file.getbuffer())
                            
                        file_type = get_file_type(temp_path)
                        jd_text = extract_content(file_type, temp_path)
                        
                        if not jd_text.startswith("Error"):
                            st.session_state.admin_jd_list.append({"name": file.name, "content": jd_text})
                            count += 1
                        else:
                            st.error(f"Error extracting content from {file.name}: {jd_text}")
                            
                if count > 0:
                    st.success(f"✅ {count} JD(s) added successfully!")
                elif uploaded_files:
                    st.error("No valid JD files were uploaded or content extraction failed.")


        # Display Added JDs
        if st.session_state.admin_jd_list:
            
            col_display_header, col_clear_button = st.columns([3, 1])
            
            with col_display_header:
                st.markdown("### ✅ Current JDs Added:")
                
            with col_clear_button:
                if st.button("🗑️ Clear All JDs", key="clear_jds_admin", use_container_width=True, help="Removes all currently loaded JDs."):
                    st.session_state.admin_jd_list = []
                    st.session_state.admin_match_results = [] 
                    st.success("All JDs and associated match results have been cleared.")
                    st.rerun() 

            for idx, jd_item in enumerate(st.session_state.admin_jd_list, 1):
                title = jd_item['name']
                display_title = title.replace("--- Simulated JD for: ", "")
                with st.expander(f"JD {idx}: {display_title}"):
                    st.text(jd_item['content'])
        else:
            st.info("No Job Descriptions added yet.")


    # --- TAB 2: Resume Analysis --- 
    with tab_analysis:
        st.subheader("Analyze Resumes Against Job Descriptions")

        # 1. Resume Upload
        st.markdown("#### 1. Upload Resumes")
        
        resume_upload_type = st.radio("Upload Type", ["Single Resume", "Multiple Resumes"], key="resume_upload_type_admin")

        uploaded_files = st.file_uploader(
            "Choose files to analyze",
            type=["pdf", "docx", "txt", "json", "rtf"], 
            accept_multiple_files=(resume_upload_type == "Multiple Resumes"),
            key="resume_file_uploader_admin"
        )
        
        col_parse, col_clear = st.columns([3, 1])
        
        with col_parse:
            if st.button("Load and Parse Resume(s) for Analysis", key="parse_resumes_admin", use_container_width=True):
                if uploaded_files:
                    files_to_process = uploaded_files if isinstance(uploaded_files, list) else ([uploaded_files] if uploaded_files else [])
                    
                    count = 0
                    with st.spinner("Parsing resume(s)... This may take a moment."):
                        for file in files_to_process:
                            if file: 
                                result = parse_and_store_resume(file, file_name_key='admin_analysis')
                                
                                if "error" not in result:
                                    result['applied_jd'] = "N/A (Pending Assignment)"
                                    result['submitted_date'] = date.today().strftime("%Y-%m-%d")
                                    
                                    st.session_state.resumes_to_analyze.append(result)
                                    
                                    resume_id = result['name']
                                    if resume_id not in st.session_state.resume_statuses:
                                        st.session_state.resume_statuses[resume_id] = "Pending"
                                    
                                    count += 1
                                else:
                                    st.error(f"Failed to parse {file.name}: {result['error']}")

                    if count > 0:
                        st.success(f"Successfully loaded and parsed {count} resume(s) for analysis.")
                        st.rerun() 
                    elif not st.session_state.resumes_to_analyze:
                        st.warning("No resumes were successfully loaded and parsed.")
                else:
                    st.warning("Please upload one or more resume files.")
        
        with col_clear:
            if st.button("🗑️ Clear All Resumes", key="clear_resumes_admin", use_container_width=True, help="Removes all currently loaded resumes and match results."):
                st.session_state.resumes_to_analyze = []
                st.session_state.admin_match_results = []
                st.session_state.resume_statuses = {} 
                st.success("All resumes and associated match results have been cleared.")
                st.rerun() 


        st.markdown("---")

        # 2. JD Selection and Analysis
        st.markdown("#### 2. Select JD and Run Analysis")

        if not st.session_state.resumes_to_analyze:
            st.info("Upload and parse resumes first to enable analysis.")
            if not st.session_state.admin_jd_list: return
        elif not st.session_state.admin_jd_list:
            st.error("Please add at least one Job Description in the 'JD Management' tab before running an analysis.")
            return

        resume_names = [r['name'] for r in st.session_state.resumes_to_analyze]
        selected_resume_names = st.multiselect(
            "Select Resume(s) for Matching",
            options=resume_names,
            default=resume_names, 
            key="select_resumes_admin"
        )
        
        resumes_to_match = [
            r for r in st.session_state.resumes_to_analyze 
            if r['name'] in selected_resume_names
        ]

        jd_options = {item['name']: item['content'] for item in st.session_state.admin_jd_list}
        selected_jd_name = st.selectbox("Select JD for Matching", list(jd_options.keys()), key="select_jd_admin")
        selected_jd_content = jd_options.get(selected_jd_name, "")


        if st.button(f"Run Match Analysis on {len(resumes_to_match)} Selected Resume(s)", key="run_match_analysis_admin"):
            st.session_state.admin_match_results = []
            
            if not selected_jd_content:
                st.error("Selected JD content is empty.")
                return
            
            if not resumes_to_match:
                st.warning("No resumes were selected for matching.")
                return

            with st.spinner(f"Matching {len(resumes_to_match)} resumes against '{selected_jd_name}'..."):
                for resume_data in resumes_to_match: 
                    
                    resume_name = resume_data['name']
                    parsed_json = resume_data['parsed']

                    try:
                        fit_output = evaluate_jd_fit(selected_jd_content, parsed_json)
                        
                        overall_score_match = re.search(r'Overall Fit Score:\s*[^\d]*(\d+)\s*/10', fit_output, re.IGNORECASE)
                        section_analysis_match = re.search(
                             r'--- Section Match Analysis ---\s*(.*?)\s*Strengths/Matches:', 
                             fit_output, re.DOTALL
                        )

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

                        st.session_state.admin_match_results.append({
                            "resume_name": resume_name,
                            "jd_name": selected_jd_name,
                            "overall_score": overall_score,
                            "skills_percent": skills_percent,
                            "experience_percent": experience_percent, 
                            "education_percent": education_percent,   
                            "full_analysis": fit_output
                        })
                    except Exception as e:
                        st.session_state.admin_match_results.append({
                            "resume_name": resume_name,
                            "jd_name": selected_jd_name,
                            "overall_score": "Error",
                            "skills_percent": "Error",
                            "experience_percent": "Error", 
                            "education_percent": "Error",   
                            "full_analysis": f"Error running analysis: {e}\n{traceback.format_exc()}"
                        })
                st.success("Analysis complete!")


        # 3. Display Results
        if st.session_state.get('admin_match_results'):
            st.markdown("#### 3. Match Results")
            results_df = st.session_state.admin_match_results
            
            display_data = []
            for item in results_df:
                status = st.session_state.resume_statuses.get(item["resume_name"], 'Pending') 
                
                display_data.append({
                    "Resume": item["resume_name"],
                    "JD": item["jd_name"],
                    "Fit Score (out of 10)": item["overall_score"],
                    "Skills (%)": item.get("skills_percent", "N/A"),
                    "Experience (%)": item.get("experience_percent", "N/A"), 
                    "Education (%)": item.get("education_percent", "N/A"),
                    "Approval Status": status
                })

            st.dataframe(display_data, use_container_width=True)

            st.markdown("##### Detailed Reports")
            for item in results_df:
                header_text = f"Report for **{item['resume_name']}** against {item['jd_name']} (Score: **{item['overall_score']}/10** | S: **{item.get('skills_percent', 'N/A')}%** | E: **{item.get('experience_percent', 'N/A')}%** | Edu: **{item.get('education_percent', 'N/A')}%**)"
                with st.expander(header_text):
                    st.markdown(item['full_analysis'])

                    
    # --- TAB 3: User Management (NEW PARENT TAB) ---
    with tab_user_mgmt:
        st.header("🛠️ User Management")
        
        nested_tab_candidate, nested_tab_vendor = st.tabs([
            "👤 Candidate Approval",
            "🤝 Vendor Approval"
        ])
        
        with nested_tab_candidate:
            candidate_approval_tab_content() 
            
        with nested_tab_vendor:
            vendor_approval_tab_content() 


    # --- TAB 4: Statistics (Renumbered) ---
    with tab_statistics:
        st.header("System Statistics")
        st.markdown("---")

        total_candidates = len(st.session_state.resumes_to_analyze)
        total_jds = len(st.session_state.admin_jd_list)
        total_vendors = len(st.session_state.vendors)
        no_of_applications = total_candidates 
        
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(label="Total Candidates", value=total_candidates, delta="Resumes Submitted")

        with col2:
            st.metric(label="Total JDs", value=total_jds, delta_color="off")
        
        with col3:
            st.metric(label="Total Vendors", value=total_vendors, delta_color="off")

        with col4:
            st.metric(label="No. of Applications", value=no_of_applications, delta_color="off")
            
        st.markdown("---")
        
        status_counts = {}
        for status in st.session_state.resume_statuses.values():
            status_counts[status] = status_counts.get(status, 0) + 1
            
        st.subheader("Candidate Status Breakdown")
        
        status_cols = st.columns(len(status_counts) or 1)
        
        if status_counts:
            col_count = len(status_cols)
            for i, (status, count) in enumerate(status_counts.items()):
                with status_cols[i % col_count]:
                    st.metric(label=f"{status}", value=count)
        else:
            st.info("No resumes loaded to calculate status breakdown.")
