import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response
from supabase import create_client, Client
from dotenv import load_dotenv
import io

# Load environment variables
load_dotenv()

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = os.getenv("FLASK_SECRET_KEY", "lundayang_marians_default_secret_key_12345")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

# Initialize Supabase client
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print("Error initializing Supabase client:", e)

# Hardcoded High-Fidelity Mock Database for Fallbacks
MOCK_PAPERS = [
    {
        "id": "mock-paper-stem-1",
        "title": "KALAT MO, SAGOT KO: THE ACCEPTABILITY OF THE PROTOTYPE WASTE SEGREGATOR MACHINE IN SANTA MARIA, LAGUNA",
        "abstract": "A prototype waste segregator machine designed to automatically classify garbage into biodegradable, non-biodegradable, and recyclable materials using inductive, capacitive, and photoelectric sensors controlled by an Arduino microcontroller. The acceptability testing was conducted within the local barangays of Santa Maria, Laguna to evaluate its efficacy, reliability, and social impact.",
        "strand": "STEM",
        "academic_year": "2023-2024",
        "research_type": "Experimental / Quantitative",
        "subject_area": "Applied Engineering & Electronics",
        "authors": [
            "Gabrielle A. Dimatatac",
            "Bridgette S. Panaligan",
            "Mark Andrew Y. Montales",
            "Fiona Sheryn A. Hernandez",
            "Kristel Anne Nicole L. Jaen",
            "Godwel Ivan D. Razon",
            "Fatima Victoria I. Valentino"
        ],
        "adviser": "Ms. Maureen L. Cruz",
        "awards": "Best in Research (STEM)",
        "keywords": ["waste segregator", "arduino", "automation", "recycling"],
        "pdf_path": "mock/waste_segregator.pdf"
    },
    {
        "id": "mock-paper-humss-1",
        "title": "PAWSITIVE LIFESTYLE: THE EFFECTS OF PETS ON TEENAGERS' WELL-BEING AS PERCEIVED BY THEIR BIOLOGICAL SEX",
        "abstract": "This study examines how pet ownership impacts the mental health and emotional well-being of teenagers, comparative between biological sexes. Utilizing a descriptive research design, data was gathered from junior and senior high school students to analyze gender-based differences in coping strategies and companion animal attachment scales.",
        "strand": "HUMSS",
        "academic_year": "2024-2025",
        "research_type": "Descriptive / Quantitative",
        "subject_area": "Social Psychology & Adolescent Well-being",
        "authors": ["Aiah Arceta", "Mikha Lim", "Stacey Sevilleja"],
        "adviser": "Mr. Jose R. Santos",
        "awards": "Best in Research (HUMSS)",
        "keywords": ["pets", "teenagers", "biological sex", "mental health"],
        "pdf_path": "mock/pawsitive_lifestyle.pdf"
    },
    {
        "id": "mock-paper-stem-2",
        "title": "ECO-BRICKS: SOLID WASTE MANAGEMENT STRATEGY IN BARANGAY POBLACION",
        "abstract": "The research explores the production of eco-bricks from shredded plastics as an alternative building material, validating its load-bearing capacity and cost-effectiveness. The physical structural strength of plastic-stuffed bottles was tested against traditional hollow blocks to assess durability and community safety factors.",
        "strand": "STEM",
        "academic_year": "2024-2025",
        "research_type": "Experimental",
        "subject_area": "Environmental Science",
        "authors": ["Xian Yvan V. Evangelio", "Carlene Jane P. Dela Cruz"],
        "adviser": "Mrs. Elena M. Reyes",
        "awards": "Outstanding STEM Project",
        "keywords": ["eco-bricks", "plastic waste", "structural engineering"],
        "pdf_path": "mock/eco_bricks.pdf"
    },
    {
        "id": "mock-paper-abm-1",
        "title": "FINANCIAL LITERACY AND SPENDING HABITS OF SENIOR HIGH SCHOOL STUDENTS",
        "abstract": "This descriptive research evaluates the correlation between financial literacy programs and personal budgeting behaviors of SHS students. It outlines key financial stressors, savings triggers, and impulse spending patterns in order to draft financial education curricula recommendations.",
        "strand": "ABM",
        "academic_year": "2024-2025",
        "research_type": "Descriptive Correlational",
        "subject_area": "Financial Management",
        "authors": ["Jean Mary E. De Torres", "Jhandy Faye B. Consignado"],
        "adviser": "Mr. Allan B. Perez",
        "awards": "Best Business Research",
        "keywords": ["financial literacy", "budgeting", "spending habits", "savings"],
        "pdf_path": "mock/financial_literacy.pdf"
    }
]

