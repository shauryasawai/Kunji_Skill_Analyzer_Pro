import json
import re
from openai import OpenAI
import pandas as pd
from pathlib import Path
from django.conf import settings
from PyPDF2 import PdfReader
from docx import Document

def generate_linkedin_search_strings(skills, role_title, experience_level):
    '''Generate optimized LinkedIn Recruiter boolean search strings'''
    
    # Clean and prepare skills
    top_skills = skills[:15] if len(skills) > 15 else skills
    
    # Create different search string variations
    searches = {}
    
    # 1. Basic Boolean Search (AND)
    basic_and = " AND ".join([f'"{skill}"' for skill in top_skills[:8]])
    searches['basic_and'] = basic_and
    
    # 2. Flexible Boolean Search (OR for similar skills)
    if len(top_skills) >= 3:
        part1 = " OR ".join([f'"{skill}"' for skill in top_skills[:3]])
        part2 = " OR ".join([f'"{skill}"' for skill in top_skills[3:6]])
        flexible = f'({part1}) AND ({part2})' if part2 else f'({part1})'
        searches['flexible'] = flexible
    
    # 3. Title + Key Skills
    skills_part = " AND ".join([f'"{skill}"' for skill in top_skills[:5]])
    title_search = f'(title:"{role_title}") AND ({skills_part})'
    searches['with_title'] = title_search
    
    # 4. Simple comma-separated for LinkedIn Skills filter
    skills_filter = ", ".join(top_skills[:10])
    searches['skills_filter'] = skills_filter
    
    # 5. X-Ray Search (for Google/LinkedIn combination)
    xray_skills = " ".join([f'"{skill}"' for skill in top_skills[:6]])
    xray_search = f'site:linkedin.com/in/ "{role_title}" {xray_skills}'
    searches['xray'] = xray_search
    
    return searches

def extract_text_from_file(file_path):
    '''Extract text from TXT, PDF, or DOCX files'''
    ext = Path(file_path).suffix.lower()
    
    try:
        if ext == '.txt':
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        
        elif ext == '.pdf':
            reader = PdfReader(file_path)
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"
            return text
        
        elif ext == '.docx':
            doc = Document(file_path)
            return '\n'.join([para.text for para in doc.paragraphs])
    
    except Exception as e:
        print(f"Error extracting text from {file_path}: {e}")
        return ""
    
    return ""

def extract_skills_from_jd(jd_text, domain_hint=""):
    '''Extract ALL skills comprehensively from job description using OpenAI API'''
    try:
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
    except Exception as e:
        print(f"Error initializing OpenAI client: {e}")
        return get_default_error_response()
    
    domain_context = f"The job is in the {domain_hint} domain." if domain_hint else ""
    
    prompt = f'''
You are an expert HR recruitment assistant AI. Carefully analyze the following Job Description and extract EVERY skill, technology, tool, qualification, and competency mentioned.

Return a structured JSON with:

1. "all_skills": A comprehensive list of ALL skills mentioned in the JD including:
   - Technical skills (programming languages, tools, frameworks, technologies)
   - Functional skills (domain-specific abilities)
   - Software/Tools (any applications, platforms, or systems)
   - Methodologies (Agile, Scrum, Six Sigma, etc.)
   - Certifications or qualifications mentioned
   - Domain knowledge areas
   - Soft skills (communication, leadership, teamwork, etc.)
   
   Extract 15-30 skills. Be thorough and don't miss anything mentioned in the JD.

2. "skill_categories": Organize the skills into categories like:
   {{"Technical": [...], "Tools": [...], "Soft Skills": [...], "Domain Knowledge": [...], "Certifications": [...]}}
   
3. "linkedin_optimized_skills": A list of 8-15 MOST IMPORTANT skills optimized for LinkedIn Recruiter search. 
   - Focus on searchable, industry-standard terms
   - Remove generic terms like "communication" or "teamwork"
   - Prioritize: specific technologies, tools, certifications, frameworks
   - Use exact names as they appear on LinkedIn (e.g., "JavaScript" not "JS", "Amazon Web Services (AWS)" not just "AWS")

4. "role_category": The most suitable role category (e.g., HR, Marketing, IT, Finance, Sales, Operations, etc.)

5. "experience_level": one of ["Entry Level", "Mid Level", "Senior Level", "Executive Level"]

6. "key_responsibilities": List 5-7 main responsibilities mentioned in the JD

7. "qualifications": Educational requirements and certifications

{domain_context}

Be extremely thorough. If someone reads only your extracted skills, they should fully understand what this job requires.

Return ONLY valid JSON, no code block, no markdown, no explanation.

JD:
{jd_text[:4000]}
'''

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an AI expert at extracting comprehensive skill requirements from job descriptions. Extract EVERY skill mentioned. Return only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=2000
        )

        content = response.choices[0].message.content.strip()
        
        # Clean content in case it includes markdown ```json``` wrapping
        cleaned = re.sub(r"^```json\s*|\s*```$", "", content, flags=re.MULTILINE).strip()

        try:
            result = json.loads(cleaned)
            
            # Validate and normalize expected keys
            
            if "linkedin_optimized_skills" not in result:
                result["linkedin_optimized_skills"] = result.get("all_skills", [])[:10]
                
            if "all_skills" not in result:
                result["all_skills"] = []
            
            if "skill_categories" not in result:
                result["skill_categories"] = {}
                
            if "role_category" not in result:
                result["role_category"] = "Unknown"
                
            if "experience_level" not in result:
                result["experience_level"] = "Unknown"
                
            if "key_responsibilities" not in result:
                result["key_responsibilities"] = []
                
            if "qualifications" not in result:
                result["qualifications"] = []
            
            return result

        except json.JSONDecodeError as je:
            print(f"⚠️ JSON Decode Error: {je}")
            print(f"⚠️ Raw LLM Output: {content}")
            return get_default_error_response()

    except Exception as e:
        print(f"❌ Error calling OpenAI API: {e}")
        return get_default_error_response()

