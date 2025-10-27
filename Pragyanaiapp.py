import streamlit as st
import os
import pdfplumber
import docx
import openpyxl
import json
import tempfile
from groq import Groq
import traceback
import re
from dotenv import load_dotenv 
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime

# -------------------------
# CONFIGURATION & API SETUP
# -------------------------

# CRITICAL FIX: Using the currently supported Groq model.
GROQ_MODEL = "llama-3.1-8b-instant"

# Options for LLM functions
section_options = ["name", "email", "phone", "skills", "education", "experience", "certifications", "projects", "strength", "personal_details", "github", "linkedin", "full resume"]
question_section_options = ["skills","experience", "certifications", "education", "projects"]

# Load environment variables from .env file
load_dotenv()

GROQ_API_KEY = os.getenv('GROQ_API_KEY')
MONGODB_URI = os.getenv('MONGODB_URI') 

# --- CRITICAL ENVIRONMENT VARIABLE CHECK ---
if not GROQ_API_KEY:
    st.error(
        "🚨 FATAL ERROR: GROQ_API_KEY environment variable not set. "
        "Please ensure a '.env' file exists in the script directory with your key."
    )
    st.stop()

if not MONGODB_URI:
    st.error(
        "🚨 FATAL ERROR: MONGODB_URI environment variable not set. "
        "The application requires a MongoDB connection. Please check your '.env' file."
    )
    st.stop()
# --- END ENVIRONMENT VARIABLE CHECK ---

# Initialize Groq Client
client = Groq(api_key=GROQ_API_KEY)

# -------------------------
# MongoDB Database Manager
# -------------------------

class DatabaseManager:
    """Handles connection and CRUD operations for MongoDB."""
    def __init__(self, uri):
        self.client = None
        self.db = None
        
        # Use st.cache_resource for the connection client
        @st.cache_resource(ttl=3600)
        def init_connection(mongo_uri):
            try:
                # Add server selection timeout to prevent infinite hangs
                client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5500)
                # Attempt a quick command to verify connection and configuration
                client.admin.command('ping') 
                
                # CRITICAL FIX: Check for default database before returning
                # This explicitly raises the ConfigurationError if the DB name is missing
                client.get_default_database() 
                
                return client
            except ConfigurationError as e:
                # Catch the specific error about the missing database name
                print(f"MongoDB Configuration Error: {e}")
                st.error(
                    "❌ MongoDB Configuration Error: The connection string is missing the database name. "
                    "Ensure your MONGODB_URI format is correct: "
                    "`mongodb+srv://user:pass@cluster.mongodb.net/DATABASE_NAME?query`"
                )
                return None
            except (PyMongoConnectionError, Exception) as e:
                # Catch general connection errors (auth, network, etc.)
                error_detail = str(e)
                if 'bad auth' in error_detail:
                    st.error("❌ MongoDB Connection Error: Authentication failed (Bad Auth). Check MONGODB_URI username and password.")
                else:
                    st.error(f"❌ MongoDB Connection Error: Failed to connect. Check MONGODB_URI and network access. Error: {e}")
                print(f"MongoDB Connection Error: {e}")
                return None

        self.client = init_connection(uri)
        if self.client:
            try:
                # Get the default database name specified in the connection string
                self.db = self.client.get_default_database()
            except ConfigurationError:
                # This should be caught by init_connection, but included for robustness
                self.db = None
        
    def is_connected(self):
        return self.client is not None and self.db is not None
        
    # --- JD Management ---
    def save_jd(self, jd_data, user_role):
        if not self.is_connected(): return None
        collection = self.db[f'{user_role}_jds']
        # Use name and content hash to check for duplicates, simpler check here
        existing_jd = collection.find_one({'name': jd_data['name'], 'content': jd_data['content']})
        
        # Add timestamp for tracking
        jd_data['updated_at'] = datetime.utcnow()
        
        if existing_jd:
            # Update existing JD (though usually not necessary for JDs)
            collection.update_one({'_id': existing_jd['_id']}, {'$set': jd_data})
            return existing_jd['_id']
        else:
            jd_data['created_at'] = datetime.utcnow()
            result = collection.insert_one(jd_data)
            return result.inserted_id

    def get_jds(self, user_role):
        if not self.is_connected(): return []
        collection = self.db[f'{user_role}_jds']
        jds = list(collection.find({}).sort('created_at', -1))
        # Convert ObjectId to string for safe handling in Streamlit
        for jd in jds:
            jd['_id'] = str(jd['_id'])
        return jds
        
    # --- Resume Management (Admin) ---
    def save_resume(self, resume_data):
        if not self.is_connected(): return None
        collection = self.db['admin_resumes']
        
        resume_name = resume_data['name']
        resume_data['updated_at'] = datetime.utcnow()

        # Check for resume with the same name
        existing_resume = collection.find_one({'name': resume_name})
        if existing_resume:
            collection.update_one({'_id': existing_resume['_id']}, {'$set': resume_data})
            return existing_resume['_id']
        else:
            resume_data['created_at'] = datetime.utcnow()
            result = collection.insert_one(resume_data)
            return result.inserted_id

    def get_resumes(self):
        if not self.is_connected(): return []
        collection = self.db['admin_resumes']
        resumes = list(collection.find({}).sort('created_at', -1))
        for resume in resumes:
            resume['_id'] = str(resume['_id'])
        return resumes
        
    # --- Match Results (Admin and Candidate) ---
    def save_match_result(self, result_data, user_role):
        if not self.is_connected(): return None
        collection = self.db[f'{user_role}_match_results']
        result_data['created_at'] = datetime.utcnow()
        result = collection.insert_one(result_data)
        return result.inserted_id
        
    def get_match_results(self, user_role):
        if not self.is_connected(): return []
        collection = self.db[f'{user_role}_match_results']
        # Get the last 50 results (or fewer)
        results = list(collection.find({}).sort('created_at', -1).limit(50)) 
        for result in results:
            result['_id'] = str(result['_id'])
            # Format the datetime for display
            if 'created_at' in result:
                result['created_at_str'] = result['created_at'].strftime("%Y-%m-%d %H:%M")
        return results

    # --- Utility: Clear all data (for demo/admin) ---
    def clear_all_data(self):
        if not self.is_connected(): return
        
        # Clear all application-specific collections
        self.db.admin_jds.drop()
        self.db.candidate_jds.drop()
        self.db.admin_resumes.drop()
        self.db.admin_match_results.drop()
        self.db.candidate_match_results.drop()
        
        # Reset session state lists (will be reloaded on next dashboard entry)
        if 'admin_jd_list' in st.session_state: st.session_state.admin_jd_list = []
        if 'resumes_to_analyze' in st.session_state: st.session_state.resumes_to_analyze = []
        if 'admin_match_results' in st.session_state: st.session_state.admin_match_results = []
        if 'candidate_jd_list' in st.session_state: st.session_state.candidate_jd_list = []
        if 'candidate_match_results' in st.session_state: st.session_state.candidate_match_results = []

