import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response
from supabase import create_client, Client
from dotenv import load_dotenv
import io
import requests

# Load environment variables
load_dotenv()

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = os.getenv("FLASK_SECRET_KEY", "lundayang_marians_default_secret_key_12345")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
# Service role key bypasses RLS — required for server-side operations
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

# Initialize Supabase client with service role key (bypasses RLS)
# Falls back to anon key if service key not provided
supabase: Client = None
_supa_key = SUPABASE_SERVICE_KEY or SUPABASE_KEY
if SUPABASE_URL and _supa_key:
    try:
        supabase = create_client(SUPABASE_URL, _supa_key)
    except Exception as e:
        print("Error initializing Supabase client:", e)

# Separate client with anon key for auth operations (sign_up, sign_in)
supabase_auth: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase_auth = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print("Error initializing Supabase auth client:", e)

# Direct requests-based Supabase Storage helpers to avoid HTTPX SSL bugs on Windows
def storage_upload(bucket, path, file_bytes, content_type):
    url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{path}"
    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY or SUPABASE_KEY}",
        "apikey": SUPABASE_SERVICE_KEY or SUPABASE_KEY,
        "Content-Type": content_type,
        "x-upsert": "true"
    }
    response = requests.post(url, headers=headers, data=file_bytes)
    if response.status_code != 200:
        raise Exception(f"Storage upload failed: {response.text}")
    return response.json()

def storage_download(bucket, path):
    url = f"{SUPABASE_URL}/storage/v1/object/authenticated/{bucket}/{path}"
    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY or SUPABASE_KEY}",
        "apikey": SUPABASE_SERVICE_KEY or SUPABASE_KEY
    }
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Storage download failed: {response.text}")
    return response.content