def get_default_error_response():
    '''Return default response when API fails'''
    return {
        "all_skills": ["Error extracting skills - please try again"],
        "skill_categories": {},
        "role_category": "Unknown",
        "experience_level": "Unknown",
        "key_responsibilities": [],
        "qualifications": []
    }

def load_skills_map():
    '''Load skills mapping from JSON file or return default'''
    try:
        if settings.SKILLS_MAP_PATH.exists():
            with open(settings.SKILLS_MAP_PATH, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:
                    print("⚠️ Skills map file is empty, using default")
                    return get_default_skills_map()
                return json.loads(content)
        else:
            print("⚠️ Skills map file not found, using default")
            return get_default_skills_map()
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"⚠️ Error loading skills map: {e}, using default")
        return get_default_skills_map()

def get_default_skills_map():
    '''Return comprehensive default skills mapping'''
    return {
        "Docker": ["Kubernetes", "AWS ECS", "Containerization", "Docker Compose", "CI/CD"],
        "Python": ["Django", "Flask", "FastAPI", "NumPy", "Pandas", "Data Science"],
        "JavaScript": ["React", "Node.js", "TypeScript", "Vue.js", "Angular"],
        "Recruitment": ["Talent Acquisition", "Interviewing", "Onboarding", "ATS", "Sourcing"],
        "Marketing": ["SEO", "Content Strategy", "Campaign Management", "Google Analytics", "Social Media"],
        "Finance": ["Budgeting", "Forecasting", "Financial Modelling", "Excel", "Accounting"],
        "SQL": ["Database Design", "PostgreSQL", "MySQL", "Data Analysis", "Query Optimization"],
        "Project Management": ["Agile", "Scrum", "JIRA", "Stakeholder Management", "Risk Management"],
        "Sales": ["CRM", "Lead Generation", "Negotiation", "Account Management", "Pipeline Management"],
        "HR": ["Employee Relations", "Performance Management", "HRMS", "Compliance", "Training"],
        "Java": ["Spring Boot", "Hibernate", "Maven", "JUnit", "Microservices"],
        "AWS": ["EC2", "S3", "Lambda", "CloudFormation", "RDS"],
        "Data Analysis": ["Excel", "Tableau", "Power BI", "Statistics", "SQL"],
        "Content Writing": ["Copywriting", "SEO Writing", "Editing", "Blogging", "Content Strategy"],
        "Customer Service": ["Communication", "Problem Solving", "CRM", "Ticketing Systems", "Customer Support"],
        "Machine Learning": ["TensorFlow", "PyTorch", "Scikit-learn", "Deep Learning", "NLP"],
        "DevOps": ["Jenkins", "Docker", "Kubernetes", "Terraform", "Monitoring"],
        "UI/UX": ["Figma", "Adobe XD", "Wireframing", "Prototyping", "User Research"],
        "Product Management": ["Roadmap Planning", "User Stories", "Product Strategy", "Analytics", "Stakeholder Management"]
    }

def expand_skills_with_map(primary_skills, secondary_skills):
    '''Expand secondary skills based on primary skills using skills map'''
    skills_map = load_skills_map()
    expanded_secondary = set(secondary_skills) if secondary_skills else set()
    
    for skill in primary_skills:
        # Check exact match
        if skill in skills_map:
            expanded_secondary.update(skills_map[skill])
        # Check case-insensitive match
        else:
            for map_skill, related in skills_map.items():
                if skill.lower() == map_skill.lower():
                    expanded_secondary.update(related)
                    break
    
    return list(expanded_secondary)