# -------------------------
# Utility: Navigation Manager
# -------------------------
def go_to(page_name):
    """Changes the current page in Streamlit's session state."""
    st.session_state.page = page_name

# -------------------------
# CORE LOGIC: FILE HANDLING AND EXTRACTION
# -------------------------

def get_file_type(file_path):
    """Identifies the file type based on its extension."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.pdf':
        return 'pdf'
    elif ext == '.docx':
        return 'docx'
    else:
        return 'txt' 

def extract_content(file_type, file_path):
    """Extracts text content from PDF or DOCX files using robust libraries."""
    try:
        if file_type == 'pdf':
            text = ''
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + '\n'
            if not text.strip():
                return "Error: PDF extraction failed. The file might be a scanned image without searchable text or is empty."
            return text
        
        elif file_type == 'docx':
            doc = docx.Document(file_path)
            text = '\n'.join([para.text for para in doc.paragraphs])
            if not text.strip():
                return "Error: DOCX content extraction failed. The file appears to be empty."
            return text
        
        elif file_type == 'txt':
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        
        else:
            return "Error: Unsupported file type."
    
    except Exception as e:
        return f"Fatal Extraction Error: Failed to read file content. Error details: {e}"

@st.cache_data(show_spinner="Analyzing content with Groq LLM...")
def parse_with_llm(text, return_type='json'):
    """Sends resume text to the LLM for structured information extraction."""
    if text.startswith("Error"):
        return {"error": text, "raw_output": ""}

    prompt = f"""Extract the following information from the resume in structured JSON.
    Ensure all relevant details for each category are captured.
    - Name, - Email, - Phone, - Skills, - Education (list of degrees/institutions/dates), 
    - Experience (list of job roles/companies/dates/responsibilities), - Certifications (list), 
    - Projects (list of project names/descriptions/technologies), - Strength (list of personal strengths/qualities), 
    - Personal Details (e.g., address, date of birth, nationality), - Github (URL), - LinkedIn (URL)
    
    Resume Text:
    {text}
    
    Provide the output strictly as a JSON object.
    """
    content = ""
    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        content = response.choices[0].message.content.strip()

        # Robust JSON extraction
        json_str = content
        if json_str.startswith('```json'):
            json_str = json_str[len('```json'):]
        if json_str.endswith('```'):
            json_str = json_str[:-len('```')]
        json_str = json_str.strip()

        json_start = json_str.find('{')
        json_end = json_str.rfind('}') + 1

        if json_start != -1 and json_end != -1 and json_end > json_start:
            json_str = json_str[json_start:json_end]

        parsed = json.loads(json_str)

    except json.JSONDecodeError as e:
        error_msg = f"JSON decoding error from LLM. LLM returned malformed JSON. Error: {e}"
        parsed = {"error": error_msg, "raw_output": content}
    except Exception as e:
        error_msg = f"LLM API interaction error: {e}"
        parsed = {"error": error_msg, "raw_output": "No LLM response due to API error."}

    if return_type == 'json':
        return parsed
    elif return_type == 'markdown':
        if "error" in parsed:
            return f"**Error:** {parsed.get('error', 'Unknown parsing error')}\nRaw output:\n```\n{parsed.get('raw_output','')}\n```"
        
        md = ""
        for k, v in parsed.items():
            if v:
                md += f"**{k.replace('_', ' ').title()}**:\n"
                if isinstance(v, list):
                    for item in v:
                        if item: 
                            md += f"- {item}\n"
                elif isinstance(v, dict):
                    for sub_k, sub_v in v.items():
                        if sub_v:
                            md += f"  - {sub_k.replace('_', ' ').title()}: {sub_v}\n"
                else:
                    md += f"  {v}\n"
                md += "\n"
        return md
    return {"error": "Invalid return_type"}


def extract_jd_from_linkedin_url(url: str) -> str:
    """
    Simulates JD content extraction from a LinkedIn URL.
    This simulation is used for robustness in a pure Streamlit environment.
    """
    try:
        job_title = "Data Scientist"
        try:
            match = re.search(r'/jobs/view/([^/]+)', url)
            if match:
                job_title = match.group(1).replace('-', ' ').title()
        except:
            pass

        if "linkedin.com/jobs/" not in url:
             return f"[Error: Not a valid LinkedIn Job URL format: {url}]"

        
        # Simulated synthesized JD content 
        jd_text = f"""
        --- Simulated JD for: {job_title} ---
        
        **Company:** Quantum Analytics Inc.
        **Role:** {job_title}
        
        **Responsibilities:**
        - Develop and implement machine learning models to solve complex business problems.
        - Clean, transform, and analyze large datasets using Python/R and SQL.
        - Collaborate with engineering teams to deploy models into production environments.
        - Communicate findings and model performance to non-technical stakeholders.
        
        **Requirements:**
        - MS/PhD in Computer Science, Statistics, or a quantitative field.
        - 3+ years of experience as a Data Scientist.
        - Expertise in Python (Pandas, Scikit-learn, TensorFlow/PyTorch).
        - Experience with cloud platforms (AWS, Azure, or GCP).
        
        --- End Simulated JD ---
        """
        
        return jd_text.strip()
            
    except Exception as e:
        return f"[Fatal Extraction Error: Simulation failed for URL {url}. Error: {e}]"


def evaluate_jd_fit(job_description, parsed_json):
    """Evaluates how well a resume fits a given job description, including section-wise scores."""
    if not job_description.strip(): return "Please paste a job description."
    
    relevant_resume_data = {
        'Skills': parsed_json.get('skills', 'Not found or empty'),
        'Experience': parsed_json.get('experience', 'Not found or empty'),
        'Education': parsed_json.get('education', 'Not found or empty'),
    }
    resume_summary = json.dumps(relevant_resume_data, indent=2)

    prompt = f"""Evaluate how well the following resume content matches the provided job description.
    
    Job Description: {job_description}
    
    Resume Sections for Analysis:
    {resume_summary}
    
    Provide a detailed evaluation structured as follows:
    1.  **Overall Fit Score:** A score out of 10.
    2.  **Section Match Percentages:** A percentage score for the match in the key sections (Skills, Experience, Education).
    3.  **Strengths/Matches:** Key points where the resume aligns well with the JD.
    4.  **Gaps/Areas for Improvement:** Key requirements in the JD that are missing or weak in the resume.
    5.  **Overall Summary:** A concise summary of the fit.
    
    **Format the output strictly as follows:**
    Overall Fit Score: [Score]/10
    
    --- Section Match Analysis ---
    Skills Match: [XX]%
    Experience Match: [YY]%
    Education Match: [ZZ]%
    
    Strengths/Matches:
    - Point 1
    - Point 2
    
    Gaps/Areas for Improvement:
    - Point 1
    - Point 2
    
    Overall Summary: [Concise summary]
    """

    response = client.chat.completions.create(
        model=GROQ_MODEL, 
        messages=[{"role": "user", "content": prompt}], 
        temperature=0.3
    )
    return response.choices[0].message.content.strip()


# -------------------------
# Utility Functions
# -------------------------
def dump_to_excel(parsed_json, filename):
    """Dumps parsed JSON data to an Excel file."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Profile Data"
    ws.append(["Category", "Details"])
    
    section_order = ['name', 'email', 'phone', 'github', 'linkedin', 'experience', 'education', 'skills', 'projects', 'certifications', 'strength', 'personal_details']
    
    for section_key in section_order:
        if section_key in parsed_json and parsed_json[section_key]:
            content = parsed_json[section_key]
            
            if section_key in ['name', 'email', 'phone', 'github', 'linkedin']:
                ws.append([section_key.replace('_', ' ').title(), str(content)])
            else:
                ws.append([])
                ws.append([section_key.replace('_', ' ').title()])
                
                if isinstance(content, list):
                    for item in content:
                        ws.append(["", str(item)])
                elif isinstance(content, dict):
                    for k, v in content.items():
                        ws.append(["", f"{k.replace('_', ' ').title()}: {v}"])
                else:
                    ws.append(["", str(content)])

    wb.save(filename)
    with open(filename, "rb") as f:
        return f.read()

