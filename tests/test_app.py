from types import SimpleNamespace
import pytest
import index as app_module


class FakeQuery:
    def __init__(self, tables, table_name):
        self.tables = tables
        self.table_name = table_name
        self._op = "select"
        self._filters = []
        self._or_expr = None
        self._payload = None
        self._order_col = None
        self._order_desc = False
        self._count_mode = None

    def select(self, cols="*", count=None):
        self._op = "select"
        self._count_mode = count
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def neq(self, col, val):
        self._filters.append(("neq", col, val))
        return self

    @property
    def not_(self):
        class NotHelper:
            def __init__(self, parent):
                self.parent = parent

            def is_(self, col, val):
                self.parent._filters.append(("not_is", col, val))
                return self.parent

        return NotHelper(self)

    def or_(self, expr):
        self._or_expr = expr
        return self

    def order(self, col, desc=False):
        self._order_col = col
        self._order_desc = desc
        return self

    def _matches(self, row):
        for op, col, val in self._filters:
            row_val = row.get(col)
            if op == "eq" and row_val != val:
                return False
            if op == "neq" and row_val == val:
                return False
            if op == "not_is" and val == "null" and row_val is None:
                return False
        if self._or_expr:
            matched_any = False
            for part in self._or_expr.split(","):
                if ".eq." in part:
                    col, val = part.split(".eq.", 1)
                    if str(row.get(col, "")) == val:
                        matched_any = True
            if not matched_any:
                return False
        return True

    def execute(self):
        rows = self.tables.setdefault(self.table_name, [])
        if self._op == "insert":
            new_row = dict(self._payload)
            if "id" not in new_row:
                new_row["id"] = f"{self.table_name}-{len(rows) + 1}"
            rows.append(new_row)
            return SimpleNamespace(data=[new_row], count=1)

        if self._op == "update":
            updated = []
            for r in rows:
                if self._matches(r):
                    r.update(self._payload)
                    updated.append(dict(r))
            return SimpleNamespace(data=updated, count=len(updated))

        if self._op == "delete":
            kept = [r for r in rows if not self._matches(r)]
            deleted_count = len(rows) - len(kept)
            self.tables[self.table_name] = kept
            return SimpleNamespace(data=[], count=deleted_count)

        matched = [dict(r) for r in rows if self._matches(r)]
        if self._order_col:
            matched.sort(key=lambda r: r.get(self._order_col) or "", reverse=self._order_desc)
        return SimpleNamespace(data=matched, count=len(matched))


class FakeAdminAuth:
    def __init__(self, auth_users):
        self.auth_users = auth_users
        self.updated_calls = []

    def update_user_by_id(self, user_id, attrs):
        self.updated_calls.append((user_id, attrs))
        for u in self.auth_users.values():
            if u["id"] == user_id:
                u.update(attrs)
        return SimpleNamespace(user=SimpleNamespace(id=user_id))


class FakeAuthNamespace:
    def __init__(self, auth_users):
        self.auth_users = auth_users
        self.admin = FakeAdminAuth(auth_users)

    def sign_up(self, creds):
        email = creds["email"]
        uid = f"user-{len(self.auth_users) + 1}"
        self.auth_users[email] = {
            "id": uid,
            "email": email,
            "password": creds["password"],
            "email_confirm": False,
        }
        return SimpleNamespace(user=SimpleNamespace(id=uid, email=email))

    def sign_in_with_password(self, creds):
        email = creds["email"]
        password = creds["password"]
        user = self.auth_users.get(email)
        if not user or user["password"] != password:
            raise Exception("Invalid login credentials")
        return SimpleNamespace(
            user=SimpleNamespace(id=user["id"], email=email),
            session=SimpleNamespace(access_token=f"tok-{user['id']}"),
        )

    def sign_out(self):
        return None


class FakeSupabase:
    def __init__(self, tables, auth_users):
        self.tables = tables
        self.auth = FakeAuthNamespace(auth_users)

    def table(self, name):
        return FakeQuery(self.tables, name)