def fetch_google_sheet_data(sheet_id, credentials_path=None):
    '''
    Fetch candidate data from Google Sheets
    
    Args:
        sheet_id: Google Sheet ID
        credentials_path: Path to service account JSON (optional, uses settings default)
    
    Returns:
        DataFrame with candidate data
    '''
    import gspread
    from google.oauth2.service_account import Credentials
    
    try:
        # Setup credentials
        if credentials_path is None:
            credentials_path = settings.GOOGLE_SHEETS_CREDENTIALS
        
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets.readonly',
            'https://www.googleapis.com/auth/drive.readonly'
        ]
        
        creds = Credentials.from_service_account_file(credentials_path, scopes=scopes)
        client = gspread.authorize(creds)
        
        # Open spreadsheet and get first sheet
        spreadsheet = client.open_by_key(sheet_id)
        worksheet = spreadsheet.sheet1  # Get first sheet
        
        # Get all values and convert to DataFrame
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        
        print(f"✅ Successfully fetched {len(df)} rows from Google Sheet")
        return df
    
    except Exception as e:
        print(f"❌ Error fetching Google Sheet: {e}")
        return pd.DataFrame()


def match_candidates_from_google_sheet(sheet_id, required_skills, min_match_percentage=50):
    '''
    Match candidates from Google Sheets with job requirements
    
    Args:
        sheet_id: Google Sheet ID
        required_skills: List of skills from JD
        min_match_percentage: Minimum percentage of skills that must match
    
    Returns:
        List of matched candidates with match scores
    '''
    try:
        # Fetch data from Google Sheets
        df = fetch_google_sheet_data(sheet_id)
        
        if df.empty:
            print("No data found in Google Sheet")
            return []
        
        # Normalize column names
        df.columns = df.columns.str.strip()
        
        # Check if Skills column exists
        if 'Skills' not in df.columns:
            print("Error: 'Skills' column not found in Google Sheet")
            print(f"Available columns: {df.columns.tolist()}")
            return []
        
        matched_candidates = []
        
        # Normalize required skills for comparison
        required_skills_lower = [skill.lower().strip() for skill in required_skills]
        
        for idx, row in df.iterrows():
            candidate_skills_str = str(row.get('Skills', ''))
            
            if not candidate_skills_str or candidate_skills_str == 'nan':
                continue
            
            # Parse candidate skills (assume comma-separated)
            candidate_skills = [s.lower().strip() for s in candidate_skills_str.split(',')]
            
            # Calculate skill matches
            matched_skills = []
            for req_skill in required_skills_lower:
                for cand_skill in candidate_skills:
                    # Check for exact match or partial match
                    if req_skill in cand_skill or cand_skill in req_skill:
                        matched_skills.append(req_skill)
                        break
            
            # Calculate match percentage
            match_percentage = (len(matched_skills) / len(required_skills_lower)) * 100 if required_skills_lower else 0
            
            # Only include candidates above threshold
            if match_percentage >= min_match_percentage:
                candidate_data = {
                    'name': row.get('Candidate Name', 'N/A'),
                    'email': row.get('Email', 'N/A'),
                    'contact': row.get('Contact', 'N/A'),
                    'location': row.get('Location', 'N/A'),
                    'current_company': row.get('Current Company', 'N/A'),
                    'designation': row.get('Designation', 'N/A'),
                    'experience': row.get('Experience', 'N/A'),
                    'linkedin': row.get('LinkedIn', 'N/A'),
                    'qualification': row.get('Qualification', 'N/A'),
                    'skills': row.get('Skills', 'N/A'),
                    'cv_link': row.get('CV Link', 'N/A'),
                    'status': row.get('Status', 'N/A'),
                    'matched_skills': matched_skills,
                    'match_percentage': round(match_percentage, 1),
                    'matched_skills_count': len(matched_skills),
                    'total_required_skills': len(required_skills_lower)
                }
                matched_candidates.append(candidate_data)
        
        # Sort by match percentage (highest first)
        matched_candidates.sort(key=lambda x: x['match_percentage'], reverse=True)
        
        return matched_candidates
    
    except Exception as e:
        print(f"Error matching candidates from Google Sheet: {e}")
        return []
    
import pandas as pd
from pathlib import Path
from django.conf import settings  # only if running inside Django