def parse_and_store_resume(uploaded_file, file_name_key='default'):
    """Handles file upload, parsing, and stores results in session state and DB."""
    
    temp_dir = tempfile.mkdtemp()
    temp_path = os.path.join(temp_dir, uploaded_file.name)
    with open(temp_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    file_type = get_file_type(temp_path)
    text = extract_content(file_type, temp_path)
    
    if text.startswith("Error"):
        return {"error": text, "full_text": text}

    parsed = parse_with_llm(text, return_type='json')
    
    if not parsed or "error" in parsed:
        return {"error": parsed.get('error', 'Unknown parsing error'), "full_text": text}

    # Generate Excel data for download
    excel_data = None
    if file_name_key == 'single_resume_candidate':
        try:
            name = parsed.get('name', 'candidate').replace(' ', '_').strip()
            name = "".join(c for c in name if c.isalnum() or c in ('_', '-')).rstrip()
            if not name: name = "candidate"
            excel_filename = os.path.join(tempfile.gettempdir(), f"{name}_parsed_data.xlsx")
            excel_data = dump_to_excel(parsed, excel_filename)
        except Exception as e:
            st.warning(f"Could not generate Excel file for single resume: {e}")
    
    # NEW: Store resume data in MongoDB if it's an Admin upload
    if file_name_key == 'admin_analysis' and st.session_state.db.is_connected():
        resume_data_to_store = {
            "name": parsed.get('name', uploaded_file.name.split('.')[0]),
            "parsed": parsed,
            "full_text": text
        }
        st.session_state.db.save_resume(resume_data_to_store)
        
    return {
        "parsed": parsed,
        "full_text": text,
        "excel_data": excel_data,
        "name": parsed.get('name', uploaded_file.name.split('.')[0])
    }


def qa_on_resume(question):
    """Chatbot for Resume (Q&A) using LLM."""
    parsed_json = st.session_state.parsed
    full_text = st.session_state.full_text
    prompt = f"""Given the following resume information:
    Resume Text: {full_text}
    Parsed Resume Data (JSON): {json.dumps(parsed_json, indent=2)}
    Answer the following question about the resume concisely and directly.
    If the information is not present, state that clearly.
    Question: {question}
    """
    response = client.chat.completions.create(model=GROQ_MODEL, messages=[{"role": "user", "content": prompt}], temperature=0.4)
    return response.choices[0].message.content.strip()

def generate_interview_questions(parsed_json, section):
    """Generates categorized interview questions using LLM."""
    section_title = section.replace("_", " ").title()
    section_content = parsed_json.get(section, "")
    if isinstance(section_content, (list, dict)):
        section_content = json.dumps(section_content, indent=2)
    elif not isinstance(section_content, str):
        section_content = str(section_content)

    if not section_content.strip():
        return f"No significant content found for the '{section_title}' section in the parsed resume. Please select a section with relevant data to generate questions."

    prompt = f"""Based on the following {section_title} section from the resume: {section_content}
Generate 3 interview questions each for these levels: Generic, Basic, Intermediate, Difficult.
**IMPORTANT: Format the output strictly as follows, with level headers and questions starting with 'Qx:':**
[Generic]
Q1: Question text...
...
[Difficult]
Q1: Question text...
    """
    response = client.chat.completions.create(
        model=GROQ_MODEL, 
        messages=[{"role": "user", "content": prompt}], 
        temperature=0.5
    )
    return response.choices[0].message.content.strip()


# -------------------------
# UI PAGES: Authentication
# -------------------------
def login_page():
    st.title("🌐 PragyanAI Job Portal")
    st.header("Login")

    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if st.button("Login", use_container_width=True):
        if email and password:
            st.success("Login successful!")
            go_to("role_selection")
        else:
            st.error("Please enter both email and password")

    st.markdown("---")
    
    if st.button("Don't have an account? Sign up here"):
        go_to("signup")

def signup_page():
    st.header("Create an Account")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    confirm = st.text_input("Confirm Password", type="password")

    if st.button("Sign Up", use_container_width=True):
        if password == confirm and email:
            st.success("Signup successful! Please login.")
            go_to("login")
        else:
            st.error("Passwords do not match or email is empty")

    if st.button("Already have an account? Login here"):
        go_to("login")

def role_selection_page():
    st.header("Select Your Role")
    role = st.selectbox(
        "Choose a Dashboard",
        ["Select Role", "Admin Dashboard", "Candidate Dashboard", "Hiring Company Dashboard"]
    )

    col1, col2 = st.columns([2, 1])

    with col1:
        if st.button("Continue", use_container_width=True):
            if role == "Admin Dashboard":
                go_to("admin_dashboard")
            elif role == "Candidate Dashboard":
                go_to("candidate_dashboard")
            elif role == "Hiring Company Dashboard":
                go_to("hiring_dashboard")
            else:
                st.warning("Please select a role first")

    with col2:
        if st.button("⬅️ Go Back to Login"):
            go_to("login")

# -------------------------
# UI PAGES: Dashboards
# -------------------------

def admin_dashboard():
    st.header("🧑‍💼 Admin Dashboard")
    st.sidebar.button("⬅️ Go Back to Role Selection", on_click=go_to, args=("role_selection",))
    
    # NEW: Check DB connection status
    if 'db' not in st.session_state or not st.session_state.db.is_connected():
        st.error("🚨 Cannot proceed: MongoDB database is not connected. Please check your MONGODB_URI or contact support.")
        return 
    
    # Initialize Admin session state variables and load from DB
    if "admin_jd_list" not in st.session_state:
        st.session_state.admin_jd_list = st.session_state.db.get_jds('admin')
    if "resumes_to_analyze" not in st.session_state:
        st.session_state.resumes_to_analyze = st.session_state.db.get_resumes()
    if "admin_match_results" not in st.session_state:
        st.session_state.admin_match_results = st.session_state.db.get_match_results('admin')
    
    tab_jd, tab_analysis, tab_settings = st.tabs(["📄 Job Description Management", "📊 Resume Analysis", "⚙️ Settings"])

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
                        if not jd_text.startswith("[Error"):
                            # Save to DB
                            jd_data = {"name": f"JD from URL: {name_base}", "content": jd_text, "source": "url"}
                            st.session_state.db.save_jd(jd_data, 'admin')
                            count += 1
                            
                    # Refresh list from DB
                    st.session_state.admin_jd_list = st.session_state.db.get_jds('admin')
                    if count > 0:
                        st.success(f"✅ {count} JD(s) added successfully!")
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
                            
                            # Save to DB
                            jd_data = {"name": name_base, "content": text, "source": "pasted"}
                            st.session_state.db.save_jd(jd_data, 'admin')
                            
                    # Refresh list from DB
                    st.session_state.admin_jd_list = st.session_state.db.get_jds('admin')
                    st.success(f"✅ {len(texts)} JD(s) added successfully!")

        # Upload File
        elif method == "Upload File":
            uploaded_files = st.file_uploader(
                "Upload JD file(s)",
                type=["pdf", "txt", "docx"],
                accept_multiple_files=True if jd_type == "Multiple JD" else False,
                key="jd_file_uploader_admin"
            )
            if st.button("Add JD(s) from File", key="add_jd_file_btn_admin"):
                files_to_process = uploaded_files if jd_type == "Multiple JD" and uploaded_files else [uploaded_files]
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
                            # Save to DB
                            jd_data = {"name": file.name, "content": jd_text, "source": "file"}
                            st.session_state.db.save_jd(jd_data, 'admin')
                            count += 1
                            
                # Refresh list from DB
                st.session_state.admin_jd_list = st.session_state.db.get_jds('admin')
                if count > 0:
                    st.success(f"✅ {count} JD(s) added successfully!")
                else:
                    st.error("No valid JD files were uploaded or content extraction failed.")

        # Display Added JDs
        if st.session_state.admin_jd_list:
            st.markdown("### ✅ Current JDs Added (Persistent in DB):")
            for idx, jd_item in enumerate(st.session_state.admin_jd_list, 1):
                title = jd_item['name']
                display_title = title.replace("--- Simulated JD for: ", "")
                col_disp, col_del = st.columns([10, 1])
                with col_disp:
                    with st.expander(f"JD {idx}: {display_title} (Added: {jd_item.get('created_at', 'N/A').strftime('%Y-%m-%d')})"):
                        st.text(jd_item['content'])
                with col_del:
                    if st.button("🗑️", key=f"del_jd_admin_{jd_item['_id']}"):
                        st.session_state.db.db.admin_jds.delete_one({'_id': ObjectId(jd_item['_id'])})
                        # Refresh list immediately after deletion
                        st.session_state.admin_jd_list = st.session_state.db.get_jds('admin')
                        st.rerun()
        else:
            st.info("No Job Descriptions added yet.")


    # --- TAB 2: Resume Analysis (Admin logic) ---
    with tab_analysis:
        st.subheader("Analyze Resumes Against Job Descriptions")

        # 1. Resume Upload (Admin uses st.session_state.resumes_to_analyze list)
        st.markdown("#### 1. Upload Resumes (Saved to DB)")
        resume_upload_type = st.radio("Upload Type", ["Single Resume", "Multiple Resumes"], key="resume_upload_type_admin")

        uploaded_files = st.file_uploader(
            "Choose files to analyze",
            type=["pdf", "docx", "txt", "json", "rtf"], 
            accept_multiple_files=(resume_upload_type == "Multiple Resumes"),
            key="resume_file_uploader_admin"
        )
        
        if st.button("Load and Parse Resume(s) for Analysis", key="parse_resumes_admin"):
            if uploaded_files:
                files_to_process = uploaded_files if isinstance(uploaded_files, list) else [uploaded_files]
                count = 0
                with st.spinner("Parsing resume(s)... This may take a moment."):
                    for file in files_to_process:
                        if file:
                            # parse_and_store_resume saves to DB if file_name_key='admin_analysis'
                            result = parse_and_store_resume(file, file_name_key='admin_analysis')
                            
                            if "error" not in result:
                                count += 1
                            else:
                                st.error(f"Failed to parse {file.name}: {result['error']}")

                # Refresh list from DB
                st.session_state.resumes_to_analyze = st.session_state.db.get_resumes()
                if count > 0:
                    st.success(f"Successfully loaded and parsed {count} resume(s) for analysis and saved to DB.")
                elif not st.session_state.resumes_to_analyze:
                    st.warning("No new resumes were successfully loaded and parsed.")
            else:
                st.warning("Please upload one or more resume files.")

        st.markdown("#### Resumes Available for Analysis (Loaded from DB):")
        if st.session_state.resumes_to_analyze:
             for resume_data in st.session_state.resumes_to_analyze:
                 st.write(f"- **{resume_data['name']}** (ID: {resume_data['_id'][:6]}...)")
        else:
             st.info("No resumes available.")
        
        st.markdown("---")

        # 2. JD Selection and Analysis
        st.markdown("#### 2. Select JD and Run Analysis")

        if not st.session_state.resumes_to_analyze:
            st.info("Upload and parse resumes first to enable analysis.")
            return

        if not st.session_state.admin_jd_list:
            st.error("Please add at least one Job Description in the 'JD Management' tab before running an analysis.")
            return

        jd_options = {item['name']: item['content'] for item in st.session_state.admin_jd_list}
        selected_jd_name = st.selectbox("Select JD for Matching", list(jd_options.keys()), key="select_jd_admin")
        selected_jd_content = jd_options.get(selected_jd_name, "")


        if st.button("Run Match Analysis", key="run_match_analysis_admin"):
            
            if not selected_jd_content:
                st.error("Selected JD content is empty.")
                return

            with st.spinner(f"Matching {len(st.session_state.resumes_to_analyze)} resumes against '{selected_jd_name}'..."):
                for resume_data in st.session_state.resumes_to_analyze:
                    
                    resume_name = resume_data['name']
                    parsed_json = resume_data['parsed']

                    try:
                        fit_output = evaluate_jd_fit(selected_jd_content, parsed_json)
                        
                        # --- ENHANCED EXTRACTION LOGIC (FIXED) ---
                        # Robust Regexes to handle single-line LLM output
                        overall_score_match = re.search(r'Overall Fit Score:\s*(\d+)\s*/10', fit_output, re.IGNORECASE)
                        section_analysis_match = re.search(
                             r'--- Section Match Analysis ---\s*(.*?)\s*Strengths/Matches:', 
                             fit_output, re.DOTALL
                        )

                        skills_percent = 'N/A'
                        experience_percent = 'N/A'
                        education_percent = 'N/A'
                        
                        if section_analysis_match:
                            section_text = section_analysis_match.group(1)
                            skills_match = re.search(r'Skills Match:\s*(\d+)%', section_text, re.IGNORECASE)
                            experience_match = re.search(r'Experience Match:\s*(\d+)%', section_text, re.IGNORECASE)
                            education_match = re.search(r'Education Match:\s*(\d+)%', section_text, re.IGNORECASE)
                            
                            if skills_match: skills_percent = skills_match.group(1)
                            if experience_match: experience_percent = experience_match.group(1)
                            if education_match: education_percent = education_match.group(1)
                        
                        overall_score = overall_score_match.group(1) if overall_score_match else 'N/A'
                        # --- END ENHANCED EXTRACTION LOGIC (FIXED) ---

                        result_item = {
                            "resume_name": resume_name,
                            "jd_name": selected_jd_name,
                            "overall_score": overall_score,
                            "skills_percent": skills_percent,
                            "experience_percent": experience_percent, 
                            "education_percent": education_percent,   
                            "full_analysis": fit_output
                        }
                        # Save results to DB
                        st.session_state.db.save_match_result(result_item, 'admin')
                        
                    except Exception as e:
                        error_item = {
                            "resume_name": resume_name,
                            "jd_name": selected_jd_name,
                            "overall_score": "Error",
                            "skills_percent": "Error",
                            "experience_percent": "Error", 
                            "education_percent": "Error",   
                            "full_analysis": f"Error running analysis: {e}\n{traceback.format_exc()}"
                        }
                        st.session_state.db.save_match_result(error_item, 'admin')
                        
                # Refresh match results from DB
                st.session_state.admin_match_results = st.session_state.db.get_match_results('admin')
                st.success("Analysis complete and results saved to DB!")


        # 3. Display Results
        if st.session_state.get('admin_match_results'):
            st.markdown("#### 3. Recent Match Results (Loaded from DB)")
            
            # Filter by selected JD for better focus
            results_to_display = [r for r in st.session_state.admin_match_results if r['jd_name'] == selected_jd_name]
            # If no results match the current JD, show all recent results
            if not results_to_display:
                results_to_display = st.session_state.admin_match_results
                st.info(f"Showing all {len(results_to_display)} most recent results as none match the selected JD: {selected_jd_name}")

            display_data = []
            for item in results_to_display:
                display_data.append({
                    "Resume": item["resume_name"],
                    "JD": item["jd_name"],
                    "Fit Score (out of 10)": item["overall_score"],
                    "Skills (%)": item.get("skills_percent", "N/A"),
                    "Experience (%)": item.get("experience_percent", "N/A"), 
                    "Education (%)": item.get("education_percent", "N/A"),
                    "Time": item.get('created_at_str', 'N/A')
                })

            st.dataframe(display_data, use_container_width=True)

            # Display detailed analysis in expanders
            st.markdown("##### Detailed Reports")
            for item in results_to_display:
                header_text = f"Report for **{item['resume_name']}** against {item['jd_name']} (Score: **{item['overall_score']}/10** | S: **{item.get('skills_percent', 'N/A')}%** | E: **{item.get('experience_percent', 'N/A')}%** | Edu: **{item.get('education_percent', 'N/A')}%**)"
                with st.expander(header_text):
                    st.markdown(item['full_analysis'])
                    
    # --- TAB 3: Settings ---
    with tab_settings:
        st.subheader("Database Settings")
        st.warning("Use these options with caution, as they affect persistent data.")
        
        if st.button("🔄 Reload All Data from MongoDB", key="reload_db_admin"):
            st.session_state.admin_jd_list = st.session_state.db.get_jds('admin')
            st.session_state.resumes_to_analyze = st.session_state.db.get_resumes()
            st.session_state.admin_match_results = st.session_state.db.get_match_results('admin')
            st.session_state.candidate_jd_list = st.session_state.db.get_jds('candidate')
            st.session_state.candidate_match_results = st.session_state.db.get_match_results('candidate')
            st.success("All data reloaded from MongoDB.")
            st.rerun()

        st.markdown("---")
        if st.button("🚨 Clear ALL Application Data from MongoDB 🚨", key="clear_db_admin"):
            if st.session_state.db and st.session_state.db.is_connected():
                st.session_state.db.clear_all_data()
                st.success("All application data cleared from MongoDB and session state reset.")
                st.rerun()
            else:
                st.error("Database is not connected.")


def candidate_dashboard():
    st.header("👩‍🎓 Candidate Dashboard")
    st.markdown("Welcome! Use the tabs below to upload your resume and access AI preparation tools.")

    st.sidebar.button("⬅️ Go Back to Role Selection", on_click=go_to, args=("role_selection",))
    
    # NEW: Check DB connection status
    if 'db' not in st.session_state or not st.session_state.db.is_connected():
        st.error("🚨 Cannot proceed: MongoDB database is not connected. Please check your MONGODB_URI or contact support.")
        return 
        
    # Initialize candidate JD and results lists from DB
    if "candidate_jd_list" not in st.session_state:
        st.session_state.candidate_jd_list = st.session_state.db.get_jds('candidate')
    if "candidate_match_results" not in st.session_state:
        st.session_state.candidate_match_results = st.session_state.db.get_match_results('candidate')

    # Sidebar for Resume Upload (Centralized Upload)
    with st.sidebar:
        st.header("Upload Your Resume")
        uploaded_file = st.file_uploader("Choose a PDF or DOCX file", type=["pdf", "docx"])
        
        if uploaded_file is not None:
            if st.button("Parse Resume", use_container_width=True):
                result = parse_and_store_resume(uploaded_file, file_name_key='single_resume_candidate')
                
                if "error" not in result:
                    st.session_state.parsed = result['parsed']
                    st.session_state.full_text = result['full_text']
                    st.session_state.excel_data = result['excel_data'] 
                    st.success("Resume parsed successfully!")
                else:
                    st.error(f"Parsing failed: {result['error']}")

        
        st.markdown("---")
        if st.session_state.parsed.get("name"):
            st.success(f"Resume for **{st.session_state.parsed['name']}** is loaded.")
        elif st.session_state.full_text:
            st.warning("Resume file loaded, but parsing may have errors.")
        else:
            st.info("Please upload a resume to begin.")

    # Main Content Tabs 
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📄 Resume Parsing", 
        "💬 Resume Chatbot (Q&A)", 
        "❓ Interview Prep", 
        "📚 JD Management", 
        "🎯 Batch JD Match"  
    ])
    
    # --- TAB 1: Resume Parsing ---
    with tab1:
         st.header("Resume Parsing")
         if not st.session_state.full_text:
             st.warning("Please upload and parse a resume in the sidebar first.")
             # Early exit is fine here as it's the first tab
             # return

         parsed = st.session_state.parsed
         full_text = st.session_state.full_text

         if "error" in parsed:
             st.error(parsed.get("error", "An unknown error occurred during parsing."))
             # return

         col1, col2 = st.columns(2)
         with col1:
             output_format = st.radio('Output Format', ['json', 'markdown'], key='format_radio_c')
         with col2:
             section = st.selectbox('Select Section to View', section_options, key='section_select_c')


         if st.session_state.full_text:
             if output_format == 'json':
                 output_str = json.dumps(parsed, indent=2)
                 st.text_area("Parsed Output (JSON)", output_str, height=350)
             else:
                 output_str = parse_with_llm(full_text, return_type='markdown')
                 st.markdown("### Parsed Output (Markdown)")
                 st.markdown(output_str)
     
             if st.session_state.excel_data:
                 st.download_button(
                     label="Download Parsed Data (Excel)",
                     data=st.session_state.excel_data,
                     file_name=f"{parsed.get('name', 'candidate').replace(' ', '_')}_parsed_data.xlsx",
                     mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                 )
             
             section_content_str = ""
             if section == "full resume":
                 section_content_str = full_text
             elif section in parsed:
                 section_val = parsed[section]
                 section_content_str = json.dumps(section_val, indent=2) if isinstance(section_val, (list, dict)) else str(section_val)
             else:
                 section_content_str = f"Section '{section}' not found or is empty."

             st.text_area("Selected Section Content", section_content_str, height=200)

    # --- TAB 2: Resume Chatbot (Q&A) ---
    with tab2:
         st.header("Resume Chatbot (Q&A)")
         st.markdown("### Ask any question about the uploaded resume.")
         if not st.session_state.full_text:
             st.warning("Please upload and parse a resume first.")
             # return

         if st.session_state.full_text:
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
         if not st.session_state.parsed or "error" in st.session_state.parsed:
             st.warning("Please upload and successfully parse a resume first.")
             # return
         
         if st.session_state.parsed and "error" not in st.session_state.parsed:
             st.subheader("Generate Interview Questions")
             section_choice = st.selectbox("Select Section", question_section_options, key='iq_section_c')
            
             if st.button("Generate Interview Questions", key='iq_btn_c'):
                 with st.spinner("Generating questions..."):
                     try:
                         raw_questions_response = generate_interview_questions(st.session_state.parsed, section_choice)
                         st.session_state.iq_output = raw_questions_response
                     except Exception as e:
                         st.error(f"Error generating questions: {e}")
                         st.session_state.iq_output = "Error generating questions."

             if st.session_state.get('iq_output'):
                 st.text_area("Generated Interview Questions (by difficulty level)", st.session_state.iq_output, height=400)
             
    # --- TAB 4: JD Management ---
    with tab4:
        st.header("📚 Manage Job Descriptions for Matching")
        st.markdown("JDs added here are saved for your batch matching.")
        
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
                        if not jd_text.startswith("[Error"):
                            # Save to DB
                            jd_data = {"name": f"JD from URL: {name_base}", "content": jd_text, "source": "url"}
                            st.session_state.db.save_jd(jd_data, 'candidate')
                            count += 1
                            
                    # Refresh list from DB
                    st.session_state.candidate_jd_list = st.session_state.db.get_jds('candidate')
                    if count > 0:
                        st.success(f"✅ {count} JD(s) added successfully!")
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
                            
                            # Save to DB
                            jd_data = {"name": name_base, "content": text, "source": "pasted"}
                            st.session_state.db.save_jd(jd_data, 'candidate')

                    # Refresh list from DB
                    st.session_state.candidate_jd_list = st.session_state.db.get_jds('candidate')
                    st.success(f"✅ {len(texts)} JD(s) added successfully!")

        # Upload File
        elif method == "Upload File":
            uploaded_files = st.file_uploader(
                "Upload JD file(s)",
                type=["pdf", "txt", "docx"],
                accept_multiple_files=True if jd_type == "Multiple JD" else False,
                key="jd_file_uploader_candidate"
            )
            if st.button("Add JD(s) from File", key="add_jd_file_btn_candidate"):
                files_to_process = uploaded_files if jd_type == "Multiple JD" and uploaded_files else [uploaded_files]
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
                            # Save to DB
                            jd_data = {"name": file.name, "content": jd_text, "source": "file"}
                            st.session_state.db.save_jd(jd_data, 'candidate')
                            count += 1

                # Refresh list from DB
                st.session_state.candidate_jd_list = st.session_state.db.get_jds('candidate')
                if count > 0:
                    st.success(f"✅ {count} JD(s) added successfully!")
                else:
                    st.error("No valid JD files were uploaded or content extraction failed.")

        # Display Added JDs
        if st.session_state.candidate_jd_list:
            st.markdown("### ✅ Current JDs Added (Persistent in DB):")
            for idx, jd_item in enumerate(st.session_state.candidate_jd_list, 1):
                title = jd_item['name']
                display_title = title.replace("--- Simulated JD for: ", "")
                col_disp, col_del = st.columns([10, 1])
                with col_disp:
                    with st.expander(f"JD {idx}: {display_title} (Added: {jd_item.get('created_at', 'N/A').strftime('%Y-%m-%d')})"):
                        st.text(jd_item['content'])
                with col_del:
                    if st.button("🗑️", key=f"del_jd_candidate_{jd_item['_id']}"):
                        st.session_state.db.db.candidate_jds.delete_one({'_id': ObjectId(jd_item['_id'])})
                        st.session_state.candidate_jd_list = st.session_state.db.get_jds('candidate')
                        st.rerun()
        else:
            st.info("No Job Descriptions added yet.")


    # --- TAB 5: Batch JD Match ---
    with tab5:
        st.header("🎯 Batch JD Match (Results saved to DB)")
        st.markdown("Compare your current resume against all saved job descriptions.")

        if not st.session_state.parsed:
            st.warning("Please **upload and parse your resume** in the sidebar first.")
            return

        if not st.session_state.candidate_jd_list:
            st.error("Please **add Job Descriptions** in the 'JD Management' tab (Tab 4) before running batch analysis.")
            return
            
        if st.button(f"Run Batch Match Against {len(st.session_state.candidate_jd_list)} JDs"):
            
            resume_name = st.session_state.parsed.get('name', 'Uploaded Resume')
            parsed_json = st.session_state.parsed

            with st.spinner(f"Matching {resume_name}'s resume against {len(st.session_state.candidate_jd_list)} JDs..."):
                for jd_item in st.session_state.candidate_jd_list:
                    
                    jd_name = jd_item['name']
                    jd_content = jd_item['content']

                    try:
                        fit_output = evaluate_jd_fit(jd_content, parsed_json)
                        
                        # --- ENHANCED EXTRACTION LOGIC (FIXED) ---
                        # Robust Regexes to handle single-line LLM output
                        overall_score_match = re.search(r'Overall Fit Score:\s*(\d+)\s*/10', fit_output, re.IGNORECASE)
                        section_analysis_match = re.search(
                             r'--- Section Match Analysis ---\s*(.*?)\s*Strengths/Matches:', 
                             fit_output, re.DOTALL
                        )

                        skills_percent = 'N/A'
                        experience_percent = 'N/A'
                        education_percent = 'N/A'
                        
                        if section_analysis_match:
                            section_text = section_analysis_match.group(1)
                            
                            skills_match = re.search(r'Skills Match:\s*(\d+)%', section_text, re.IGNORECASE)
                            experience_match = re.search(r'Experience Match:\s*(\d+)%', section_text, re.IGNORECASE)
                            education_match = re.search(r'Education Match:\s*(\d+)%', section_text, re.IGNORECASE)
                            
                            if skills_match: skills_percent = skills_match.group(1)
                            if experience_match: experience_percent = experience_match.group(1)
                            if education_match: education_percent = education_match.group(1)
                        
                        overall_score = overall_score_match.group(1) if overall_score_match else 'N/A'
                        # --- END ENHANCED EXTRACTION LOGIC (FIXED) ---

                        result_item = {
                            "jd_name": jd_name,
                            "overall_score": overall_score,
                            "skills_percent": skills_percent,
                            "experience_percent": experience_percent, 
                            "education_percent": education_percent,   
                            "full_analysis": fit_output,
                            "resume_name": resume_name, 
                        }
                        
                        # Save results to DB
                        st.session_state.db.save_match_result(result_item, 'candidate')
                        
                    except Exception as e:
                        error_item = {
                            "jd_name": jd_name,
                            "overall_score": "Error",
                            "skills_percent": "Error",
                            "experience_percent": "Error", 
                            "education_percent": "Error",   
                            "full_analysis": f"Error running analysis for {jd_name}: {e}\n{traceback.format_exc()}",
                            "resume_name": resume_name
                        }
                        st.session_state.db.save_match_result(error_item, 'candidate')
                
                # Refresh match results from DB
                st.session_state.candidate_match_results = st.session_state.db.get_match_results('candidate')
                st.success("Batch analysis complete and results saved to DB!")


        # 3. Display Results
        if st.session_state.get('candidate_match_results'):
            st.markdown("#### Recent Match Results for Your Resume (Loaded from DB)")
            results_df = st.session_state.candidate_match_results
            
            # Create a simple table/summary of results
            display_data = []
            for item in results_df:
                display_data.append({
                    "Job Description": item["jd_name"].replace("--- Simulated JD for: ", ""),
                    "Fit Score (out of 10)": item["overall_score"],
                    "Skills (%)": item.get("skills_percent", "N/A"),
                    "Experience (%)": item.get("experience_percent", "N/A"), 
                    "Education (%)": item.get("education_percent", "N/A"),   
                    "Time": item.get('created_at_str', 'N/A')
                })

            st.dataframe(display_data, use_container_width=True)

            # Display detailed analysis in expanders
            st.markdown("##### Detailed Reports")
            for item in results_df:
                header_text = f"Report for **{item['jd_name'].replace('--- Simulated JD for: ', '')}** (Score: **{item['overall_score']}/10** | S: **{item.get('skills_percent', 'N/A')}%** | E: **{item.get('experience_percent', 'N/A')}%** | Edu: **{item.get('education_percent', 'N/A')}%**) @ {item.get('created_at_str', 'N/A')}"
                with st.expander(header_text):
                    st.markdown(item['full_analysis'])