@pytest.fixture
def client(monkeypatch):
    auth_users = {
        "admin@smla.edu.ph": {"id": "admin-1", "email": "admin@smla.edu.ph", "password": "Password123", "email_confirm": True},
        "approved@smla.edu.ph": {"id": "student-1", "email": "approved@smla.edu.ph", "password": "Password123", "email_confirm": True},
        "pending@smla.edu.ph": {"id": "student-2", "email": "pending@smla.edu.ph", "password": "Password123", "email_confirm": True},
        "rejected@smla.edu.ph": {"id": "student-3", "email": "rejected@smla.edu.ph", "password": "Password123", "email_confirm": True},
    }

    papers = []
    for idx in range(1, 9):
        papers.append({
            "id": f"paper-stem-{idx}",
            "title": f"STEM Prototype Study {idx}",
            "abstract": f"Abstract for study {idx} exploring Arduino automation.",
            "strand": "STEM",
            "academic_year": "2024-2025",
            "research_type": "Experimental / Quantitative" if idx % 2 == 1 else "Descriptive",
            "subject_area": "Applied Science",
            "authors": ["Juan Dela Cruz"],
            "adviser": "Ms. Maureen L. Cruz",
            "awards": "Best in Research" if idx == 1 else None,
            "keywords": ["arduino", "prototype"] if idx % 2 == 1 else ["survey", "education"],
            "pdf_path": f"STEM/paper_{idx}.pdf",
            "created_at": f"2025-01-0{idx}T00:00:00Z",
        })
    papers.append({
        "id": "paper-humss-1",
        "title": "Stage Fright to Stage Bright",
        "abstract": "Theater workshop impact study.",
        "strand": "HUMSS",
        "academic_year": "2025-2026",
        "research_type": "Qualitative",
        "subject_area": "Humanities",
        "authors": ["Maria Santos"],
        "adviser": "Mr. Jose Santos",
        "awards": "Best in Research (HUMSS)",
        "keywords": ["theater", "speaking"],
        "pdf_path": "HUMSS/stage.pdf",
        "created_at": "2025-02-01T00:00:00Z",
    })
    papers.append({
        "id": "paper-abm-quanti-quali",
        "title": "Quanti-Quali Business Study",
        "abstract": "Mixed study of local enterprises.",
        "strand": "ABM",
        "academic_year": "2025-2026",
        "research_type": "Quanti-Quali Research",
        "subject_area": "Business",
        "authors": ["Ana Reyes"],
        "adviser": "Mr. Allan Perez",
        "awards": None,
        "keywords": ["business"],
        "pdf_path": "ABM/quanti_quali.pdf",
        "created_at": "2025-02-02T00:00:00Z",
    })
    papers.append({
        "id": "paper-abm-tracer",
        "title": "Alumni Tracer Study",
        "abstract": "Graduate outcomes survey.",
        "strand": "ABM",
        "academic_year": "2025-2026",
        "research_type": "Tracer Study",
        "subject_area": "Education",
        "authors": ["Leo Cruz"],
        "adviser": "Mr. Allan Perez",
        "awards": None,
        "keywords": ["alumni"],
        "pdf_path": "ABM/tracer.pdf",
        "created_at": "2025-02-03T00:00:00Z",
    })

    tables = {
        "profiles": [
            {"id": "admin-1", "student_id": "ADM-001", "name": "Admin User", "grade_section": "Faculty", "email": "admin@smla.edu.ph", "role": "admin", "status": "approved", "created_at": "2025-01-01"},
            {"id": "student-1", "student_id": "2024-001", "name": "Approved Student", "grade_section": "12-STEM", "email": "approved@smla.edu.ph", "role": "student", "status": "approved", "created_at": "2025-01-02"},
            {"id": "student-2", "student_id": "2024-002", "name": "Pending Student", "grade_section": "12-ABM", "email": "pending@smla.edu.ph", "role": "student", "status": "pending", "created_at": "2025-01-03"},
            {"id": "student-3", "student_id": "2024-003", "name": "Rejected Student", "grade_section": "12-HUMSS", "email": "rejected@smla.edu.ph", "role": "student", "status": "rejected", "created_at": "2025-01-04"},
        ],
        "research_papers": papers,
        "bookmarks": [{"id": "bm-1", "user_id": "student-1", "paper_id": "paper-stem-1"}],
        "site_visits": [],
        "paper_views": [],
        "admin_audit_logs": [],
    }

    fake_supa = FakeSupabase(tables, auth_users)
    monkeypatch.setattr(app_module, "supabase", fake_supa)
    monkeypatch.setattr(app_module, "supabase_auth", fake_supa)
    app_module.app.config["TESTING"] = True

    with app_module.app.test_client() as test_client:
        test_client.fake_supa = fake_supa
        yield test_client


