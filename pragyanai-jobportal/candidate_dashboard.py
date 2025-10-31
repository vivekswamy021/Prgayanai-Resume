# candidate_dashboard.py

import streamlit as st
from utils import go_to, parse_with_llm, parse_and_store_resume, qa_on_resume, generate_interview_questions, clear_interview_state, evaluate_interview_answers, extract_jd_from_linkedin_url, evaluate_jd_fit, question_section_options
import json
import re

def candidate_dashboard():
    st.header("👩‍🎓 Candidate Dashboard")
    st.markdown("Welcome! Use the tabs below to upload your resume and access AI preparation tools.")

    # --- MODIFIED NAVIGATION BLOCK ---
    nav_col, _ = st.columns([1, 1]) 

    with nav_col:
        if st.button("🚪 Log Out", key="candidate_logout_btn", use_container_width=True):
            go_to("login") 
    # --- END MODIFIED NAVIGATION BLOCK ---
    
    # Sidebar for Status Only
    with st.sidebar:
        st.header("Resume Status")
        
        if st.session_state.parsed.get("name"):
            st.success(f"Currently viewing: **{st.session_state.parsed['name']}**")
        elif st.session_state.full_text:
            st.warning("Resume content is loaded, but parsing may have errors.")
        else:
            st.info("Please upload and select a resume in the 'Resume Parsing' tab to begin.")

    # Main Content Tabs 
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📄 Resume Parsing", 
        "💬 Resume Chatbot (Q&A)", 
        "❓ Interview Prep", 
        "📚 JD Management", 
        "🎯 Batch JD Match" 
    ])
    
    is_resume_parsed = bool(st.session_state.get('parsed', {}).get('name')) or bool(st.session_state.get('full_text'))
    
    # --- TAB 1: Resume Parsing ---
    with tab1:
        st.header("Resume Upload and Parsing")
        
        # 1. Upload Section
        st.markdown("### 1. Upload Resume") 
        
        uploaded_file = st.file_uploader( 
            "Choose PDF or DOCX file", 
            type=["pdf", "docx"], 
            accept_multiple_files=False, 
            key='candidate_file_upload_main'
        )

        if uploaded_file is not None:
            st.session_state.candidate_uploaded_resumes = [uploaded_file] 
            st.toast("Resume uploaded successfully.")
        elif st.session_state.candidate_uploaded_resumes and uploaded_file is None:
             st.session_state.candidate_uploaded_resumes = []
             st.session_state.parsed = {}
             st.session_state.full_text = ""
             st.toast("Upload cleared.")

        st.markdown("---")

        # 2. Parse Uploaded Resume
        st.markdown("### 2. Parse Uploaded Resume")
        
        file_to_parse = st.session_state.candidate_uploaded_resumes[0] if st.session_state.candidate_uploaded_resumes else None
        
        if file_to_parse:
            if st.button(f"Parse and Load: **{file_to_parse.name}**", use_container_width=True):
                with st.spinner(f"Parsing {file_to_parse.name}..."):
                    result = parse_and_store_resume(file_to_parse, file_name_key='single_resume_candidate')
                    
                    if "error" not in result:
                        st.session_state.parsed = result['parsed']
                        st.session_state.full_text = result['full_text']
                        st.session_state.excel_data = result['excel_data'] 
                        st.session_state.parsed['name'] = result['name'] 
                        
                        clear_interview_state()
                        
                        st.success(f"Successfully loaded and parsed **{result['name']}**.")
                    else:
                        st.error(f"Parsing failed for {file_to_parse.name}: {result['error']}")
                        st.session_state.parsed = {"error": result['error'], "name": file_to_parse.name}
                        st.session_state.full_text = result['full_text'] or ""
        else:
            st.info("No resume file is currently uploaded. Please upload a file in section 1.")

            
        st.markdown("---")
            
        # 3. View Parsed Data
        st.markdown("### 3. View Parsed Data")
        is_resume_parsed = bool(st.session_state.get('parsed', {}).get('name')) or bool(st.session_state.get('full_text'))
        
        if is_resume_parsed:
            output_format = st.radio('Output Format', ['json', 'markdown'], key='format_radio_c')

            parsed = st.session_state.parsed
            full_text = st.session_state.full_text

            if "error" in parsed:
                st.error(parsed.get("error", "An unknown error occurred during parsing."))
            else:
                if output_format == 'json':
                    output_str = json.dumps(parsed, indent=2)
                    st.text_area("Parsed Output (JSON)", output_str, height=350)
                else:
                    output_str = parse_with_llm(full_text, return_type='markdown') if full_text else "Full text not available."
                    st.markdown("#### Parsed Output (Markdown)")
                    st.markdown(output_str)

                if st.session_state.excel_data:
                    st.download_button(
                        label="Download Parsed Data (Excel)",
                        data=st.session_state.excel_data,
                        file_name=f"{parsed.get('name', 'candidate').replace(' ', '_')}_parsed_data.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                
        else:
            st.warning("No resume has been parsed yet. Please click the 'Parse and Load' button in section 2.")


    # --- TAB 2: Resume Chatbot (Q&A) ---
    with tab2:
        st.header("Resume Chatbot (Q&A)")
        st.markdown("### Ask any question about the currently loaded resume.")
        if not is_resume_parsed:
            st.warning("Please upload and parse a resume in the 'Resume Parsing' tab first.")
        else:
            if 'qa_answer' not in st.session_state: st.session_state.qa_answer = ""
            
            question = st.text_input("Your Question", placeholder="e.g., What are the candidate's key skills?")
            
            if st.button("Get Answer", key="qa_btn"):
                with st.spinner("Generating answer..."):
                    try:
                        answer = qa_on_resume(question)
                        st.session_state.qa_answer = answer
                    except Exception as e:
                        st.error(f"Error during Q&A: {e}")
                        st.session_state.qa_answer = "Could not generate an answer."

            if st.session_state.get('qa_answer'):
                st.text_area("Answer", st.session_state.qa_answer, height=150)

    # --- TAB 3: Interview Prep ---
    with tab3:
        st.header("Interview Preparation Tools")
        if not is_resume_parsed or "error" in st.session_state.parsed:
            st.warning("Please upload and successfully parse a resume first.")
        else:
            if 'iq_output' not in st.session_state: st.session_state.iq_output = ""
            if 'interview_qa' not in st.session_state: st.session_state.interview_qa = [] 
            if 'evaluation_report' not in st.session_state: st.session_state.evaluation_report = "" 
            
            st.subheader("1. Generate Interview Questions")
            
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
                                    "answer": "", 
                                    "level": current_level
                                })
                                
                        st.session_state.interview_qa = q_list
                        
                        st.success(f"Generated {len(q_list)} questions based on your **{section_choice}** section.")
                        
                    except Exception as e:
                        st.error(f"Error generating questions: {e}")
                        st.session_state.iq_output = "Error generating questions."
                        st.session_state.interview_qa = []


            # --- INTERACTIVE Q&A SECTION ---
            if st.session_state.get('interview_qa'):
                st.markdown("---")
                st.subheader("2. Practice and Record Answers")
                
                with st.form("interview_practice_form"):
                    
                    for i, qa_item in enumerate(st.session_state.interview_qa):
                        st.markdown(f"**Question {i+1}:** {qa_item['question']}")
                        
                        answer = st.text_area(
                            f"Your Answer for Q{i+1}", 
                            value=st.session_state.interview_qa[i]['answer'], 
                            height=100,
                            key=f'answer_q_{i}',
                            label_visibility='collapsed'
                        )
                        st.session_state.interview_qa[i]['answer'] = answer 
                        st.markdown("---")
                        
                    submit_button = st.form_submit_button("Submit & Evaluate Answers", use_container_width=True)

                    if submit_button:
                        
                        if all(item['answer'].strip() for item in st.session_state.interview_qa):
                            with st.spinner("Sending answers to AI Evaluator..."):
                                try:
                                    report = evaluate_interview_answers(
                                        st.session_state.interview_qa,
                                        st.session_state.parsed
                                    )
                                    st.session_state.evaluation_report = report
                                    st.success("Evaluation complete! See the report below.")
                                except Exception as e:
                                    st.error(f"Evaluation failed: {e}")
                                    st.session_state.evaluation_report = f"Evaluation failed: {e}"
                        else:
                            st.error("Please answer all generated questions before submitting.")
                
                # Display Evaluation Report
                if st.session_state.get('evaluation_report'):
                    st.markdown("---")
                    st.subheader("3. AI Evaluation Report")
                    st.markdown(st.session_state.evaluation_report)
                    
            elif st.session_state.get('iq_output'):
                 st.text_area("Generated Interview Questions (Raw Output)", st.session_state.iq_output, height=400)
                
    # --- TAB 4: JD Management (Candidate) ---
    with tab4:
        st.header("📚 Manage Job Descriptions for Matching")
        st.markdown("Add multiple JDs here to compare your resume against them in the next tab.")
        
        if "candidate_jd_list" not in st.session_state:
             st.session_state.candidate_jd_list = []
        
        jd_type = st.radio("Select JD Type", ["Single JD", "Multiple JD"], key="jd_type_candidate")
        st.markdown("### Add JD by:")
        
        method = st.radio("Choose Method", ["Upload File", "Paste Text", "LinkedIn URL"], key="jd_add_method_candidate") 

        # URL
        if method == "LinkedIn URL":
            url_list = st.text_area(
                "Enter one or more URLs (comma separated)" if jd_type == "Multiple JD" else "Enter URL", key="url_list_candidate"
            )
            if st.button("Add JD(s) from URL", key="add_jd_url_btn_candidate"):
                if url_list:
                    urls = [u.strip() for u in url_list.split(",")] if jd_type == "Multiple JD" else [url_list.strip()]
                    
                    count = 0
                    for url in urls:
                        if not url: continue
                        
                        with st.spinner(f"Attempting JD extraction for: {url}"):
                            jd_text = extract_jd_from_linkedin_url(url)
                        
                        name_base = url.split('/jobs/view/')[-1].split('/')[0] if '/jobs/view/' in url else f"URL {count+1}"
                        name = f"JD from URL: {name_base}" 
                        if name in [item['name'] for item in st.session_state.candidate_jd_list]:
                            name = f"JD from URL: {name_base} ({len(st.session_state.candidate_jd_list) + 1})" 

                        st.session_state.candidate_jd_list.append({"name": name, "content": jd_text})
                        
                        if not jd_text.startswith("[Error"):
                            count += 1
                                
                    if count > 0:
                        st.success(f"✅ {count} JD(s) added successfully! Check the display below for the extracted content.")
                    else:
                        st.error("No JDs were added successfully.")


        # Paste Text
        elif method == "Paste Text":
            text_list = st.text_area(
                "Paste one or more JD texts (separate by '---')" if jd_type == "Multiple JD" else "Paste JD text here", key="text_list_candidate"
            )
            if st.button("Add JD(s) from Text", key="add_jd_text_btn_candidate"):
                if text_list:
                    texts = [t.strip() for t in text_list.split("---")] if jd_type == "Multiple JD" else [text_list.strip()]
                    for i, text in enumerate(texts):
                         if text:
                            name_base = text.splitlines()[0].strip()
                            if len(name_base) > 30: name_base = f"{name_base[:27]}..."
                            if not name_base: name_base = f"Pasted JD {len(st.session_state.candidate_jd_list) + i + 1}"
                            
                            st.session_state.candidate_jd_list.append({"name": name_base, "content": text})
                    st.success(f"✅ {len(texts)} JD(s) added successfully!")

        # Upload File
        elif method == "Upload File":
            uploaded_files = st.file_uploader(
                "Upload JD file(s)",
                type=["pdf", "txt", "docx"],
                accept_multiple_files=(jd_type == "Multiple JD"), 
                key="jd_file_uploader_candidate"
            )
            if st.button("Add JD(s) from File", key="add_jd_file_btn_candidate"):
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
                            st.session_state.candidate_jd_list.append({"name": file.name, "content": jd_text})
                            count += 1
                        else:
                            st.error(f"Error extracting content from {file.name}: {jd_text}")
                            
                if count > 0:
                    st.success(f"✅ {count} JD(s) added successfully!")
                elif uploaded_files:
                    st.error("No valid JD files were uploaded or content extraction failed.")


        # Display Added JDs
        if st.session_state.candidate_jd_list:
            
            col_display_header, col_clear_button = st.columns([3, 1])
            
            with col_display_header:
                st.markdown("### ✅ Current JDs Added:")
                
            with col_clear_button:
                if st.button("🗑️ Clear All JDs", key="clear_jds_candidate", use_container_width=True, help="Removes all currently loaded JDs."):
                    st.session_state.candidate_jd_list = []
                    st.session_state.candidate_match_results = [] 
                    st.success("All JDs and associated match results have been cleared.")
                    st.rerun() 

            for idx, jd_item in enumerate(st.session_state.candidate_jd_list, 1):
                title = jd_item['name']
                display_title = title.replace("--- Simulated JD for: ", "")
                with st.expander(f"JD {idx}: {display_title}"):
                    st.text(jd_item['content'])
        else:
            st.info("No Job Descriptions added yet.")

    # --- TAB 5: Batch JD Match (Candidate) ---
    with tab5:
        st.header("🎯 Batch JD Match")
        st.markdown("Compare your current resume against all saved job descriptions.")

        if not is_resume_parsed:
            st.warning("Please **upload and parse your resume** in the 'Resume Parsing' tab (Tab 1) first.")
        
        elif not st.session_state.candidate_jd_list:
            st.error("Please **add Job Descriptions** in the 'JD Management' tab (Tab 4) before running batch analysis.")
            
        else:
            if "candidate_match_results" not in st.session_state:
                st.session_state.candidate_match_results = []

            all_jd_names = [item['name'] for item in st.session_state.candidate_jd_list]
            
            selected_jd_names = st.multiselect(
                "Select Job Descriptions to Match Against",
                options=all_jd_names,
                default=all_jd_names, 
                key='candidate_batch_jd_select'
            )
            
            jds_to_match = [
                jd_item for jd_item in st.session_state.candidate_jd_list 
                if jd_item['name'] in selected_jd_names
            ]

            if st.button(f"Run Match Analysis on {len(jds_to_match)} Selected JD(s)"):
                st.session_state.candidate_match_results = []
                
                if not jds_to_match:
                    st.warning("Please select at least one Job Description to run the analysis.")
                    
                else:
                    resume_name = st.session_state.parsed.get('name', 'Uploaded Resume')
                    parsed_json = st.session_state.parsed

                    with st.spinner(f"Matching {resume_name}'s resume against {len(jds_to_match)} selected JD(s)..."):
                        
                        for jd_item in jds_to_match:
                            
                            jd_name = jd_item['name']
                            jd_content = jd_item['content']

                            try:
                                fit_output = evaluate_jd_fit(jd_content, parsed_json)
                                
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

                                st.session_state.candidate_match_results.append({
                                    "jd_name": jd_name,
                                    "overall_score": overall_score,
                                    "skills_percent": skills_percent,
                                    "experience_percent": experience_percent, 
                                    "education_percent": education_percent,   
                                    "full_analysis": fit_output
                                })
                            except Exception as e:
                                st.session_state.candidate_match_results.append({
                                    "jd_name": jd_name,
                                    "overall_score": "Error",
                                    "skills_percent": "Error",
                                    "experience_percent": "Error", 
                                    "education_percent": "Error",   
                                    "full_analysis": f"Error running analysis for {jd_name}: {e}"
                                })
                        st.success("Batch analysis complete!")


            # 3. Display Results
            if st.session_state.get('candidate_match_results'):
                st.markdown("#### Match Results for Your Resume")
                results_df = st.session_state.candidate_match_results
                
                display_data = []
                for item in results_df:
                    display_data.append({
                        "Job Description": item["jd_name"].replace("--- Simulated JD for: ", ""),
                        "Fit Score (out of 10)": item["overall_score"],
                        "Skills (%)": item.get("skills_percent", "N/A"),
                        "Experience (%)": item.get("experience_percent", "N/A"), 
                        "Education (%)": item.get("education_percent", "N/A"),   
                    })

                st.dataframe(display_data, use_container_width=True)

                st.markdown("##### Detailed Reports")
                for item in results_df:
                    header_text = f"Report for **{item['jd_name'].replace('--- Simulated JD for: ', '')}** (Score: **{item['overall_score']}/10** | S: **{item.get('skills_percent', 'N/A')}%** | E: **{item.get('experience_percent', 'N/A')}%** | Edu: **{item.get('education_percent', 'N/A')}%**)"
                    with st.expander(header_text):
                        st.markdown(item['full_analysis'])