def hiring_dashboard():
    st.header("🏢 Hiring Company Dashboard")
    st.write("Manage job postings and view candidate applications. (Placeholder for future features)")
    st.sidebar.button("⬅️ Go Back to Role Selection", on_click=go_to, args=("role_selection",))

# -------------------------
# Main App Initialization
# -------------------------
def main():
    st.set_page_config(layout="wide", page_title="PragyanAI Job Portal")

    # --- Session State Initialization ---
    if 'page' not in st.session_state:
        st.session_state.page = "login"
        
    # NEW: Initialize Database Connection
    # This must run before any dashboard attempts to access st.session_state.db
    if 'db' not in st.session_state:
        st.session_state.db = DatabaseManager(MONGODB_URI)
            
    # Initialize session state for AI features
    if 'parsed' not in st.session_state:
        st.session_state.parsed = {}
        st.session_state.full_text = ""
        st.session_state.excel_data = None
        st.session_state.qa_answer = ""
        st.session_state.iq_output = ""
        st.session_state.jd_fit_output = ""
        
        # Reset lists if a hard restart occurs, lists will be loaded from DB in respective dashboards
        st.session_state.admin_jd_list = []
        st.session_state.resumes_to_analyze = []
        st.session_state.admin_match_results = []
        st.session_state.candidate_jd_list = []
        st.session_state.candidate_match_results = []


    # --- Page Routing ---
    if st.session_state.page == "login":
        login_page()
    elif st.session_state.page == "signup":
        signup_page()
    elif st.session_state.page == "role_selection":
        role_selection_page()
    elif st.session_state.page == "admin_dashboard":
        admin_dashboard()
    elif st.session_state.page == "candidate_dashboard":
        candidate_dashboard()
    elif st.session_state.page == "hiring_dashboard":
        hiring_dashboard()

if __name__ == '__main__':
    main()