# Helper to verify if user is logged in
def is_logged_in():
    return 'user' in session

# Decorator to restrict pages to logged-in users
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_logged_in():
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Decorator to restrict pages to admin users
def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_logged_in():
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

# ----------------- AUTHENTICATION -----------------

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if is_logged_in():
        return redirect(url_for('home'))
    
    error = None
    if request.method == 'POST':
        student_id = request.form.get('student_id', '').strip()
        name = request.form.get('name', '').strip()
        grade_section = request.form.get('grade_section', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # Derive email and roles
        email = f"{student_id}@smapi.edu"
        role = "student"

        if not student_id or not name or not grade_section or not password or not confirm_password:
            error = "All fields are required."
        elif password != confirm_password:
            error = "Passwords do not match."
        elif len(password) < 6:
            error = "Password must be at least 6 characters."
        else:
            try:
                # Sign up in Supabase if client is configured, otherwise simulate successful signup
                if supabase:
                    auth_res = supabase.auth.sign_up({
                        "email": email,
                        "password": password
                    })
                    if auth_res and auth_res.user:
                        supabase.table("profiles").insert({
                            "id": auth_res.user.id,
                            "student_id": student_id,
                            "name": name,
                            "grade_section": grade_section,
                            "email": email,
                            "role": role
                        }).execute()
                return redirect(url_for('login', msg="Account created successfully! Please log in."))
            except Exception as e:
                error = f"Error during sign up: {str(e)}"

    return render_template('signup.html', error=error)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if is_logged_in():
        return redirect(url_for('home'))
    
    error = None
    msg = request.args.get('msg')
    
    if request.method == 'POST':
        student_id = request.form.get('student_id', '').strip()
        password = request.form.get('password', '')

        if not student_id or not password:
            error = "Student ID and Password are required."
        else:
            # Fallback for development/demonstration using mock admin details
            if student_id == "0966789529" and password == "password":
                session['user'] = {
                    'id': "demo-user-aiah",
                    'email': "biniaiah@gmail.com",
                    'student_id': "0966789529"
                }
                session['access_token'] = "demo-token"
                session['role'] = "admin"
                return redirect(url_for('home'))
            
            try:
                if supabase:
                    profile_res = supabase.table("profiles").select("email, role").eq("student_id", student_id).execute()
                    if not profile_res.data:
                        error = "Invalid Student ID."
                    else:
                        email = profile_res.data[0]['email']
                        role = profile_res.data[0]['role']
                        
                        auth_res = supabase.auth.sign_in_with_password({
                            "email": email,
                            "password": password
                        })
                        
                        if auth_res and auth_res.session:
                            session['user'] = {
                                'id': auth_res.user.id,
                                'email': auth_res.user.email,
                                'student_id': student_id
                            }
                            session['access_token'] = auth_res.session.access_token
                            session['role'] = role
                            return redirect(url_for('home'))
                        else:
                            error = "Incorrect password."
                else:
                    error = "Supabase client not connected. Use '0966789529' and 'password' for demo login."
            except Exception as e:
                error = f"Login failed: {str(e)}"
                
    return render_template('login.html', error=error, msg=msg)

@app.route('/logout')
def logout():
    session.clear()
    if supabase:
        try:
            supabase.auth.sign_out()
        except:
            pass
    return redirect(url_for('login'))

@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    error = None
    success = None
    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not password or not confirm_password:
            error = "All fields are required."
        elif password != confirm_password:
            error = "Passwords do not match."
        elif len(password) < 6:
            error = "Password must be at least 6 characters."
        else:
            try:
                if supabase:
                    supabase.auth.update_user({"password": password})
                    success = "Password updated successfully!"
                else:
                    success = "Demo Password updated successfully!"
            except Exception as e:
                error = f"Failed to update password: {str(e)}"
                
    return render_template('change_password.html', error=error, success=success)

# ----------------- APP PAGES -----------------

@app.route('/')
@login_required
def home():
    recent_papers = MOCK_PAPERS
    best_in_research = [MOCK_PAPERS[1], MOCK_PAPERS[2], MOCK_PAPERS[3], MOCK_PAPERS[0]] # matching mockup list of rows
    
    if supabase:
        try:
            papers_res = supabase.table("research_papers").select("*").execute()
            if papers_res.data:
                recent_papers = papers_res.data
                
            best_res = supabase.table("research_papers").select("*").not_.is_("awards", "null").not_.eq("awards", "").execute()
            if best_res.data:
                best_in_research = best_res.data
        except Exception as e:
            print("DB read failed, running with fallbacks:", e)
            
    return render_template('home.html', recent_papers=recent_papers, best_in_research=best_in_research)

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    error = None
    success = None
    user_id = session['user']['id']
    student_id = session['user']['student_id']
    
    profile_data = {
        "id": user_id,
        "student_id": student_id,
        "name": "Aiah Arceta",
        "grade_section": "12- SJP II",
        "email": session['user']['email'],
        "role": session.get('role', 'student')
    }
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        grade_section = request.form.get('grade_section', '').strip()
        email = request.form.get('email', '').strip()
        
        if not name or not grade_section or not email:
            error = "All fields are required."
        else:
            profile_data["name"] = name
            profile_data["grade_section"] = grade_section
            profile_data["email"] = email
            session['user']['email'] = email
            
            if supabase and not user_id.startswith("demo-"):
                try:
                    supabase.table("profiles").update({
                        "name": name,
                        "grade_section": grade_section,
                        "email": email
                    }).eq("id", user_id).execute()
                    success = "Profile updated successfully!"
                except Exception as e:
                    error = f"Error updating profile: {str(e)}"
            else:
                success = "Demo Profile updated successfully!"
                
            # Save uploaded avatar image
            avatar_file = request.files.get('avatar')
            if avatar_file and avatar_file.filename:
                ext = os.path.splitext(avatar_file.filename)[1].lower()
                if ext in ['.jpg', '.jpeg', '.png', '.gif']:
                    try:
                        static_images_path = os.path.join(app.root_path, 'static', 'images')
                        os.makedirs(static_images_path, exist_ok=True)
                        save_path = os.path.join(static_images_path, 'aiah.png')
                        avatar_file.save(save_path)
                        success = "Profile and avatar photo updated successfully!"
                    except Exception as e:
                        print("Error saving uploaded avatar:", e)
                        error = f"Error saving photo: {str(e)}"
                
    if supabase and not user_id.startswith("demo-"):
        try:
            res = supabase.table("profiles").select("*").eq("id", user_id).execute()
            if res.data:
                profile_data = res.data[0]
        except Exception as e:
            print("DB profile load error:", e)
        
    return render_template('profile.html', profile=profile_data, error=error, success=success)

@app.route('/bookmarks')
@login_required
def bookmarks():
    # Load bookmarks from session mock or database
    bookmarked_papers = [MOCK_PAPERS[1]] # default mock bookmark
    
    if supabase and not session['user']['id'].startswith("demo-"):
        try:
            res = supabase.table("bookmarks").select("research_papers(*)").eq("user_id", session['user']['id']).execute()
            if res.data:
                bookmarked_papers = [b['research_papers'] for b in res.data if b.get('research_papers')]
        except Exception as e:
            print("DB bookmarks load error:", e)
            
    return render_template('bookmarks.html', papers=bookmarked_papers)

@app.route('/bookmark/toggle', methods=['POST'])
@login_required
def toggle_bookmark():
    paper_id = request.form.get('paper_id')
    if not paper_id:
        return jsonify({"success": False, "error": "Paper ID required."}), 400
        
    if supabase and not session['user']['id'].startswith("demo-"):
        try:
            user_id = session['user']['id']
            check_res = supabase.table("bookmarks").select("id").eq("user_id", user_id).eq("paper_id", paper_id).execute()
            if check_res.data:
                supabase.table("bookmarks").delete().eq("user_id", user_id).eq("paper_id", paper_id).execute()
                return jsonify({"success": True, "bookmarked": False})
            else:
                supabase.table("bookmarks").insert({"user_id": user_id, "paper_id": paper_id}).execute()
                return jsonify({"success": True, "bookmarked": True})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
    else:
        # Simulate local session bookmark toggle
        return jsonify({"success": True, "bookmarked": True})

@app.route('/strand/<strand_name>')
@login_required
def strand(strand_name):
    strand_name = strand_name.upper()
    if strand_name not in ('HUMSS', 'ABM', 'STEM'):
        return redirect(url_for('home'))
        
    search_query = request.args.get('q', '').strip()
    year_filter = request.args.get('year', '').strip()
    
    # Load papers from mock
    papers = [p for p in MOCK_PAPERS if p['strand'] == strand_name]
    
    if supabase:
        try:
            query = supabase.table("research_papers").select("*").eq("strand", strand_name)
            if year_filter:
                query = query.eq("academic_year", year_filter)
            res = query.execute()
            if res.data:
                papers = res.data
        except Exception as e:
            print("DB search error:", e)
            
    # Apply search filter
    if search_query:
        q = search_query.lower()
        filtered = []
        for p in papers:
            authors_str = " ".join(p.get('authors', [])).lower()
            keywords_str = " ".join(p.get('keywords', [])).lower()
            if (q in p.get('title', '').lower() or
                q in p.get('abstract', '').lower() or
                q in p.get('adviser', '').lower() or
                q in p.get('subject_area', '').lower() or
                q in authors_str or
                q in keywords_str):
                filtered.append(p)
        papers = filtered
        
    academic_years = sorted(list(set(p['academic_year'] for p in MOCK_PAPERS if p['strand'] == strand_name)), reverse=True)
    
    return render_template('strand.html', strand=strand_name, papers=papers, search_query=search_query, selected_year=year_filter, academic_years=academic_years)

@app.route('/paper/<paper_id>')
@login_required
def paper_detail(paper_id):
    paper = None
    # Find in mock
    for p in MOCK_PAPERS:
        if p['id'] == paper_id:
            paper = p
            break
            
    is_bookmarked = (paper_id == "mock-paper-humss-1") # default bookmark mock state
    
    if supabase and not paper_id.startswith("mock-"):
        try:
            res = supabase.table("research_papers").select("*").eq("id", paper_id).execute()
            if res.data:
                paper = res.data[0]
            
            user_id = session['user']['id']
            bookmark_res = supabase.table("bookmarks").select("id").eq("user_id", user_id).eq("paper_id", paper_id).execute()
            is_bookmarked = len(bookmark_res.data) > 0
        except Exception as e:
            print("DB detail load error:", e)
            
    if not paper:
        return redirect(url_for('home'))
        
    return render_template('detail.html', paper=paper, is_bookmarked=is_bookmarked)

@app.route('/api/paper/<paper_id>/pdf')
@login_required
def stream_pdf(paper_id):
    # If a mock paper is requested, serve a simple blank/styled mock PDF binary stream
    if paper_id.startswith("mock-"):
        # Create a mock 1-page PDF using minimal bytes or send a dummy file stream
        # This allows testing the PDF canvas renderer immediately without having a real PDF uploaded!
        # Standard minimal PDF structure bytes (just enough for pdf.js to show "Mock PDF Document" text)
        mock_pdf_data = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/MediaBox[0 0 595 842]/Parent 2 0 R/Resources<<>>/Contents 4 0 R>>endobj\n4 0 obj<</Length 48>>stream\nBT /F1 12 Tf 72 712 Td (Lundayang Marians Secure PDF Copy) Tj ET\nendstream\nendobj\nxref\n0 5\n0000000000 65535 f\n0000000009 00000 n\n0000000056 00000 n\n0000000111 00000 n\n0000000212 00000 n\ntrailer<</Size 5/Root 1 0 R>>\nstartxref\n309\n%%EOF"
        return Response(
            io.BytesIO(mock_pdf_data),
            mimetype="application/pdf",
            headers={"Content-Disposition": "inline; filename=mock_research.pdf"}
        )
        
    try:
        if supabase:
            res = supabase.table("research_papers").select("pdf_path").eq("id", paper_id).execute()
            if res.data:
                pdf_path = res.data[0]['pdf_path']
                pdf_data = supabase.storage.from_("research_papers").download(pdf_path)
                return Response(
                    io.BytesIO(pdf_data),
                    mimetype="application/pdf",
                    headers={"Content-Disposition": "inline; filename=research.pdf"}
                )
        return jsonify({"error": "Supabase storage error."}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/developers')
@login_required
def developers():
    return render_template('developers.html')

@app.route('/faq')
@login_required
def faq():
    return render_template('faq.html')

# ----------------- ADMIN PORTAL -----------------

@app.route('/admin/upload', methods=['GET', 'POST'])
@admin_required
def admin_upload():
    error = None
    success = None
    
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        abstract = request.form.get('abstract', '').strip()
        strand = request.form.get('strand', '')
        academic_year = request.form.get('academic_year', '').strip()
        research_type = request.form.get('research_type', '').strip()
        subject_area = request.form.get('subject_area', '').strip()
        adviser = request.form.get('adviser', '').strip()
        awards = request.form.get('awards', '').strip() or None
        
        authors_raw = request.form.get('authors', '').split(',')
        authors = [a.strip() for a in authors_raw if a.strip()]
        
        keywords_raw = request.form.get('keywords', '').split(',')
        keywords = [k.strip() for k in keywords_raw if k.strip()]
        
        pdf_file = request.files.get('pdf_file')
        
        if not title or not abstract or not strand or not academic_year or not research_type or not subject_area or not adviser or not authors or not pdf_file:
            error = "All fields except Awards are required, including the PDF file."
        elif not pdf_file.filename.endswith('.pdf'):
            error = "File must be a PDF."
        else:
            try:
                if supabase:
                    safe_filename = f"{strand}/{academic_year.replace('/', '_')}_{pdf_file.filename.replace(' ', '_')}"
                    file_bytes = pdf_file.read()
                    supabase.storage.from_("research_papers").upload(
                        path=safe_filename,
                        file=file_bytes,
                        file_options={"content-type": "application/pdf"}
                    )
                    
                    supabase.table("research_papers").insert({
                        "title": title,
                        "abstract": abstract,
                        "strand": strand,
                        "academic_year": academic_year,
                        "research_type": research_type,
                        "subject_area": subject_area,
                        "authors": authors,
                        "adviser": adviser,
                        "awards": awards,
                        "keywords": keywords,
                        "pdf_path": safe_filename,
                        "created_by": session['user']['id']
                    }).execute()
                    success = "Research paper successfully uploaded and indexed!"
                else:
                    success = "Demo Upload: Research paper successfully uploaded!"
            except Exception as e:
                error = f"Upload failed: {str(e)}"
                
    return render_template('admin_upload.html', error=error, success=success)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