def match_candidates_with_jd(candidate_excel_path, required_skills, min_match_percentage=50):
    '''
    Match candidates from Excel database with job requirements
    
    Args:
        candidate_excel_path: Path to candidate Excel file
        required_skills: List of skills from JD
        min_match_percentage: Minimum percentage of skills that must match (default 50%)
    
    Returns:
        List of matched candidates with match scores
    '''
    try:
        # Read candidate database
        df = pd.read_excel(candidate_excel_path)
        
        # Normalize column names (remove spaces, lowercase)
        df.columns = df.columns.str.strip()
        
        # Check if Skills column exists
        if 'Skills' not in df.columns:
            print("❌ Error: 'Skills' column not found in Excel")
            return []
        
        matched_candidates = []
        
        # Normalize required skills for comparison
        required_skills_lower = [skill.lower().strip() for skill in required_skills]
        
        for _, row in df.iterrows():
            candidate_skills_str = str(row.get('Skills', ''))
            
            if not candidate_skills_str or candidate_skills_str.lower() == 'nan':
                continue
            
            # Parse candidate skills (assume comma-separated)
            candidate_skills = [s.lower().strip() for s in candidate_skills_str.split(',')]
            
            # Calculate skill matches
            matched_skills = []
            for req_skill in required_skills_lower:
                for cand_skill in candidate_skills:
                    # Check for exact or partial match
                    if req_skill in cand_skill or cand_skill in req_skill:
                        matched_skills.append(req_skill)
                        break
            
            # Calculate match percentage
            match_percentage = (len(matched_skills) / len(required_skills_lower)) * 100 if required_skills_lower else 0
            
            # Only include candidates above threshold
            if match_percentage >= min_match_percentage:
                candidate_data = {
                    'name': row.get('Candidate Name', 'N/A'),
                    'email': row.get('Email of Candidate', 'N/A'),
                    'contact': row.get('Contact Number', 'N/A'),
                    'location': row.get('Candidate Location', 'N/A'),
                    'current_company': row.get('Current Company', 'N/A'),
                    'designation': row.get('Current Designation', 'N/A'),
                    'experience': row.get('Experience', 'N/A'),
                    'linkedin': row.get('Linkedin URL', 'N/A'),
                    'qualification': row.get('Qualification', 'N/A'),
                    'skills': row.get('Skills', 'N/A'),
                    'cv_link': row.get('Candidate CV Path', 'N/A'),
                    'status': row.get('Candidate Status', 'N/A'),
                    'matched_skills': matched_skills,
                    'match_percentage': round(match_percentage, 1),
                    'matched_skills_count': len(matched_skills),
                    'total_required_skills': len(required_skills_lower)
                }
                matched_candidates.append(candidate_data)
        
        # Sort by match percentage (highest first)
        matched_candidates.sort(key=lambda x: x['match_percentage'], reverse=True)
        
        return matched_candidates
    
    except Exception as e:
        print(f"❌ Error matching candidates: {e}")
        return []


def export_matched_candidates(matched_candidates, output_path):
    '''
    Export matched candidates to Excel
    '''
    try:
        df = pd.DataFrame(matched_candidates)
        
        # Reorder columns for better readability
        column_order = [
            'match_percentage', 'matched_skills_count', 'total_required_skills',
            'name', 'email', 'contact', 'designation', 'current_company',
            'experience', 'location', 'qualification', 'linkedin',
            'skills', 'matched_skills', 'cv_link', 'status'
        ]
        
        # Only include columns that exist
        column_order = [col for col in column_order if col in df.columns]
        df = df[column_order]
        
        # Export to Excel
        df.to_excel(output_path, index=False, engine='openpyxl')
        print(f"✅ Matched candidates exported to: {output_path}")
        return True
    
    except Exception as e:
        print(f"❌ Error exporting matched candidates: {e}")
        return False


def save_jd_to_excel(jd_data):
    '''
    Save job description data to Excel database
    '''
    try:
        excel_path = Path(settings.EXCEL_DATABASE_PATH)
        data_dir = excel_path.parent
        
        df_new = pd.DataFrame([jd_data])
        
        if excel_path.exists():
            try:
                df_existing = pd.read_excel(excel_path)
                df_combined = pd.concat([df_existing, df_new], ignore_index=True)
            except Exception as e:
                print(f"⚠️ Error reading existing Excel file: {e}, creating new one")
                df_combined = df_new
        else:
            df_combined = df_new
        
        # Ensure data directory exists
        data_dir.mkdir(parents=True, exist_ok=True)
        
        # Save to Excel
        df_combined.to_excel(excel_path, index=False, engine='openpyxl')
        print(f"✅ Successfully saved JD data to Excel: {excel_path}")
        
    except Exception as e:
        print(f"❌ Error saving JD data to Excel: {e}")

        
        
        