def test_public_landing_and_info_pages(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"Our Vision" in res.data
    assert b"Our Mission" in res.data
    assert b"Log In" in res.data
    # Upgraded guest navbar pills & frosted language control
    assert b"nav-login-pill" in res.data
    assert b"nav-signup-pill" in res.data
    assert b"nav-pill-btn" in res.data
    # Undecided visitors see the open cookie banner, blocker-safe fallback modal markup, and cache-busted CSS
    assert b'id="cookie-banner"' in res.data
    assert b'class="cookie-banner open"' in res.data
    assert b'id="lm-prefs-modal"' in res.data
    assert b'id="open-cookie-settings-btn"' in res.data
    assert b"/static/css/style.css?v=" in res.data
    assert len(client.fake_supa.tables["site_visits"]) == 0
    with client.session_transaction() as sess:
        assert "visitor_id" not in sess

    # Footer keeps Developers & FAQ spotlight cards and puts Privacy Policy, Terms & Cookie Settings in bottom bar
    assert b"footer-bottom-links" in res.data
    assert b'href="/privacy-policy"' in res.data
    assert b'href="/terms"' in res.data

    # Invalid consent option is rejected cleanly
    bad_consent = client.post("/api/cookie-consent", json={"consent": "unknown"})
    assert bad_consent.status_code == 400

    # Selecting "essential" stores cookie, closes banner, and skips site_visits telemetry
    essential_res = client.post("/api/cookie-consent", json={"consent": "essential", "path": "/"})
    assert essential_res.status_code == 200
    assert essential_res.get_json()["consent"] == "essential"
    assert "lm_cookie_consent=essential" in essential_res.headers.get("Set-Cookie", "")

    assert client.get("/").status_code == 200
    assert b'class="cookie-banner open"' not in client.get("/").data
    assert client.get("/developers").status_code == 200
    assert client.get("/faq").status_code == 200

    privacy_res = client.get("/privacy-policy")
    assert privacy_res.status_code == 200
    assert b"Privacy Policy" in privacy_res.data
    assert b"RA 10173" in privacy_res.data
    assert b"Cookies &amp; Session Telemetry" in privacy_res.data
    assert b"lm_cookie_consent" in privacy_res.data

    terms_res = client.get("/terms")
    assert terms_res.status_code == 200
    assert b"Terms &amp; Conditions" in terms_res.data
    assert b"APA 7th Edition" in terms_res.data

    signup_get = client.get("/signup")
    assert signup_get.status_code == 200
    assert b'href="/privacy-policy"' in signup_get.data
    assert b'href="/terms"' in signup_get.data
    assert len(client.fake_supa.tables["site_visits"]) == 0

    # Opting into "all" records initial visit + subsequent public visits
    accept_res = client.post("/api/cookie-consent", json={"consent": "all", "path": "/"})
    assert accept_res.status_code == 200
    assert accept_res.get_json()["consent"] == "all"
    assert "lm_cookie_consent=all" in accept_res.headers.get("Set-Cookie", "")

    home_after = client.get("/")
    assert b'class="cookie-banner open"' not in home_after.data
    assert b'data-consent="all"' in home_after.data
    assert client.get("/faq").status_code == 200
    assert client.get("/privacy-policy").status_code == 200
    assert len(client.fake_supa.tables["site_visits"]) >= 4


def test_signup_sets_pending_and_enforces_password_rules(client):
    weak = client.post("/signup", data={
        "student_id": "2026-100",
        "name": "Weak Pw",
        "grade_section": "12-STEM",
        "email": "weak@smla.edu.ph",
        "password": "weak",
        "confirm_password": "weak",
    })
    assert weak.status_code == 200
    assert b"at least 8 characters" in weak.data

    ok = client.post("/signup", data={
        "student_id": "2026-101",
        "name": "New Marian",
        "grade_section": "12-STEM",
        "email": "newmarian@smla.edu.ph",
        "password": "StrongPass1",
        "confirm_password": "StrongPass1",
    })
    assert ok.status_code == 302
    created_profiles = [p for p in client.fake_supa.tables["profiles"] if p["student_id"] == "2026-101"]
    assert len(created_profiles) == 1
    assert created_profiles[0]["status"] == "pending"


def test_login_blocks_pending_and_rejected_allows_approved(client):
    pending_res = client.post("/login", data={"student_id": "2024-002", "password": "Password123"})
    assert pending_res.status_code == 200
    assert b"pending administrator approval" in pending_res.data
    with client.session_transaction() as sess:
        assert "user" not in sess

    rejected_res = client.post("/login", data={"student_id": "2024-003", "password": "Password123"})
    assert rejected_res.status_code == 200
    assert b"declined" in rejected_res.data

    approved_res = client.post("/login", data={"student_id": "2024-001", "password": "Password123"}, follow_redirects=True)
    assert approved_res.status_code == 200
    assert b"BROWSE RESEARCH" in approved_res.data
    assert b"Filter by Research Type" not in approved_res.data
    assert b"home-type-select" not in approved_res.data
    assert b"MISSION &amp; VISION" in approved_res.data


def test_change_password_verifies_current_password(client):
    client.post("/login", data={"student_id": "2024-001", "password": "Password123"})

    bad = client.post("/change-password", data={
        "current_password": "WrongPassword1",
        "password": "NewPassword1",
        "confirm_password": "NewPassword1",
    })
    assert bad.status_code == 200
    assert b"Current password is incorrect" in bad.data

    good = client.post("/change-password", data={
        "current_password": "Password123",
        "password": "NewPassword1",
        "confirm_password": "NewPassword1",
    })
    assert good.status_code == 200
    assert b"Password updated successfully!" in good.data
    assert client.fake_supa.auth.auth_users["approved@smla.edu.ph"]["password"] == "NewPassword1"


def test_search_suggestions_type_filter_and_pagination(client):
    client.post("/login", data={"student_id": "2024-001", "password": "Password123"})

    # 1-char autosuggest support
    sug_1char = client.get("/api/search-suggestions?q=s")
    assert sug_1char.status_code == 200
    assert len(sug_1char.get_json()["suggestions"]) > 0

    sug_res = client.get("/api/search-suggestions?q=arduino")
    assert sug_res.status_code == 200
    suggestions = sug_res.get_json()["suggestions"]
    assert len(suggestions) == 4

    # STEM has 8 papers -> Page 1 shows 6, Page 2 shows 2
    p1 = client.get("/strand/STEM?page=1")
    assert p1.status_code == 200
    assert b"Showing 1&ndash;6 of 8 papers" in p1.data

    p2 = client.get("/strand/STEM?page=2")
    assert p2.status_code == 200
    assert b"Showing 7&ndash;8 of 8 papers" in p2.data

    # Research type filter on /search: normalized categories & abbreviation matching
    typed = client.get("/search?type=Qualitative")
    assert typed.status_code == 200
    assert b"Stage Fright to Stage Bright" in typed.data
    assert b"Quanti-Quali Business Study" in typed.data
    assert b"STEM Prototype Study 1" not in typed.data
    # Raw messy DB type strings should not pollute the dropdown
    assert b'<option value="Quanti-Quali Research">' not in typed.data

    other_typed = client.get("/search?type=Other+%2F+Applied")
    assert other_typed.status_code == 200
    assert b"Alumni Tracer Study" in other_typed.data
    assert b"Stage Fright to Stage Bright" not in other_typed.data


def test_paper_view_tracking_and_admin_dashboard(client):
    # Student cannot access admin dashboard or export; analytics remain disabled before opt-in consent
    client.post("/login", data={"student_id": "2024-001", "password": "Password123"})
    assert client.get("/admin/dashboard").status_code == 302
    assert client.get("/admin/export/papers.csv").status_code == 302
    assert client.post("/admin/users/bulk-approve").status_code == 302
    student_paper_pre = client.get("/paper/paper-stem-1")
    assert student_paper_pre.status_code == 200
    assert b"detail-bookmark-btn" in student_paper_pre.data
    assert b'id="cookie-banner"' in student_paper_pre.data
    assert len(client.fake_supa.tables["paper_views"]) == 0
    assert len(client.fake_supa.tables["site_visits"]) == 0

    # Essential Only keeps telemetry disabled
    client.post("/api/cookie-consent", json={"consent": "essential", "path": "/paper/paper-stem-1"})
    assert client.get("/paper/paper-stem-1").status_code == 200
    assert len(client.fake_supa.tables["paper_views"]) == 0

    # Accept All enables visit + paper_view analytics for students
    client.post("/api/cookie-consent", json={"consent": "all", "path": "/paper/paper-stem-1"})
    student_paper = client.get("/paper/paper-stem-1")
    assert student_paper.status_code == 200
    assert b"detail-bookmark-btn" in student_paper.data
    assert b"nav-user-chip" in student_paper.data
    assert b"Approved Student" in student_paper.data
    assert len(client.fake_supa.tables["paper_views"]) == 1
    student_visit_count = len(client.fake_supa.tables["site_visits"])

    # Switching back to Essential clears visitor_id and stops additional analytics inserts
    client.post("/api/cookie-consent", json={"consent": "essential", "path": "/paper/paper-stem-1"})
    with client.session_transaction() as sess:
        assert "visitor_id" not in sess
    assert client.get("/paper/paper-stem-1").status_code == 200
    assert len(client.fake_supa.tables["paper_views"]) == 1
    assert len(client.fake_supa.tables["site_visits"]) == student_visit_count

    client.get("/logout")
    admin_login = client.post("/login", data={"student_id": "ADM-001", "password": "Password123"})
    assert admin_login.status_code == 302
    assert "/admin/dashboard" in admin_login.headers["Location"]
    admin_pre_visits = len(client.fake_supa.tables["site_visits"])

    # Admin is strictly isolated away from Home and student repository routes
    for student_route in ("/", "/home", "/landing", "/strand/STEM", "/search", "/bookmarks"):
        blocked = client.get(student_route)
        assert blocked.status_code == 302
        assert "/admin/dashboard" in blocked.headers["Location"]

    assert client.post("/bookmark/toggle", data={"paper_id": "paper-stem-1"}).status_code == 403
    assert client.get("/api/search-suggestions?q=s").status_code == 403

    dash = client.get("/admin/dashboard")
    assert dash.status_code == 200
    assert b"Admin Dashboard" in dash.data
    assert b"Pending Student" in dash.data
    assert b"STEM Prototype Study 1" in dash.data
    assert b"Admin Workspace" in dash.data
    assert b"7-Day Visits &amp; Paper Views" in dash.data
    assert b"Activity Log" in dash.data
    assert b"Export CSV" in dash.data
    # Admin navigation & footer omit Home, Mission & Vision, Upload nav item, and Bookmarks
    assert b"Mission &amp; Vision" not in dash.data
    assert b'href="/bookmarks"' not in dash.data
    assert b'href="/admin/upload"' not in dash.data
    assert b'class="page-back-btn' not in dash.data
    assert b"open-upload-modal-btn" in dash.data
    assert b"paper-editor-modal" in dash.data
    # Admin navbar chip displays initials badge & Admin role pill while keeping left bar clear
    assert b"nav-avatar-badge is-admin" in dash.data
    assert b"dropdown-role-pill is-admin" in dash.data
    # Admin portal skips cookie banner, fallback preferences modal, and footer cookie settings trigger
    assert b'id="cookie-banner"' not in dash.data
    assert b'id="lm-prefs-modal"' not in dash.data
    assert b'id="open-cookie-settings-btn"' not in dash.data

    # Legacy GET /admin/upload & /admin/paper/<id>/edit redirect to Dashboard modal hashes
    get_upload = client.get("/admin/upload")
    assert get_upload.status_code == 302
    assert "/admin/dashboard#upload-paper" in get_upload.headers["Location"]
    get_edit = client.get("/admin/paper/paper-stem-1/edit")
    assert get_edit.status_code == 302
    assert "/admin/dashboard#edit=paper-stem-1" in get_edit.headers["Location"]

    # CSV Report Export works for admin
    csv_res = client.get("/admin/export/papers.csv")
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.content_type
    assert b"STEM Prototype Study 1" in csv_res.data
    assert b"Title,Strand,Academic Year" in csv_res.data

    # Admin can preview papers via /paper/<id> with in-page Edit modal & without bookmark/recommendations or inflating analytics
    admin_preview = client.get("/paper/paper-stem-1")
    assert admin_preview.status_code == 200
    assert b"open-edit-paper-modal-btn" in admin_preview.data
    assert b"paper-editor-modal" in admin_preview.data
    assert b"detail-bookmark-btn" not in admin_preview.data
    assert b"Researches you might like:" not in admin_preview.data
    assert b'id="cookie-banner"' not in admin_preview.data
    assert b'id="lm-prefs-modal"' not in admin_preview.data
    assert b'id="open-cookie-settings-btn"' not in admin_preview.data
    assert len(client.fake_supa.tables["paper_views"]) == 1
    assert len(client.fake_supa.tables["site_visits"]) == admin_pre_visits
    assert len(client.fake_supa.tables["site_visits"]) == student_visit_count

    # AJAX Modal Upload & Edit endpoints work cleanly and write audit logs
    ajax_upload = client.post(
        "/admin/upload",
        data={
            "title": "Modal Uploaded Paper",
            "abstract": "Abstract created inside the admin modal.",
            "strand": "ABM",
            "academic_year": "2026-2027",
            "research_type": "Descriptive",
            "subject_area": "Business & Entrepreneurship",
            "authors": "Test Author One",
            "adviser": "Ms. Maureen L. Cruz",
            "awards": "",
            "keywords": "modal, upload",
            "pdf_path": "ABM/modal_test.pdf",
        },
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert ajax_upload.status_code == 200
    upload_json = ajax_upload.get_json()
    assert upload_json["success"] is True
    assert upload_json["paper"]["title"] == "Modal Uploaded Paper"
    created_pid = upload_json["paper"]["id"]

    ajax_edit = client.post(
        f"/admin/paper/{created_pid}/edit",
        data={
            "title": "Modal Edited Paper Title",
            "abstract": "Updated abstract in modal.",
            "strand": "STEM",
            "academic_year": "2026-2027",
            "research_type": "Experimental",
            "subject_area": "Applied Science & Technology",
            "authors": "Test Author One, Co Author",
            "adviser": "Ms. Maureen L. Cruz",
            "awards": "Best Innovation",
            "keywords": "modal, edited",
            "pdf_path": "ABM/modal_test.pdf",
        },
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert ajax_edit.status_code == 200
    edit_json = ajax_edit.get_json()
    assert edit_json["success"] is True
    assert edit_json["paper"]["title"] == "Modal Edited Paper Title"
    assert edit_json["paper"]["strand"] == "STEM"

    # Admin profile adapts student labels cleanly & legal pages back link routes to dashboard
    admin_prof = client.get("/profile")
    assert admin_prof.status_code == 200
    assert b"Admin ID" in admin_prof.data
    assert b"Office / Department" in admin_prof.data
    assert b"/admin/dashboard" in admin_prof.data

    admin_privacy = client.get("/privacy-policy")
    assert admin_privacy.status_code == 200
    assert b"/admin/dashboard" in admin_privacy.data

    # Approve pending student via admin bulk-approve endpoint & verify audit log
    bulk_res = client.post("/admin/users/bulk-approve")
    assert bulk_res.status_code == 200
    bulk_json = bulk_res.get_json()
    assert bulk_json["success"] is True
    assert bulk_json["approved_count"] == 1
    assert "student-2" in bulk_json["approved_ids"]
    assert len(client.fake_supa.tables["admin_audit_logs"]) == 3

    # Single user role update logs another audit entry
    role_res = client.post("/admin/users/student-2/status", json={"role": "admin"})
    assert role_res.status_code == 200
    assert role_res.get_json()["role"] == "admin"
    assert len(client.fake_supa.tables["admin_audit_logs"]) == 4

    # Reload dashboard confirms audit entries appear in Activity Log
    dash_after = client.get("/admin/dashboard")
    assert dash_after.status_code == 200
    assert b"Bulk approved 1 pending account(s)" in dash_after.data

    # Revert student-2 role back to student and log in as student-2 -> lands on Repository Home
    client.post("/admin/users/student-2/status", json={"role": "student"})

    # Now pending student can log in and lands on Repository Home
    client.get("/logout")
    login_now = client.post("/login", data={"student_id": "2024-002", "password": "Password123"})
    assert login_now.status_code == 302
    assert "/admin/dashboard" not in login_now.headers["Location"]
