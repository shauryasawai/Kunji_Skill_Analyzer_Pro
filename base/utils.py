import json
import re
from openai import OpenAI
import pandas as pd
from pathlib import Path
from django.conf import settings
from PyPDF2 import PdfReader
from docx import Document

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

3. "role_category": The most suitable role category (e.g., HR, Marketing, IT, Finance, Sales, Operations, etc.)

4. "experience_level": one of ["Entry Level", "Mid Level", "Senior Level", "Executive Level"]

5. "key_responsibilities": List 5-7 main responsibilities mentioned in the JD

6. "qualifications": Educational requirements and certifications

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

def save_to_excel(jd_data):
    '''Save job description data to Excel database'''
    try:
        excel_path = settings.EXCEL_DATABASE_PATH
        
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
        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
        
        # Save to Excel
        df_combined.to_excel(excel_path, index=False, engine='openpyxl')
        print(f"✅ Successfully saved to Excel: {excel_path}")
        
    except Exception as e:
        print(f"❌ Error saving to Excel: {e}")