def storage_remove(bucket, path):
    url = f"{SUPABASE_URL}/storage/v1/object/{bucket}"
    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY or SUPABASE_KEY}",
        "apikey": SUPABASE_SERVICE_KEY or SUPABASE_KEY,
        "Content-Type": "application/json"
    }
    response = requests.delete(url, headers=headers, json={"prefixes": [path]})
    return response

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
        
        # Derive email
        email = f"{student_id}@smapi.edu"
        role = "student"

        if not student_id or not name or not grade_section or not password or not confirm_password:
            error = "All fields are required."
        elif password != confirm_password:
            error = "Passwords do not match."
        elif len(password) < 6:
            error = "Password must be at least 6 characters."
        elif not supabase or not supabase_auth:
            error = "Database connection unavailable. Please try again later."
        else:
            try:
                auth_res = supabase_auth.auth.sign_up({
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
        elif not supabase or not supabase_auth:
            error = "Database connection unavailable. Please try again later."
        else:
            try:
                profile_res = supabase.table("profiles").select("email, role").eq("student_id", student_id).execute()
                if not profile_res.data:
                    error = "Invalid Student ID."
                else:
                    email = profile_res.data[0]['email']
                    role = profile_res.data[0]['role']
                    
                    auth_res = supabase_auth.auth.sign_in_with_password({
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
            except Exception as e:
                error = f"Login failed: {str(e)}"
                
    return render_template('login.html', error=error, msg=msg)

@app.route('/logout')
def logout():
    session.clear()
    if supabase_auth:
        try:
            supabase_auth.auth.sign_out()
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
        elif not supabase:
            error = "Database connection unavailable."
        else:
            try:
                supabase_auth.auth.update_user({"password": password})
                success = "Password updated successfully!"
            except Exception as e:
                error = f"Failed to update password: {str(e)}"
                
    return render_template('change_password.html', error=error, success=success)

# ----------------- APP PAGES -----------------

@app.route('/')
@login_required
def home():
    recent_papers = []
    best_in_research = []
    
    if supabase:
        try:
            papers_res = supabase.table("research_papers").select("*").order("created_at", desc=True).execute()
            if papers_res.data:
                recent_papers = papers_res.data
                
            best_res = supabase.table("research_papers").select("*").not_.is_("awards", "null").neq("awards", "").execute()
            if best_res.data:
                best_in_research = best_res.data
        except Exception as e:
            print("DB read failed:", e)
            
    return render_template('home.html', recent_papers=recent_papers, best_in_research=best_in_research)

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    error = None
    success = None
    user_id = session['user']['id']
    
    # Default profile data from session
    profile_data = {
        "id": user_id,
        "student_id": session['user']['student_id'],
        "name": "",
        "grade_section": "",
        "email": session['user']['email'],
        "role": session.get('role', 'student'),
        "avatar_url": None
    }
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        grade_section = request.form.get('grade_section', '').strip()
        email = request.form.get('email', '').strip()
        
        if not name or not grade_section or not email:
            error = "All fields are required."
        elif not supabase:
            error = "Database connection unavailable."
        else:
            try:
                update_data = {
                    "name": name,
                    "grade_section": grade_section,
                    "email": email
                }
                
                # Handle avatar upload to Supabase storage
                avatar_file = request.files.get('avatar')
                if avatar_file and avatar_file.filename:
                    ext = os.path.splitext(avatar_file.filename)[1].lower()
                    if ext in ['.jpg', '.jpeg', '.png', '.gif']:
                        try:
                            avatar_filename = f"{user_id}{ext}"
                            file_bytes = avatar_file.read()
                            
                            # Try to remove old avatar first (ignore errors)
                            try:
                                storage_remove("avatars", avatar_filename)
                            except:
                                pass
                            
                            # Upload new avatar
                            storage_upload("avatars", avatar_filename, file_bytes, avatar_file.content_type or "image/png")
                            
                            # Get public URL
                            avatar_url = f"{SUPABASE_URL}/storage/v1/object/public/avatars/{avatar_filename}"
                            update_data["avatar_url"] = avatar_url
                        except Exception as e:
                            print("Error uploading avatar:", e)
                            error = f"Error uploading photo: {str(e)}"
                
                supabase.table("profiles").update(update_data).eq("id", user_id).execute()
                session['user']['email'] = email
                success = "Profile updated successfully!"
            except Exception as e:
                error = f"Error updating profile: {str(e)}"
    
    # Load profile from database
    if supabase:
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
    bookmarked_papers = []
    
    if supabase:
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
    
    if not supabase:
        return jsonify({"success": False, "error": "Database connection unavailable."}), 500
        
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

@app.route('/search')
@login_required
def search():
    search_query = request.args.get('q', '').strip()
    strand_filter = request.args.get('strand', '').strip().upper()
    year_filter = request.args.get('year', '').strip()
    
    papers = []
    academic_years = []
    
    if supabase:
        try:
            query = supabase.table("research_papers").select("*")
            if strand_filter in ('HUMSS', 'ABM', 'STEM'):
                query = query.eq("strand", strand_filter)
            if year_filter:
                query = query.eq("academic_year", year_filter)
            res = query.execute()
            if res.data:
                papers = res.data
            
            # Get distinct academic years for all papers to populate filters
            years_res = supabase.table("research_papers").select("academic_year").execute()
            if years_res.data:
                academic_years = sorted(list(set(r['academic_year'] for r in years_res.data)), reverse=True)
        except Exception as e:
            print("DB search error:", e)
            
    # Apply search filter client-side
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
        
    return render_template('search_results.html', papers=papers, search_query=search_query, selected_strand=strand_filter, selected_year=year_filter, academic_years=academic_years)

@app.route('/strand/<strand_name>')
@login_required
def strand(strand_name):
    strand_name = strand_name.upper()
    if strand_name not in ('HUMSS', 'ABM', 'STEM'):
        return redirect(url_for('home'))
        
    search_query = request.args.get('q', '').strip()
    year_filter = request.args.get('year', '').strip()
    
    papers = []
    academic_years = []
    
    if supabase:
        try:
            query = supabase.table("research_papers").select("*").eq("strand", strand_name)
            if year_filter:
                query = query.eq("academic_year", year_filter)
            res = query.execute()
            if res.data:
                papers = res.data
            
            # Get distinct academic years for this strand
            years_res = supabase.table("research_papers").select("academic_year").eq("strand", strand_name).execute()
            if years_res.data:
                academic_years = sorted(list(set(r['academic_year'] for r in years_res.data)), reverse=True)
        except Exception as e:
            print("DB search error:", e)
            
    # Apply search filter client-side
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
        
    return render_template('strand.html', strand=strand_name, papers=papers, search_query=search_query, selected_year=year_filter, academic_years=academic_years)

@app.route('/paper/<paper_id>')
@login_required
def paper_detail(paper_id):
    paper = None
    is_bookmarked = False
    recommended_papers = []
    
    if supabase:
        try:
            res = supabase.table("research_papers").select("*").eq("id", paper_id).execute()
            if res.data:
                paper = res.data[0]
            
            user_id = session['user']['id']
            bookmark_res = supabase.table("bookmarks").select("id").eq("user_id", user_id).eq("paper_id", paper_id).execute()
            is_bookmarked = len(bookmark_res.data) > 0
            
            # Recommendation Engine: fetch candidates excluding active paper
            if paper:
                candidates_res = supabase.table("research_papers").select("*").neq("id", paper_id).execute()
                if candidates_res.data:
                    candidates = candidates_res.data
                    
                    cur_keywords = set(k.lower().strip() for k in paper.get('keywords', []) if k)
                    cur_strand = paper.get('strand', '').upper()
                    cur_subject = paper.get('subject_area', '').lower()
                    cur_type = paper.get('research_type', '').lower()
                    title_words = set(w.lower() for w in paper.get('title', '').split() if len(w) > 3)
                    
                    scored_candidates = []
                    for p in candidates:
                        score = 0
                        
                        # 1. Strand matching
                        p_strand = p.get('strand', '').upper()
                        if p_strand and p_strand == cur_strand:
                            score += 3
                            
                        # 2. Keywords overlap
                        p_keywords = set(k.lower().strip() for k in p.get('keywords', []) if k)
                        matching_keywords = cur_keywords.intersection(p_keywords)
                        score += len(matching_keywords) * 2
                        
                        # 3. Subject area / Research type match
                        p_subject = p.get('subject_area', '').lower()
                        p_type = p.get('research_type', '').lower()
                        if p_subject and cur_subject and (p_subject in cur_subject or cur_subject in p_subject):
                            score += 2
                        if p_type and cur_type and (p_type in cur_type or cur_type in p_type):
                            score += 1
                            
                        # 4. Title term overlap
                        p_title_words = set(w.lower() for w in p.get('title', '').split() if len(w) > 3)
                        title_overlap = title_words.intersection(p_title_words)
                        score += len(title_overlap)
                        
                        # Only consider papers with genuine similarity (score > 0)
                        if score > 0:
                            scored_candidates.append((score, p))
                        
                    # Sort candidates by relevance score descending
                    scored_candidates.sort(key=lambda x: x[0], reverse=True)
                    recommended_papers = [item[1] for item in scored_candidates[:4]]
        except Exception as e:
            print("DB detail load error:", e)
            
    if not paper:
        return redirect(url_for('home'))
        
    return render_template('detail.html', paper=paper, is_bookmarked=is_bookmarked, recommended_papers=recommended_papers)

@app.route('/api/paper/<paper_id>/pdf')
@login_required
def stream_pdf(paper_id):
    if not supabase:
        return jsonify({"error": "Database connection unavailable."}), 500
    
    try:
        res = supabase.table("research_papers").select("pdf_path").eq("id", paper_id).execute()
        if res.data:
            pdf_path = res.data[0]['pdf_path']
            pdf_data = storage_download("research_papers", pdf_path)
            return Response(
                io.BytesIO(pdf_data),
                mimetype="application/pdf",
                headers={
                    "Content-Disposition": "inline; filename=research.pdf",
                    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                    "Pragma": "no-cache",
                    "Expires": "0",
                    "X-Content-Type-Options": "nosniff"
                }
            )
        return jsonify({"error": "Paper not found."}), 404
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
        elif not supabase:
            error = "Database connection unavailable."
        else:
            try:
                safe_filename = f"{strand}/{academic_year.replace('/', '_')}_{pdf_file.filename.replace(' ', '_')}"
                file_bytes = pdf_file.read()
                storage_upload("research_papers", safe_filename, file_bytes, "application/pdf")
                
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
            except Exception as e:
                error = f"Upload failed: {str(e)}"
                
    return render_template('admin_upload.html', error=error, success=success)

@app.route('/admin/paper/<paper_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_paper(paper_id):
    if not supabase:
        return jsonify({"error": "Database connection unavailable."}), 500

    try:
        paper_res = supabase.table("research_papers").select("*").eq("id", paper_id).execute()
        if not paper_res.data:
            return redirect(url_for('home'))

        paper = paper_res.data[0]
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

            if not title or not abstract or not strand or not academic_year or not research_type or not subject_area or not adviser or not authors:
                error = "All fields except Awards are required."
            elif pdf_file and pdf_file.filename and not pdf_file.filename.lower().endswith('.pdf'):
                error = "File must be a PDF."
            else:
                try:
                    pdf_path = paper['pdf_path']
                    if pdf_file and pdf_file.filename:
                        storage_upload("research_papers", pdf_path, pdf_file.read(), "application/pdf")

                    updated_values = {
                        "title": title,
                        "abstract": abstract,
                        "strand": strand,
                        "academic_year": academic_year,
                        "research_type": research_type,
                        "subject_area": subject_area,
                        "authors": authors,
                        "adviser": adviser,
                        "awards": awards,
                        "keywords": keywords
                    }

                    supabase.table("research_papers").update(updated_values).eq("id", paper_id).execute()
                    paper.update(updated_values)
                    success = "Research paper updated successfully."
                except Exception as e:
                    error = f"Update failed: {str(e)}"

            if error:
                paper = {
                    **paper,
                    "title": request.form.get('title', '').strip(),
                    "abstract": request.form.get('abstract', '').strip(),
                    "strand": request.form.get('strand', ''),
                    "academic_year": request.form.get('academic_year', '').strip(),
                    "research_type": request.form.get('research_type', '').strip(),
                    "subject_area": request.form.get('subject_area', '').strip(),
                    "authors": [a.strip() for a in request.form.get('authors', '').split(',') if a.strip()],
                    "adviser": request.form.get('adviser', '').strip(),
                    "awards": request.form.get('awards', '').strip() or None,
                    "keywords": [k.strip() for k in request.form.get('keywords', '').split(',') if k.strip()]
                }

        return render_template('admin_upload.html', error=error, success=success, paper=paper)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/admin/paper/<paper_id>/delete', methods=['POST'])
@admin_required
def delete_paper(paper_id):
    if not supabase:
        return jsonify({"success": False, "error": "Database connection unavailable."}), 500
        
    try:
        # 1. Fetch paper details to get the pdf_path
        res = supabase.table("research_papers").select("pdf_path").eq("id", paper_id).execute()
        if not res.data:
            return jsonify({"success": False, "error": "Paper not found."}), 404
            
        pdf_path = res.data[0]['pdf_path']
        
        # 2. Delete the PDF file from storage
        try:
            storage_remove("research_papers", pdf_path)
        except Exception as e:
            print("Failed to delete PDF from storage:", e)
            
        # 3. Delete database row (bookmarks cascade automatically)
        supabase.table("research_papers").delete().eq("id", paper_id).execute()
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
