import os
import csv
import math
import re
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response
from supabase import create_client, Client
from dotenv import load_dotenv
import io
import requests
import hashlib

# Load environment variables
load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, template_folder=os.path.join(BASE_DIR, 'templates'), static_folder=os.path.join(BASE_DIR, 'static'))
app.secret_key = os.getenv("FLASK_SECRET_KEY", "lundayang_marians_default_secret_key_12345")

# WSGI Middleware to normalize PATH_INFO for Vercel serverless rewrites
class VercelPathFixMiddleware:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        invoke_path = environ.get('HTTP_X_INVOKE_PATH') or environ.get('HTTP_X_FORWARDED_PATH')
        if invoke_path:
            environ['PATH_INFO'] = invoke_path
            return self.wsgi_app(environ, start_response)

        qs = environ.get('QUERY_STRING', '')
        if '__path__=' in qs:
            from urllib.parse import parse_qs
            parsed_qs = parse_qs(qs)
            if '__path__' in parsed_qs and parsed_qs['__path__']:
                environ['PATH_INFO'] = parsed_qs['__path__'][0]
                return self.wsgi_app(environ, start_response)

        path_info = environ.get('PATH_INFO', '')
        if path_info in ('/api/index.py', '/api/index', '/api'):
            environ['PATH_INFO'] = '/'
        elif path_info.startswith('/api/index.py/'):
            environ['PATH_INFO'] = path_info[len('/api/index.py'):]
        elif path_info.startswith('/api/index/'):
            environ['PATH_INFO'] = path_info[len('/api/index'):]

        return self.wsgi_app(environ, start_response)

app.wsgi_app = VercelPathFixMiddleware(app.wsgi_app)

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

# ----------------- MISSION & VISION + RESEARCH TAXONOMY -----------------
# Centralized Mission & Vision text (edit here to update both Landing & Home pages)
MISSION_VISION = {
    "vision_title": "Our Vision",
    "vision_text": (
        "A center of Marian academic excellence and digital scholarship where student-led "
        "research inspires innovation, integrity, and community-centered progress in Santa Maria, Laguna and beyond."
    ),
    "mission_title": "Our Mission",
    "mission_text": (
        "To preserve, organize, and showcase approved student research of Sta. Maria (Laguna) Academy Inc. "
        "in a secure digital repository—empowering future Marian researchers with accessible references, "
        "fostering ethical scholarship, and cultivating critical inquiry."
    ),
}

CORE_RESEARCH_TYPES = [
    "Quantitative",
    "Qualitative",
    "Mixed Methods",
    "Experimental",
    "Descriptive",
    "Action Research",
]
STANDARD_RESEARCH_TYPES = list(CORE_RESEARCH_TYPES)

PAPERS_PER_PAGE = 6

# ----------------- TRANSLATION SYSTEM -----------------
TRANSLATIONS = {
    'tl': {
        "English": "English",
        "Tagalog": "Tagalog",
        "Home": "Tahanan",
        "Landing": "Panimula",
        "Mission & Vision": "Misyon at Bisyon",
        "Developers": "Mga Tagapag-unlad",
        "FAQ": "Mga Madalas Itanong",
        "Dashboard": "Dashboard",
        "Upload": "I-upload",
        "My Profile": "Aking Profile",
        "Bookmarks": "Mga Naka-bookmark",
        "Change Password": "Palitan ang Password",
        "Log Out": "Mag-log Out",
        "Log In": "Mag-log In",
        "Sign Up": "Mag-rehistro",
        "SEARCH": "MAGHANAP",
        "Enter search item:": "Ipasok ang hahanapin:",
        "Search": "Maghanap",
        "Search Research Papers...": "Maghanap ng mga Papel Pananaliksik...",
        "All Strands": "Lahat ng Strand",
        "All Types": "Lahat ng Uri",
        "All Years": "Lahat ng Taon",
        "Filter by Research Type": "I-filter ayon sa Uri ng Pananaliksik",
        "Research Type:": "Uri ng Pananaliksik:",
        "Academic Strand:": "Akademikong Strand:",
        "Academic Year:": "Taong Akademiko:",
        "Keywords:": "Mga Susing Salita:",
        "Enter keywords...": "Magpasok ng mga susing salita...",
        "Sort by:": "I-sort ayon sa:",
        "Latest": "Pinakabagong",
        "Oldest": "Pinakalumang",
        "Title A-Z": "Pamagat A-Z",
        "Filter Results": "I-filter ang mga Resulta",
        "Clear Filters": "Alisin ang Filter",
        "Found": "Nakatagpo ng",
        "research papers": "mga papel pananaliksik",
        "research paper": "papel pananaliksik",
        "No research papers found matching your criteria.": "Walang natagpuang papel pananaliksik na tumutugma sa iyong pamantayan.",
        "BROWSE RESEARCH": "MAG-BROWSE NG PANANALIKSIK",
        "RECENT RESEARCH PAPERS": "MGA BAGONG PAPEL PANANALIKSIK",
        "BEST IN RESEARCH": "PINAKAMAHUSAY SA PANANALIKSIK",
        "View All": "Tingnan Lahat",
        "Read Paper": "Basahin ang Papel",
        "No research papers available yet.": "Wala pang available na papel pananaliksik.",
        "No awarded research papers found.": "Walang natagpuang ginawarang papel pananaliksik.",
        "Previous": "Nakaraan",
        "Next": "Susunod",
        "Showing": "Ipinapakita",
        "of": "sa",
        "papers": "mga papel",
        "Loading Lundayang Marians...": "Ikinakarga ang Lundayang Marians...",
        "Our Vision": "Aming Bisyon",
        "Our Mission": "Aming Misyon",
        "MISSION & VISION": "MISYON AT BISYON",
        "A center of Marian academic excellence and digital scholarship where student-led research inspires innovation, integrity, and community-centered progress in Santa Maria, Laguna and beyond.": "Isang sentro ng kahusayang akademiko at dihital na karunungan ng mga Marian kung saan ang pananaliksik ng mga mag-aaral ay nagbibigay-inspirasyon sa makabagong ideya, integridad, at pag-unlad ng komunidad sa Santa Maria, Laguna at higit pa.",
        "To preserve, organize, and showcase approved student research of Sta. Maria (Laguna) Academy Inc. in a secure digital repository—empowering future Marian researchers with accessible references, fostering ethical scholarship, and cultivating critical inquiry.": "Upang ingatan, ayusin, at itampok ang mga naaprubahang pananaliksik ng mga mag-aaral ng Sta. Maria (Laguna) Academy Inc. sa isang ligtas na dihital na imbakan—na nagbibigay-lakas sa mga darating na mananaliksik na Marian sa pamamagitan ng madaling ma-access na sanggunian, pagtataguyod ng etikal na pag-aaral, at paglinang ng mapanuring pagsisiyasat.",
        "Admin Dashboard": "Dashboard ng Admin",
        "Total Papers": "Kabuuang Papel",
        "Website Visits": "Mga Bisita sa Website",
        "Paper Views": "Mga Pagtingin sa Papel",
        "Pending Approvals": "Naghihintay ng Pag-apruba",
        "Account Approvals": "Pag-apruba ng Account",
        "Approve": "Aprubahan",
        "Reject": "Tanggihan",
        "Pending": "Naghihintay",
        "Approved": "Naaprubahan",
        "Rejected": "Tinanggihan",
        "Quick Links": "Mabilis na Link",
        "Repository": "Imbakan",
        "View-only archive protecting Marian student intellectual property.": "View-only na arkibo na nagpoprotekta sa intelektwal na ari-arian ng mga mag-aaral na Marian.",
        "Explore Research Repository": "Galugarin ang Imbakan ng Pananaliksik",
        "The Cradle of Marian Scholarship": "Ang Duyan ng Karunungang Marian",
        "Current Password": "Kasalukuyang Password",
        "Enter your current and new password below.": "Ipasok ang iyong kasalukuyan at bagong password sa ibaba.",
        "Go Back": "Bumalik",
        "SEARCH FILTER": "FILTER NG PAGHAHANAP",
        "STEM": "STEM",
        "ABM": "ABM",
        "HUMSS": "HUMSS",
        "TVL": "TVL",
        "GAS": "GAS",
        "Science, Technology, Engineering, & Mathematics": "Agham, Teknolohiya, Inhenyeriya, at Matematika",
        "Accountancy, Business, & Management": "Akawntansi, Negosyo, at Pamamahala",
        "Humanities & Social Sciences": "Humanidades at Agham Panlipunan",
        "Technical-Vocational-Livelihood": "Teknikal-Bokasyonal-Pangkabuhayan",
        "General Academic Strand": "Pangkalahatang Akademikong Strand",
        "Abstract": "Buod (Abstract)",
        "Authors": "Mga May-akda",
        "Adviser": "Tagapayo",
        "Academic Year": "Taong Akademiko",
        "Strand": "Strand",
        "Research Type": "Uri ng Pananaliksik",
        "Subject Area": "Larangan ng Paksa",
        "Awards": "Mga Parangal",
        "Keywords": "Mga Susing Salita",
        "Citation": "Sitasyon",
        "Copy Citation": "Kopyahin ang Sitasyon",
        "Bookmark": "I-bookmark",
        "Bookmarked": "Naka-bookmark",
        "Download PDF": "I-download ang PDF",
        "Read Online": "Basahin Online",
        "Back to Home": "Bumalik sa Tahanan",
        "Back to Search": "Bumalik sa Paghahanap",
        "Sta. Maria (Laguna) Academy Inc.": "Sta. Maria (Laguna) Academy Inc.",
        "Brgy. Poblacion II, Santa Maria, Laguna": "Brgy. Poblacion II, Santa Maria, Laguna",
        "Digital Research Repository": "Dihital na Imbakan ng Pananaliksik",
        "Student ID": "ID ng Mag-aaral",
        "Admin ID": "ID ng Admin",
        "Office / Department": "Opisina / Departamento",
        "Admin Workspace": "Espasyo ng Admin",
        "Activity Log": "Talaan ng Aktibidad",
        "Overview": "Pangkalahatang-ideya",
        "Research Papers": "Mga Papel Pananaliksik",
        "Export CSV": "I-export ang CSV",
        "Approve All Pending": "Aprubahan Lahat ng Nakabinbin",
        "Privacy Policy": "Patakaran sa Privacy",
        "Terms & Conditions": "Mga Tuntunin at Kundisyon",
        "Effective Date": "Petsa ng Bisa",
        "Cookie Settings": "Mga Setting ng Cookie",
        "Cookie Preferences": "Mga Kagustuhan sa Cookie",
        "Essential Only": "Mahahalaga Lamang",
        "Accept All": "Tanggapin Lahat",
        "Cookies & Telemetry": "Cookies at Telemetriya",
        "Current choice": "Kasalukuyang pinili",
        "All cookies active": "Aktibo ang lahat ng cookie",
        "Always Active": "Laging Aktibo",
        "Optional": "Opsyonal",
        "Not yet selected": "Hindi pa napili",
        "Menu": "Menu",
        "SMLA Archive": "Arkibo ng SMLA",
        "Student": "Mag-aaral",
        "Admin": "Admin",
        "Essential Session Data": "Mahalagang Data ng Sesyon",
        "Keeps login authentication, account role, selected language, and your saved preference active.": "Pinapanatiling aktibo ang pag-log in, gampanin ng account, piniling wika, at ang iyong nai-save na kagustuhan.",
        "Campus Readership Telemetry": "Telemetriya ng Pagbabasa sa Kampus",
        "Records anonymized campus visits and research view counts for the Admin Dashboard—no third-party ad trackers.": "Itinatala ang hindi nakikilalang pagbisita at dami ng pagtingin sa pananaliksik para sa Admin Dashboard—walang third-party ad tracker.",
        "Essential cookies keep login sessions and language preferences active. Optional analytics help librarians track campus visits and research views—no third-party ad trackers.": "Pinapanatiling aktibo ng mahahalagang cookie ang sesyon ng pag-log in at wika. Ang opsyonal na analytics ay tumutulong sa mga librarian na subaybayan ang pagbisita at pagtingin sa pananaliksik—walang third-party ad tracker.",
        "Full Name": "Buong Pangalan",
        "Grade & Section": "Baitang at Seksyon",
        "Role": "Gampanin",
        "Email": "Email",
        "Save Changes": "I-save ang mga Pagbabago",
        "Current Password": "Kasalukuyang Password",
        "New Password": "Bagong Password",
        "Confirm New Password": "Kumpirmahin ang Bagong Password",
        "Update Password": "I-update ang Password",
        "Upload Research Paper": "I-upload ang Papel Pananaliksik",
        "Edit Research Paper": "I-edit ang Papel Pananaliksik",
        "Title": "Pamagat",
        "PDF Document": "Dokumentong PDF",
        "Submit Paper": "Isumite ang Papel",
        "Development Team": "Koponan ng Tagapag-unlad",
        "Meet the creators behind Lundayang Marians": "Kilalanin ang mga lumikha sa likod ng Lundayang Marians",
        "Frequently Asked Questions": "Mga Madalas Itanong (FAQ)",
        "Got questions? We've got answers.": "May mga tanong? Mayroon kaming mga sagot.",
        "Select Strand": "Pumili ng Strand",
        "Select Type": "Pumili ng Uri",
        "Select Academic Year": "Pumili ng Taong Akademiko",
        "Search papers, authors, keywords...": "Maghanap ng mga papel, may-akda, susing salita...",
        "All Academic Years": "Lahat ng Taong Akademiko",
        "My Bookmarks": "Aking Mga Naka-bookmark",
        "You haven't bookmarked any research papers yet.": "Wala ka pang nai-bookmark na papel pananaliksik.",
        "Browse Papers": "Mag-browse ng mga Papel",
        "Remove": "Alisin",
        "View Paper": "Tingnan ang Papel",
        "Search Results": "Mga Resulta ng Paghahanap",
        "Enter your student credentials to continue": "Ipasok ang iyong student credentials upang magpatuloy",
        "Password": "Password",
        "Don't have an account?": "Wala pang account?",
        "Already have an account?": "Mayroon nang account?",
        "Create an Account": "Likhain ang Account",
        "Join the Lundayang Marians research community": "Sumali sa komunidad ng pananaliksik ng Lundayang Marians",
        "Confirm Password": "Kumpirmahin ang Password",
        "Email Address": "Email Address",
        "Student ID or Email": "Student ID o Email",
        "Forgot Password?": "Nakalimutan ang Password?",
        "Enter your email address to receive a password reset link.": "Ipasok ang iyong email address upang makatanggap ng link sa pag-reset ng password.",
        "Send Reset Link": "Ipadala ang Link sa Pag-reset",
        "Back to Log In": "Bumalik sa Log In",
        "Reset Password": "I-reset ang Password",
        "Enter your new password below.": "Ipasok ang iyong bagong password sa ibaba.",
        "Set New Password": "I-set ang Bagong Password",
        "Verified": "Na-verify",
        "Verification Pending": "Naghihintay ng Pag-verify",
        "Unverified": "Hindi Pa Na-verify",
        "Verification email sent to": "Naipadala ang email sa pag-verify sa",
        "Reverted to old email until verified.": "Mananatili sa lumang email hanggang ma-verify.",
        "Verify Your Email Address": "I-verify ang Iyong Email Address",
        "Please check your inbox and click the link to confirm your email change.": "Paki-check ang iyong inbox at i-click ang link upang kumpirmahin ang pagbabago ng email.",
        "Or enter 8-digit verification code:": "O ipasok ang 8-digit na code sa pag-verify:",
        "Verify Code": "I-verify ang Code",
        "Resend Verification Email": "Muling Ipadala ang Email",
        "I've Verified My Email": "Na-verify Ko Na Ang Aking Email",
        "Verification Details": "Mga Detalye ng Pag-verify",
        "Saving Changes...": "Inipon ang mga Pagbabago...",
        "Sending Email...": "Ipinapadala ang Email...",
        "Verifying...": "Bina-verify...",

        # Strand full names
        "Humanities and Social Sciences": "Humanidades at Agham Panlipunan",
        "Accountancy, Business, and Management": "Akawntansi, Negosyo, at Pamamahala",
        "Science, Technology, Engineering, and Mathematics": "Agham, Teknolohiya, Inhenyeriya, at Matematika",
        "HUMANITIES AND SOCIAL SCIENCE": "HUMANITIES AND SOCIAL SCIENCE",
        "ACCOUNTANCY AND BUSINESS MANAGEMENT": "ACCOUNTANCY AND BUSINESS MANAGEMENT",
        "SCIENCE, TECHNOLOGY, ENGINEERING, AND MATHEMATICS": "SCIENCE, TECHNOLOGY, ENGINEERING, AND MATHEMATICS",

        # Homepage descriptions
        "Lundayang Marians": "Lundayang Marians",
        "Santa Maria (Laguna) Academy Inc.": "Santa Maria (Laguna) Academy Inc.",
        "is the web-based research repository of": "ay ang web-based na imbakan ng pananaliksik ng",
        "envisioned as the cradle of Marian scholarship. The name combines \"Lundayan\", meaning cradle or focal point, with \"Marians\", the collective identity of the academy's students. This platform centralizes academic outputs, offering a simple interface and organized categories for easy access and exploration.": "na pinaniniwalaang duyan ng akademikong kahusayan ng mga Marian. Ang pangalan ay pinagsamang \"Lundayan\", na nangangahulugang duyan o sentro, at \"Marians\", ang kolektibong pagkakakilanlan ng mga mag-aaral ng akademya. Ang platapormang ito ay nagpapatupad ng sentralisadong mga akademikong gawa, na nag-aalok ng simpleng interface at organisadong mga kategorya para sa madaling pag-access at paggalugad.",
        "By preserving research in a digital archive,": "Sa pamamagitan ng pag-iingat ng pananaliksik sa isang dihital na arkibo,",
        "fosters collaboration, supports future studies, and strengthens the Marian community's commitment to academic excellence. It serves not only as a repository but also as a symbol of innovation and inclusivity, ensuring that the scholarly contributions of Marians remain accessible and impactful for years to come.": "ay nagtataguyod ng pagtutulungan, sumusuporta sa mga darating na pag-aaral, at nagpapatibay sa kompromiso ng komunidad ng Marian sa akademikong kahusayan. Naglilingkod ito hindi lamang bilang isang imbakan kundi bilang simbolo rin ng makabagong ideya at pagiging kabilang, na tinitiyak na ang mga akademikong ambag ng mga Marian ay mananatiling accessible at may epekto sa mga darating na taon.",

        # Research Recognition
        "RESEARCH RECOGNITION": "PAGKILALA SA PANANALIKSIK",
        "This Research has been officially Recognized by the Municipality of Santa Maria, Laguna": "Ang Pananaliksik na ito ay Opisyal na Kinilala ng Bayan ng Santa Maria, Laguna",
        "SK Chairman Angel Mangundayao of the Municipality of Santa Maria, Laguna": "SK Chairman Angel Mangundayao ng Bayan ng Santa Maria, Laguna",
        "proudly acknowledges the outstanding efforts of the student researchers of Santa Maria (Laguna) Academy, INC., Gabrielle A. Dimatatac, Bridgette S. Panaligan, Mark Andrew Y. Montales, Fiona Sheryn A. Hernandez, Kristel Anne Nicole L. Jaen, Godwel Ivan D. Razon, and Fatima Victoria I. Valentino, for their innovative study entitled": "buong pagmamaking kinikilala ang natatanging pagsisikap ng mga mag-aaral na mananaliksik ng Santa Maria (Laguna) Academy, INC., na sina Gabrielle A. Dimatatac, Bridgette S. Panaligan, Mark Andrew Y. Montales, Fiona Sheryn A. Hernandez, Kristel Anne Nicole L. Jaen, Godwel Ivan D. Razon, at Fatima Victoria I. Valentino, para sa kanilang makabagong pag-aaral na may pamagat na",
        "Special recognition is also extended to their Research Adviser, Ms. Maureen L. Cruz, whose guidance and expertise provided the necessary direction and support in the completion of this project.": "Ipinapaabot din ang espesyal na pagkilala sa kanilang Tagapayo sa Pananaliksik na si Gng. Maureen L. Cruz, na ang patnubay at dalubhasa ay nagbigay ng kinakailangang direksyon at suporta sa pagkumpleto ng proyektong ito.",
        "This initiative reflects the commitment of the youth of Santa Maria Academy to environmental responsibility and sustainable development. It also demonstrates the vital role of student-led innovation in creating solutions that can be adopted by the barangay and the wider community for the benefit of the people of Santa Maria, Laguna.": "Ang inisyatibong ito ay nagpapakita ng kompromiso ng kabataan ng Santa Maria Academy sa responsibilidad sa kapaligiran at napapanatiling pag-unlad. Ipinapakita rin nito ang mahalagang gampanin ng makabagong ideya na pinangungunahan ng mag-aaral sa paglikha ng mga solusyon na magagamit ng barangay at ng buong komunidad para sa kapakinabangan ng mga mamamayan ng Santa Maria, Laguna.",

        # Best in Research
        "Recognizing Outstanding Research Achievements in Recent Years": "Pagkilala sa mga Natatanging Tagumpay sa Pananaliksik sa mga Nakalipas na Taon",

        # Strand Page
        "Research Papers": "Mga Papel Pananaliksik",
        "Year": "Taon",
        "No Research Papers Found": "Walang Natagpuang Papel Pananaliksik",
        "We couldn't find any papers matching your search parameters or filter criteria.": "Wala kaming mahanap na mga papel na tumutugma sa iyong mga parameter ng paghahanap o pamantayan sa filter.",
        "Reset Filters": "I-reset ang mga Filter",
        "A scholarly research paper authored by": "Isang akademikong papel pananaliksik na isinulat ni",
        "under the": "sa ilalim ng",
        "strand.": "strand.",
        "Humanities and Social Sciences (HUMSS)": "Humanities and Social Sciences (HUMSS)",
        "is the branch of knowledge that studies human beings, their culture, society, behavior, relationships, and experiences. It combines the humanities, which focus on human culture, values, history, literature, philosophy, and the arts, with the social sciences, which examine how individuals and groups interact within society through disciplines such as sociology, psychology, economics, political science, and anthropology.": "ay ang sangay ng kaalaman na nag-aaral sa mga tao, sa kanilang kultura, lipunan, pag-uugali, relasyon, at mga karanasan. Pinagsasama nito ang humanidades, na nakatuon sa kultura ng tao, mga halaga, kasaysayan, panitikan, pilosopiya, at mga sining, kasama ang agham panlipunan, na nagsusuri kung paano nakikipag-ugnayan ang mga indibidwal at grupo sa loob ng lipunan sa pamamagitan ng mga disiplina tulad ng sosyolohiya, sikolohiya, ekonomiks, agham pampulitika, at antropolohiya.",
        "Accountancy, Business, and Management (ABM)": "Accountancy, Business, and Management (ABM)",
        "is a Senior High School strand that prepares students for careers in business, entrepreneurship, accounting, marketing, finance, and management. It develops skills in leadership, problem-solving, communication, and decision-making, making it ideal for students who want to pursue business-related courses or start their own businesses.": "ay isang Senior High School strand na naghahanda sa mga mag-aaral para sa mga karera sa negosyo, entrepreneurship, akawntansi, marketing, pinansya, at pamamahala. Nililinang nito ang mga kasanayan sa pamumuno, paglutas ng problema, komunikasyon, at paggawa ng desisyon, na ginagawang perpekto para sa mga mag-aaral na gustong kumuha ng mga kursong nauugnay sa negosyo o magsimula ng kanilang sariling negosyo.",
        # Developers Page
        "THE DEVELOPERS": "MGA TAGABUO",
        "THE ADVISER": "ANG TAGAPAYO",
        "The developers/researchers extend their sincere appreciation to": "Ang mga tagabuo/mananaliksik ay taos-pusong nagpapasalamat kay",
        ", their research adviser, for her invaluable guidance, unwavering support, and encouragement throughout the conduct of the study. Her expertise, patience, and constructive feedback greatly contributed to the successful completion of the research. As one of the key individuals behind the realization of Lundayang Marians, her guidance and dedication played an essential role in bringing the project to fruition.": ", ang kanilang tagapayo sa pananaliksik, para sa kanyang mahalagang patnubay, walang matagag na suporta, at pagpapalakas ng loob sa buong panahon ng pag-aaral. Ang kanyang dalubhasa, pasensya, at nakabubuo na puna ay malaki ang naiambag sa matagumpay na pagkumpleto ng pananaliksik. Bilang isa sa mga pangunahing indibidwal sa likod ng pagsasakatuparan ng Lundayang Marians, ang kanyang patnubay at dedikasyon ay nagkaroon ng mahalagang gampanin sa pagtatagumpay ng proyekto.",

        # Detail Page labels
        "RESEARCH TITLE": "PAMAGAT NG PANANALIKSIK",
        "AUTHOR": "MAY-AKDA",
        "ADVISER": "TAGAPAYO",
        "ACADEMIC YEAR": "TAONG AKADEMIKO",
        "RESEARCH TYPE": "URI NG PANANALIKSIK",
        "SUBJECT AREA": "LARANGAN NG PAKSA",
        "AWARDS": "MGA PARANGAL",
        "KEYWORDS": "MGA SUSING SALITA",
        "ABSTRACT": "BUOD (ABSTRACT)",
        "See More": "Tingnan Pa",
        "See Less": "Tingnan Nang Kaunti",
        "HOW TO CITE (APA 7th)": "PAANO ISITE (APA 7th)",
        "Copy APA": "Kopyahin ang APA",
        "Copied!": "Kinopya!",
        "PDF COPY": "KOPYA NG PDF",
        "EDIT": "I-EDIT",
        "DELETE": "BURAHIN",
        "Researches you might like:": "Mga pananaliksik na maaari mong magustuhan:",
        "Streaming secure document copy...": "Tumatanggap ng ligtas na kopya ng dokumento...",

        # Admin Upload Form
        "Edit Research Paper": "I-edit ang Papel Pananaliksik",
        "Upload Research Paper": "I-upload ang Papel Pananaliksik",
        "Research Title": "Pamagat ng Pananaliksik",
        "Research Abstract": "Buod ng Pananaliksik (Abstract)",
        "Strand Category": "Kategorya ng Strand",
        "Academic Year": "Taong Akademiko",
        "Research Type": "Uri ng Pananaliksik",
        "Subject Area": "Larangan ng Paksa",
        "Authors / Researchers (Comma Separated)": "Mga May-akda / Mananaliksik (Nakahati sa Koma)",
        "Research Adviser": "Tagapayo sa Pananaliksik",
        "Awards / Recognition (Optional)": "Mga Parangal / Pagkilala (Opsyonal)",
        "Keywords / Tags (Comma Separated)": "Mga Susing Salita / Tag (Nakahati sa Koma)",
        "Upload Research PDF Copy": "I-upload ang Kopya ng PDF ng Pananaliksik",
        "Update Research Paper": "I-update ang Papel Pananaliksik",
        "Upload & Register Research Paper": "I-upload at I-rehistro ang Papel Pananaliksik",

        # FAQ Page
        "FREQUENTLY ASKED QUESTIONS": "MGA MADALAS ITANONG (FAQ)",
        "What is Lundayang Marians?": "Ano ang Lundayang Marians?",
        "Lundayang Marians is a school-based digital research repository developed by Santa Maria (Laguna) Academy Inc. It serves as a centralized online archive that stores, organizes, preserves, and provides access to approved student research papers. The repository allows users to conveniently search and view previous studies while ensuring that valuable academic outputs are preserved for future generations of students.": "Ang Lundayang Marians ay isang pampaaralang dihital na imbakan ng pananaliksik na binuo ng Santa Maria (Laguna) Academy Inc. Naglilingkod ito bilang isang sentralisadong online archive na nag-iimbak, nag-aayos, nagpapanatili, at nagbibigay ng access sa mga naaprubahang papel pananaliksik ng mga mag-aaral. Pinapayagan ng imbakan ang mga gumagamit na maginhawang maghanap at tumingin ng mga nakaraang pag-aaral habang tinitiyak na ang mga mahalagang akademikong gawa ay naingatan para sa mga darating na henerasyon ng mga mag-aaral.",
        "What is the main purpose of the repository?": "Ano ang pangunahing layunin ng imbakan?",
        "The primary purpose of Lundayang Marians is to preserve student research outputs and make them more accessible to the school community. It also aims to support future researchers by providing reliable academic references, reducing the risk of lost or damaged printed copies, encouraging quality research, and promoting a stronger culture of research within the institution.": "Ang pangunahing layunin ng Lundayang Marians ay upang ingatan ang mga nagawang pananaliksik ng mga mag-aaral at gawin itong mas madaling ma-access ng komunidad ng paaralan. Layunin din nitong suportahan ang mga darating na mananaliksik sa pamamagitan ng pagbibigay ng maaasahang mga akademikong sanggunian, pagbawas sa panganib ng mawala o masirang nakalimbag na kopya, pagtataguyod ng de-kalidad na pananaliksik, at pagpapalakas ng kultura ng pananaliksik sa loob ng institusyon.",
        "Who can access the repository?": "Sino ang makaka-access sa imbakan?",
        "The repository is intended for authorized users of Santa Maria (Laguna) Academy Inc., including students, teachers, research advisers, librarians, and designated school administrators. Access to certain features may depend on the user’s account and the policies implemented by the school.": "Ang imbakan ay nakalaan para sa mga awtorisadong gumagamit ng Santa Maria (Laguna) Academy Inc., kabilang ang mga mag-aaral, guro, tagapayo sa pananaliksik, tagapamahala ng aklatan, at mga itinalagang administrador ng paaralan. Ang pag-access sa ilang mga tampok ay maaaring nakadepende sa account ng gumagamit at sa mga patakarang ipinapatupad ng paaralan.",
        "What types of research papers are available in the repository?": "Anong mga uri ng papel pananaliksik ang magagamit sa imbakan?",
        "Only approved student research papers completed at Santa Maria (Laguna) Academy Inc. are included in the repository. These may consist of quantitative, qualitative, mixed-method, experimental, descriptive, and other research studies that have successfully passed the school’s research requirements.": "Tanging ang mga naaprubahang papel pananaliksik ng mag-aaral na nakumpleto sa Santa Maria (Laguna) Academy Inc. ang kasama sa imbakan. Maaari itong buuin ng kuwantitatibo, kuwalitatibo, pinagsamang pamamaraan (mixed-method), eksperimental, deskriptibo, at iba pang pag-aaral sa pananaliksik na matagumpay na nakapasa sa mga kinakailangan sa pananaliksik ng paaralan.",
        "Why does the repository only contain student research?": "Bakit tanging pananaliksik lamang ng mag-aaral ang nilalaman ng imbakan?",
        "The repository was specifically developed to preserve and showcase the academic work of students. By focusing solely on student research, the system provides a dedicated collection that future students can use as references while highlighting the research achievements of the school’s learners.": "Ang imbakan ay partikular na binuo upang ingatan at itampok ang akademikong gawa ng mga mag-aaral. Sa pamamagitan ng pagtuon lamang sa pananaliksik ng mag-aaral, ang sistema ay nagbibigay ng nakalaang koleksyon na magagamit ng mga darating na mag-aaral bilang sanggunian habang binibigyang-diin ang mga tagumpay sa pananaliksik ng mga mag-aaral ng paaralan.",
        "How can I search for a research paper?": "Paano ako makakapaghanap ng papel pananaliksik?",
        "Users can search for research papers using various search options, including the research title, author’s name, adviser, strand, academic year, subject area, or keywords. These search features allow users to quickly locate studies related to their research interests.": "Maaaring maghanap ang mga gumagamit ng mga papel pananaliksik gamit ang iba't ibang opsyon sa paghahanap, kabilang ang pamagat ng pananaliksik, pangalan ng may-akda, tagapayo, strand, taong akademiko, larangan ng paksa, o mga susing salita. Ang mga tampok na ito ay nagbibigay-daan sa mga gumagamit na mabilis na mahanap ang mga pag-aaral na nauugnay sa kanilang interes sa pananaliksik.",
        "Can I browse research papers by category?": "Maaari ko bang i-browse ang mga papel pananaliksik ayon sa kategorya?",
        "Yes. Research papers are organized into categories such as academic year, strand, research type, and subject area. This organization allows users to explore studies more efficiently without needing to know the exact title of a paper.": "Oo. Ang mga papel pananaliksik ay nakaayos sa mga kategorya tulad ng taong akademiko, strand, uri ng pananaliksik, at larangan ng paksa. Ang organisasyong ito ay nagbibigay-daan sa mga gumagamit na galugarin ang mga pag-aaral nang mas mahusay nang hindi kinakailangang malaman ang eksaktong pamagat ng papel.",
        "Can I download research papers?": "Maaari ko bang i-download ang mga papel pananaliksik?",
        "No. Research papers are available for viewing only. Downloading is restricted to protect the intellectual property rights of student authors and to minimize plagiarism and unauthorized distribution of research outputs.": "Hindi. Ang mga papel pananaliksik ay magagamit lamang para sa pagtingin (view-only). Ang pag-download ay nakarimata upang protektahan ang mga karapatan sa intelektwal na ari-arian ng mga mag-aaral na may-akda at upang mabawasan ang plagiarism at hindi awtorisadong pamamahagi ng mga gawa sa pananaliksik.",
        "Why are downloads not allowed?": "Bakit hindi pinapayagan ang pag-download?",
        "Restricting downloads helps ensure that student research is used responsibly. It protects the originality of academic work, discourages plagiarism, and respects the rights of the student researchers who authored the studies.": "Ang paghihigpit sa pag-download ay tumutulong upang matiyak na ang pananaliksik ng mag-aaral ay ginagamit nang may responsibilidad. Pinoprotektahan nito ang orihinalidad ng akademikong gawa, pinipigilan ang plagiarism, at iginagalang ang mga karapatan ng mga mag-aaral na mananaliksik na sumulat ng mga pag-aaral.",
        "How are research papers submitted to the repository?": "Paano isinusumite ang mga papel pananaliksik sa imbakan?",
        "Only the final, approved versions of student research papers are submitted to the repository through the designated school office or repository administrator. Papers are reviewed before they are uploaded to ensure that they meet the school’s submission requirements.": "Tanging ang mga pinal at naaprubahang bersyon ng mga papel pananaliksik ng mag-aaral ang isinusumite sa imbakan sa pamamagitan ng itinalagang tanggapan ng paaralan o administrador ng imbakan. Ang mga papel ay sinusuri bago i-upload upang matiyak na natutugunan nito ang mga kinakailangan sa pagsusumite ng paaralan.",
        "Who manages the repository?": "Sino ang namamahala sa imbakan?",
        "The repository is managed by authorized school personnel, such as the research coordinator, librarian, or designated system administrator. They are responsible for uploading approved research papers, maintaining the database, ensuring system security, and assisting users when necessary.": "Ang imbakan ay pinamamahalaan ng mga awtorisadong tauhan ng paaralan, tulad ng tagapag-ugnay sa pananaliksik, tagapamahala ng aklatan, o itinalagang administrador ng sistema. Sila ang responsable sa pag-upload ng mga naaprubahang papel pananaliksik, pagpapanatili ng database, pagtiyak sa seguridad ng sistema, at pagtulong sa mga gumagamit kapag kinakailangan.",
        "How does the repository help students?": "Paano tumutulong ang imbakan sa mga mag-aaral?",
        "The repository provides students with convenient access to previous research studies that can serve as references during the preparation of research proposals, literature reviews, and final papers. It also helps students identify research gaps, avoid duplication of topics, and improve the quality of their own research.": "Ang imbakan ay nagbibigay sa mga mag-aaral ng maginhawang access sa mga nakaraang pag-aaral sa pananaliksik na magagamit bilang mga sanggunian sa panahon ng paghahanda ng mga panukalang pananaliksik, pagsusuri ng kaugnay na literatura, at mga pinal na papel. Tumutulong din ito sa mga mag-aaral na matukoy ang mga kakulangan sa pananaliksik, maiwasan ang pag-uulit ng mga paksa, at mapabuti ang kalidad ng kanilang sariling pananaliksik.",
        "How does the repository help teachers and research advisers?": "Paano tumutulong ang imbakan sa mga guro at tagapayo sa pananaliksik?",
        "Teachers and research advisers can use the repository to guide students in selecting research topics, recommend relevant previous studies, evaluate research trends, and monitor the development of student research within the school.": "Maaaring gamitin ng mga guro at tagapayo sa pananaliksik ang imbakan upang gabayan ang mga mag-aaral sa pagpili ng mga paksa sa pananaliksik, magrekomenda ng mga nauugnay na nakaraang pag-aaral, suriin ang mga uso sa pananaliksik, at subaybayan ang pag-unlad ng pananaliksik ng mag-aaral sa loob ng paaralan.",
        "Is the information stored in the repository secure?": "Ligtas ba ang impormasyong nakaimbak sa imbakan?",
        "Yes. The repository includes security measures such as user authentication, controlled access, and regular system maintenance to protect both research documents and user information. These measures help ensure that the repository remains secure and reliable.": "Oo. Ang imbakan ay naglalaman ng mga hakbang sa seguridad tulad ng awtentikasyon ng gumagamit, kontroladong access, at regular na pagpapanatili ng sistema upang protektahan ang parehong mga dokumento ng pananaliksik at impormasyon ng gumagamit. Ang mga hakbang na ito ay tumutulong upang matiyak na ang imbakan ay mananatiling ligtas at maaasahan.",
        "How does the repository protect student authors?": "Paano pinoprotektahan ng imbakan ang mga mag-aaral na may-akda?",
        "Each research paper clearly identifies its authors and advisers. Users are reminded to properly cite all referenced works and to comply with the school’s policies on academic honesty, intellectual property, and responsible use of research materials.": "Malinaw na tinutukoy ng bawat papel pananaliksik ang mga may-akda at tagapayo nito. Ang mga gumagamit ay pinapaalalahanan na wastong isite ang lahat ng isinangguni na gawa at sumunod sa mga patakaran ng paaralan sa akademikong katapatan, intelektwal na ari-arian, at responsableng paggamit ng mga materyales sa pananaliksik.",
        "Can research papers be edited after they are uploaded?": "Maaari bang i-edit ang mga papel pananaliksik pagkatapos ma-upload?",
        "If errors are discovered or updates are required, corrections may only be made by the repository administrator after obtaining approval from the appropriate school authorities. Unauthorized users cannot modify uploaded research papers.": "Kung matuklasan ang mga pagkakamali o kailangan ng mga update, ang mga pagwawasto ay maaari lamang isagawa ng administrador ng imbakan pagkatapos makakuha ng pag-apruba mula sa angkop na mga awtoridad ng paaralan. Ang mga hindi awtorisadong gumagamit ay hindi makakapagbago ng mga na-upload na papel pananaliksik.",
        "What should I do if I cannot find the research paper I need?": "Ano ang dapat kong gawin kung hindi ko mahanap ang kailangan kong papel pananaliksik?",
        "If you are unable to locate a specific research paper, you may contact the repository administrator, school librarian, or research coordinator for assistance. They can verify whether the research has been archived or if there are restrictions affecting its availability.": "Kung hindi mo mahanap ang isang partikular na papel pananaliksik, maaari kang makipag-ugnayan sa administrador ng imbakan, tagapamahala ng aklatan, o tagapag-ugnay sa pananaliksik para sa tulong. Maaari nilang kumpirmahin kung ang pananaliksik ay nai-archive o kung may mga paghihigpit na nakakaapekto sa availability nito.",
        "Can I use the research papers as references for my own study?": "Maaari ko bang gamitin ang mga papel pananaliksik bilang sanggunian sa aking sariling pag-aaral?",
        "Yes. Research papers in the repository are intended to serve as academic references for future student researchers. However, users must properly cite all sources and follow the school’s academic integrity and plagiarism policies.": "Oo. Ang mga papel pananaliksik sa imbakan ay nakalaan upang magsilbing akademikong sanggunian para sa mga darating na mag-aaral na mananaliksik. Gayunpaman, kailangang wastong isite ng mga gumagamit ang lahat ng pinagmulan at sundin ang akademikong integridad at mga patakaran sa plagiarism ng paaralan.",
        "Why is preserving student research important?": "Bakit mahalaga ang pagpapanatili ng pananaliksik ng mag-aaral?",
        "Student research represents valuable academic knowledge and reflects the efforts and achievements of learners. Preserving these studies ensures that they remain available for future students, prevents the loss of important academic work, and contributes to the continuous improvement of research within the school.": "Ang pananaliksik ng mag-aaral ay kumakatawan sa mahalagang akademikong kaalaman at nagpapakita ng mga pagsisikap at tagumpay ng mga mag-aaral. Ang pagpapanatili ng mga pag-aaral na ito ay nagtitiyak na mananatili silang magagamit para sa mga darating na mag-aaral, maiwasan ang pagkawala ng mahalagang akademikong gawa, at mag-ambag sa patuloy na pagpapabuti ng pananaliksik sa paaralan.",
        "What makes Lundayang Marians different from printed research archives?": "Ano ang ginagawang iba ng Lundayang Marians sa mga nakalimbag na arkibo ng pananaliksik?",
        "Unlike traditional printed archives, Lundayang Marians provides a searchable digital platform that allows users to locate research papers quickly using keywords, categories, filters, and metadata. It also reduces the need to manually browse physical copies while helping preserve research documents from deterioration or loss.": "Hindi tulad ng mga tradisyunal na nakalimbag na arkibo, ang Lundayang Marians ay nagbibigay ng nahanap na dihital na plataporma na nagpapahintulot sa mga gumagamit na mabilis na mahanap ang mga papel pananaliksik gamit ang mga susing salita, kategorya, filter, at metadata. Binabawasan din nito ang pangangailangang manu-manong mag-browse ng mga pisikal na kopya habang tumutulong na ingatan ang mga dokumento sa pananaliksik mula sa pagkasira o pagkawala.",
        "How does Lundayang Marians contribute to the school’s research culture?": "Paano nag-aambag ang Lundayang Marians sa kultura ng pananaliksik ng paaralan?",
        "By making student research more accessible, organized, and preserved, Lundayang Marians encourages students to conduct meaningful studies, promotes collaboration and academic excellence, supports evidence-based learning, and inspires future researchers to build upon previous student research while maintaining ethical research practices.": "Sa pamamagitan ng paggawa sa pananaliksik ng mag-aaral na mas accessible, organisado, at naingatan, ang Lundayang Marians ay naghihikayat sa mga mag-aaral na mag-aral ng mga makabuluhang pananaliksik, nagtataguyod ng pagtutulungan at akademikong kahusayan, sumusuporta sa pag-aaral na batay sa ebidensya, at nagbibigay-inspirasyon sa mga darating na mananaliksik na magtayo sa mga nakaraang pananaliksik ng mag-aaral habang pinapanatili ang mga etikal na kasanayan sa pananaliksik."
    }
}

# Helper to format author name into APA 7th edition (Surname, Initial(s))
def format_apa_author(author_name):
    if not author_name:
        return ""
    name = author_name.strip()
    # Handle if name is already "Surname, Given..."
    if ',' in name:
        parts = name.split(',', 1)
        surname = parts[0].strip()
        given = parts[1].strip().split()
        initials = []
        for p in given:
            clean = p.replace('.', '').strip()
            if clean:
                initials.append(f"{clean[0].upper()}.")
        initials_str = " ".join(initials)
        return f"{surname}, {initials_str}" if initials_str else surname

    parts = name.split()
    if len(parts) == 1:
        return parts[0]
    surname = parts[-1]
    given_parts = parts[:-1]
    initials = []
    for p in given_parts:
        clean = p.replace('.', '').strip()
        if clean:
            initials.append(f"{clean[0].upper()}.")
    initials_str = " ".join(initials)
    if initials_str:
        return f"{surname}, {initials_str}"
    return surname

# Helper to generate APA 7th citation object (plain text & HTML)
def generate_apa_citation(paper):
    if not paper:
        return {"plain": "", "html": ""}
    
    authors = paper.get('authors', [])
    if isinstance(authors, str):
        authors = [a.strip() for a in authors.split(',') if a.strip()]
        
    formatted_authors = [format_apa_author(a) for a in authors if a]
    
    if not formatted_authors:
        authors_str = "Santa Maria (Laguna) Academy Inc."
    elif len(formatted_authors) == 1:
        authors_str = formatted_authors[0]
    elif len(formatted_authors) == 2:
        authors_str = f"{formatted_authors[0]}, & {formatted_authors[1]}"
    elif len(formatted_authors) <= 20:
        authors_str = ", ".join(formatted_authors[:-1]) + f", & {formatted_authors[-1]}"
    else:
        authors_str = ", ".join(formatted_authors[:19]) + f", ... {formatted_authors[-1]}"
        
    year = str(paper.get('academic_year', '')).strip()
    year_str = f"({year})." if year else "(n.d.)."
    
    # Title in proper case
    title = str(paper.get('title', '')).strip()
    if title.isupper():
        title = title.title()
    if title and not title.endswith(('.', '?', '!')):
        title += '.'
        
    paper_id = paper.get('id', '')
    url = f"https://lundayang-marians.vercel.app/paper/{paper_id}" if paper_id else "https://lundayang-marians.vercel.app/"
    source = "Lundayang Marians, Santa Maria (Laguna) Academy Inc."
    
    plain_citation = f"{authors_str} {year_str} {title} {source} {url}"
    html_citation = f'{authors_str} {year_str} {title} <i>{source}</i> <a href="{url}" target="_blank" class="apa-link">{url}</a>'
    
    return {"plain": plain_citation, "html": html_citation}

def validate_password_strength(password):
    """Enforce strong password rules: >=8 chars, upper, lower, and digit."""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not re.search(r"[A-Z]", password):
        return False, "Password must include at least one uppercase letter."
    if not re.search(r"[a-z]", password):
        return False, "Password must include at least one lowercase letter."
    if not re.search(r"\d", password):
        return False, "Password must include at least one number."
    return True, None


COOKIE_CONSENT_NAME = "lm_cookie_consent"


def get_style_version():
    """Return mtime-based version query parameter for style.css cache-busting."""
    try:
        return str(int(os.path.getmtime(os.path.join(BASE_DIR, 'static', 'css', 'style.css'))))
    except OSError:
        return "1"


def get_cookie_consent():
    """Return saved cookie consent ('all', 'essential') or None if undecided."""
    val = (request.cookies.get(COOKIE_CONSENT_NAME) or "").strip().lower()
    return val if val in ("all", "essential") else None


def has_analytics_consent():
    """Only record non-admin usage analytics when explicitly accepted."""
    return not is_admin_session() and get_cookie_consent() == "all"


def get_or_create_visitor_token():
    """Return a stable session-scoped visitor identifier for site visit metrics."""
    token = session.get('visitor_id')
    if not token:
        token = uuid.uuid4().hex
        session['visitor_id'] = token
    return token


def get_pending_approvals_count():
    """Return count of pending user signups for admin navigation badge."""
    if not supabase or session.get('role') != 'admin':
        return 0
    try:
        res = supabase.table("profiles").select("id", count="exact").eq("status", "pending").execute()
        if hasattr(res, 'count') and res.count is not None:
            return res.count
        return len(res.data or [])
    except Exception:
        return 0


def record_paper_view(paper_id):
    """Record a research paper detail view in Supabase analytics."""
    if not supabase or not paper_id or not has_analytics_consent():
        return
    try:
        supabase.table("paper_views").insert({
            "paper_id": paper_id,
            "user_id": (session.get('user') or {}).get('id'),
            "viewer_token": get_or_create_visitor_token(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as e:
        print("Analytics paper_view error:", e)


@app.before_request
def track_site_visit():
    """Log page visits for the Admin Dashboard without interrupting page rendering."""
    if not supabase or request.method != 'GET':
        return
    if not has_analytics_consent() or request.path.startswith(('/static', '/api', '/admin')):
        return
    if request.endpoint in (None, 'static', 'set_language', 'stream_pdf', 'search_suggestions', 'logout'):
        return
    if request.headers.get('Purpose') == 'prefetch' or request.headers.get('Sec-Purpose') == 'prefetch':
        return

    try:
        visitor_token = get_or_create_visitor_token()
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        supabase.table("site_visits").insert({
            "visitor_token": visitor_token,
            "visit_date": today_str,
            "path": request.path[:255],
            "user_id": (session.get('user') or {}).get('id'),
        }).execute()
    except Exception as e:
        print("Analytics site_visit error:", e)


def _build_nav_user():
    """Return concise signed-in user identity metadata for the navigation chip & dropdown."""
    user = session.get('user')
    if not user:
        return None
    full_name = (user.get('name') or '').strip()
    student_id = (user.get('student_id') or '').strip()
    email = (user.get('email') or '').strip()
    role_key = session.get('role') or 'student'
    display_source = full_name or student_id or (email.split('@')[0] if '@' in email else 'User')
    parts = [p for p in re.split(r'\s+', display_source) if p]
    if len(parts) >= 2:
        initials = (parts[0][0] + parts[-1][0]).upper()
        short_display = f"{parts[0]} {parts[-1][0]}." if full_name else display_source
    else:
        initials = display_source[:2].upper()
        short_display = display_source
    if len(short_display) > 18:
        short_display = f"{short_display[:17]}…"
    return {
        "full_name": full_name or display_source,
        "display": short_display,
        "initials": initials,
        "student_id": student_id,
        "role_label": "Admin" if role_key == 'admin' else "Student",
        "is_admin": role_key == 'admin',
    }


@app.context_processor
def inject_translations():
    lang = session.get('lang', 'en')
    def t(key):
        if lang == 'tl' and key in TRANSLATIONS.get('tl', {}):
            return TRANSLATIONS['tl'][key]
        return key
    admin_active = is_admin_session()
    return dict(
        t=t,
        generate_apa_citation=generate_apa_citation,
        mission_vision=MISSION_VISION,
        standard_research_types=STANDARD_RESEARCH_TYPES,
        pending_approvals_count=get_pending_approvals_count(),
        current_endpoint=request.endpoint or '',
        is_admin=admin_active,
        portal_home_url=url_for(default_portal_endpoint()),
        cookie_consent=get_cookie_consent(),
        asset_version=get_style_version(),
        nav_user=_build_nav_user(),
    )

@app.route('/set-language/<lang>')
def set_language(lang):
    if lang in ['en', 'tl']:
        session['lang'] = lang
    referrer = request.referrer
    if referrer:
        return redirect(referrer)
    return redirect(url_for(default_portal_endpoint()))


@app.route('/api/cookie-consent', methods=['POST'])
def set_cookie_consent():
    """Save visitor cookie preference ('all' or 'essential') and apply analytics telemetry rules."""
    data = request.get_json(silent=True) or request.form
    choice = (data.get('consent') or '').strip().lower()
    if choice not in ('all', 'essential'):
        return jsonify({"success": False, "error": "Invalid cookie preference."}), 400

    prev_consent = get_cookie_consent()
    if choice == 'essential':
        session.pop('visitor_id', None)
    elif supabase and not is_admin_session() and prev_consent != 'all':
        raw_path = (data.get('path') or '/').strip()[:255] or '/'
        page_path = raw_path if raw_path.startswith('/') else f'/{raw_path}'
        if not page_path.startswith(('/static', '/api', '/admin')):
            try:
                supabase.table("site_visits").insert({
                    "visitor_token": get_or_create_visitor_token(),
                    "visit_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "path": page_path,
                    "user_id": (session.get('user') or {}).get('id'),
                }).execute()
            except Exception as e:
                print("Consent initial site_visit error:", e)

    resp = jsonify({"success": True, "consent": choice})
    resp.set_cookie(
        COOKIE_CONSENT_NAME,
        choice,
        max_age=180 * 24 * 3600,
        samesite='Lax',
        secure=request.is_secure,
        path='/',
    )
    return resp

# Helper to verify if user is logged in
def is_logged_in():
    return 'user' in session


def is_admin_session():
    """Return True when the active session belongs to an authenticated admin."""
    return is_logged_in() and session.get('role') == 'admin'


def default_portal_endpoint():
    """Route admins to Admin Dashboard and all other users to Home."""
    return 'admin_dashboard' if is_admin_session() else 'home'


# Decorator to restrict pages to logged-in users
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_logged_in():
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# Decorator to keep student repository routes isolated from admin accounts
def student_repository_only(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if is_admin_session():
            return redirect(url_for('admin_dashboard'))
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
        return redirect(url_for(default_portal_endpoint()))
    
    error = None
    if request.method == 'POST':
        student_id = request.form.get('student_id', '').strip()
        name = request.form.get('name', '').strip()
        grade_section = request.form.get('grade_section', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        role = "student"
        pw_ok, pw_error = validate_password_strength(password)

        if not student_id or not name or not grade_section or not email or not password or not confirm_password:
            error = "All fields are required."
        elif password != confirm_password:
            error = "Passwords do not match."
        elif not pw_ok:
            error = pw_error
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
                        "role": role,
                        "status": "pending"
                    }).execute()
                return redirect(url_for('login', msg="Account created! An administrator must approve your account before you can log in."))
            except Exception as e:
                error = f"Error during sign up: {str(e)}"

    return render_template('signup.html', error=error)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if is_logged_in():
        return redirect(url_for(default_portal_endpoint()))
    
    error = None
    pending_notice = None
    msg = request.args.get('msg')
    
    if request.method == 'POST':
        login_input = request.form.get('student_id', '').strip()
        password = request.form.get('password', '')

        if not login_input or not password:
            error = "Student ID/Email and Password are required."
        elif not supabase or not supabase_auth:
            error = "Database connection unavailable. Please try again later."
        else:
            profile_status = None
            try:
                profile_res = supabase.table("profiles").select("id, email, role, student_id, status, name").or_(f"student_id.eq.{login_input},email.eq.{login_input.lower()}").execute()
                
                email_to_use = None
                student_id_to_use = login_input
                role = "student"
                profile_name = ""

                if profile_res.data:
                    profile = profile_res.data[0]
                    email_to_use = profile['email']
                    student_id_to_use = profile['student_id']
                    role = profile['role']
                    profile_status = profile.get('status') or 'approved'
                    profile_name = profile.get('name') or ''
                elif "@" in login_input:
                    email_to_use = login_input.lower()
                else:
                    error = "Invalid Student ID or Email."

                if email_to_use and not error:
                    auth_res = supabase_auth.auth.sign_in_with_password({
                        "email": email_to_use,
                        "password": password
                    })
                    
                    if auth_res and auth_res.session:
                        # Double check profile status if not found in initial lookup
                        if profile_status is None:
                            p_check = supabase.table("profiles").select("role, student_id, status, name").eq("id", auth_res.user.id).execute()
                            if p_check.data:
                                profile_status = p_check.data[0].get('status') or 'approved'
                                role = p_check.data[0].get('role', role)
                                student_id_to_use = p_check.data[0].get('student_id', student_id_to_use)
                                profile_name = p_check.data[0].get('name') or profile_name

                        if profile_status == 'pending':
                            pending_notice = "Your account is still pending administrator approval. Please check back once an administrator approves your registration."
                        elif profile_status == 'rejected':
                            error = "Your account registration was declined by an administrator. Please contact the school office for assistance."
                        else:
                            session['user'] = {
                                'id': auth_res.user.id,
                                'email': auth_res.user.email,
                                'student_id': student_id_to_use,
                                'name': profile_name,
                            }
                            session['access_token'] = auth_res.session.access_token
                            session['role'] = role
                            return redirect(url_for(default_portal_endpoint()))
                    else:
                        error = "Incorrect password."
            except Exception as e:
                err_str = str(e)
                if "email not confirmed" in err_str.lower() and profile_status == 'pending':
                    pending_notice = "Your account is pending administrator approval. Please check back once an administrator approves your registration."
                elif "email not confirmed" in err_str.lower() and profile_status == 'rejected':
                    error = "Your account registration was declined by an administrator."
                else:
                    error = f"Login failed: {err_str}"
                
    return render_template('login.html', error=error, pending_notice=pending_notice, msg=msg)

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if is_logged_in():
        return redirect(url_for(default_portal_endpoint()))
        
    error = None
    msg = None
    
    if request.method == 'POST':
        email_input = request.form.get('email', '').strip().lower()
        if not email_input:
            error = "Email address is required."
        elif not supabase_auth:
            error = "Database connection unavailable. Please try again later."
        else:
            try:
                redirect_url = request.url_root.rstrip('/') + url_for('reset_password')
                supabase_auth.auth.reset_password_for_email(
                    email_input,
                    options={"redirect_to": redirect_url}
                )
                msg = "Password reset instructions have been sent to your email address."
            except Exception as e:
                error = f"Failed to send reset link: {str(e)}"
                
    return render_template('forgot_password.html', error=error, msg=msg)

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    error = None
    msg = None

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        access_token = request.form.get('access_token', '').strip()
        code = request.form.get('code', '').strip()
        token_hash = request.form.get('token_hash', '').strip()
        pw_ok, pw_error = validate_password_strength(password)

        if not password or not confirm_password:
            error = "All fields are required."
        elif password != confirm_password:
            error = "Passwords do not match."
        elif not pw_ok:
            error = pw_error
        elif not supabase or not supabase_auth:
            error = "Database connection unavailable."
        else:
            try:
                user_id = None
                
                if access_token:
                    res = supabase_auth.auth.get_user(access_token)
                    if res and res.user:
                        user_id = res.user.id
                elif code:
                    res = supabase_auth.auth.exchange_code_for_session({"auth_code": code})
                    if res and res.user:
                        user_id = res.user.id
                elif token_hash:
                    res = supabase_auth.auth.verify_otp({"token_hash": token_hash, "type": "recovery"})
                    if res and res.user:
                        user_id = res.user.id
                elif is_logged_in():
                    user_id = session['user']['id']

                if user_id:
                    supabase.auth.admin.update_user_by_id(user_id, {"password": password})
                    return redirect(url_for('login', msg="Password reset successfully! Please log in with your new password."))
                else:
                    error = "Invalid or expired reset link. Please request a new password reset."
            except Exception as e:
                error = f"Failed to reset password: {str(e)}"

    return render_template('reset_password.html', error=error, msg=msg)

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
        current_password = request.form.get('current_password', '')
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        pw_ok, pw_error = validate_password_strength(password)
        
        if not current_password or not password or not confirm_password:
            error = "All fields are required."
        elif password != confirm_password:
            error = "New passwords do not match."
        elif current_password == password:
            error = "New password must be different from your current password."
        elif not pw_ok:
            error = pw_error
        elif not supabase or not supabase_auth:
            error = "Database connection unavailable."
        else:
            try:
                user_email = session['user'].get('email')
                user_id = session['user'].get('id')
                verify_res = supabase_auth.auth.sign_in_with_password({
                    "email": user_email,
                    "password": current_password
                })
                if not verify_res or not verify_res.user:
                    error = "Current password is incorrect."
                else:
                    supabase.auth.admin.update_user_by_id(user_id, {"password": password})
                    if verify_res.session:
                        session['access_token'] = verify_res.session.access_token
                    success = "Password updated successfully!"
            except Exception as e:
                err_msg = str(e)
                if "invalid login credentials" in err_msg.lower():
                    error = "Current password is incorrect."
                else:
                    error = f"Failed to update password: {err_msg}"
                
    return render_template('change_password.html', error=error, success=success)

# ----------------- RESEARCH FILTERING & PAGINATION HELPERS -----------------

def _matches_core_research_type(paper_type, canonical_type):
    """Match abbreviated and compound DB research_type labels against clean canonical categories."""
    raw = (paper_type or '').strip().lower()
    target = (canonical_type or '').strip().lower()
    if not target:
        return True
    if not raw:
        return False
    if target == "quantitative":
        return "quantitative" in raw or bool(re.search(r"\bquanti\b", raw))
    if target == "qualitative":
        return "qualitative" in raw or bool(re.search(r"\bquali\b", raw))
    if target == "mixed methods":
        has_quanti = "quantitative" in raw or bool(re.search(r"\bquanti\b", raw))
        has_quali = "qualitative" in raw or bool(re.search(r"\bquali\b", raw))
        return "mixed" in raw or (has_quanti and has_quali)
    if target == "experimental":
        return "experimental" in raw
    if target == "descriptive":
        return "descriptive" in raw
    if target == "action research":
        return "action" in raw
    return target in raw


def get_distinct_research_types(papers):
    """Return clean canonical research categories plus 'Other / Applied' if uncategorized types exist."""
    types = list(CORE_RESEARCH_TYPES)
    has_other = any(
        (p.get('research_type') or '').strip()
        and not any(_matches_core_research_type(p.get('research_type'), core) for core in CORE_RESEARCH_TYPES)
        for p in (papers or [])
    )
    if has_other:
        types.append("Other / Applied")
    return types


def filter_papers(papers, search_query='', strand_filter='', year_filter='', type_filter=''):
    """Apply keyword, strand, academic year, and research type filtering consistently."""
    filtered = list(papers or [])
    if strand_filter in ('HUMSS', 'ABM', 'STEM'):
        filtered = [p for p in filtered if (p.get('strand') or '').upper() == strand_filter]
    if year_filter:
        filtered = [p for p in filtered if (p.get('academic_year') or '').strip() == year_filter]
    if type_filter:
        tf = type_filter.strip()
        if tf.lower() == "other / applied":
            filtered = [
                p for p in filtered
                if (p.get('research_type') or '').strip()
                and not any(_matches_core_research_type(p.get('research_type'), core) for core in CORE_RESEARCH_TYPES)
            ]
        else:
            filtered = [p for p in filtered if _matches_core_research_type(p.get('research_type'), tf)]
    if search_query:
        q = search_query.strip().lower()
        q_filtered = []
        for p in filtered:
            authors_str = " ".join(p.get('authors') or []).lower()
            keywords_str = " ".join(p.get('keywords') or []).lower()
            if (
                q in (p.get('title') or '').lower()
                or q in (p.get('abstract') or '').lower()
                or q in (p.get('adviser') or '').lower()
                or q in (p.get('subject_area') or '').lower()
                or q in (p.get('research_type') or '').lower()
                or q in authors_str
                or q in keywords_str
            ):
                q_filtered.append(p)
        filtered = q_filtered
    return filtered


def build_pagination_range(current_page, total_pages):
    """Build compact numbered page sequence like [1, 2, 3, '...', 10]."""
    if total_pages <= 7:
        return list(range(1, total_pages + 1))
    pages = [1]
    start = max(2, current_page - 1)
    end = min(total_pages - 1, current_page + 1)
    if start > 2:
        pages.append('...')
    for p in range(start, end + 1):
        pages.append(p)
    if end < total_pages - 1:
        pages.append('...')
    pages.append(total_pages)
    return pages


def paginate_items(items, page, per_page=PAPERS_PER_PAGE):
    """Slice list of items into a single page with pagination metadata."""
    total_count = len(items)
    total_pages = max(1, math.ceil(total_count / per_page)) if total_count else 1
    current_page = max(1, min(page or 1, total_pages))
    start_idx = (current_page - 1) * per_page
    end_idx = min(start_idx + per_page, total_count)
    return {
        "items": items[start_idx:end_idx],
        "total_count": total_count,
        "per_page": per_page,
        "current_page": current_page,
        "total_pages": total_pages,
        "start_item": start_idx + 1 if total_count else 0,
        "end_item": end_idx,
        "has_prev": current_page > 1,
        "has_next": current_page < total_pages,
        "prev_page": current_page - 1,
        "next_page": current_page + 1,
        "pages": build_pagination_range(current_page, total_pages),
    }

# ----------------- APP PAGES -----------------

def _load_public_landing_stats():
    stats = {"total_papers": 0, "STEM": 0, "ABM": 0, "HUMSS": 0}
    if not supabase:
        return stats
    try:
        res = supabase.table("research_papers").select("strand").execute()
        rows = res.data or []
        stats["total_papers"] = len(rows)
        for row in rows:
            s = (row.get("strand") or "").upper()
            if s in stats:
                stats[s] += 1
    except Exception as e:
        print("Public stats read error:", e)
    return stats


def _render_repository_home():
    recent_papers = []
    best_in_research = []
    research_types = list(STANDARD_RESEARCH_TYPES)
    
    if supabase:
        try:
            papers_res = supabase.table("research_papers").select("*").order("created_at", desc=True).execute()
            if papers_res.data:
                recent_papers = papers_res.data
                research_types = get_distinct_research_types(recent_papers)
                
            best_res = supabase.table("research_papers").select("*").not_.is_("awards", "null").neq("awards", "").execute()
            if best_res.data:
                sorted_best = sorted(best_res.data, key=lambda p: (p.get('academic_year', ''), p.get('created_at', '')), reverse=True)
                best_in_research = sorted_best[:3]
        except Exception as e:
            print("DB read failed:", e)
            
    return render_template('home.html', recent_papers=recent_papers, best_in_research=best_in_research, research_types=research_types)


@app.route('/')
@student_repository_only
def home():
    if not is_logged_in():
        stats = _load_public_landing_stats()
        return render_template('landing.html', stats=stats)
    return _render_repository_home()


@app.route('/landing')
@student_repository_only
def landing():
    stats = _load_public_landing_stats()
    return render_template('landing.html', stats=stats)


@app.route('/home')
@login_required
@student_repository_only
def repository_home():
    return _render_repository_home()

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    error = None
    success = None
    show_verification_modal = False
    user_id = session['user']['id']
    
    # Load profile data from database
    profile_data = None
    if supabase:
        try:
            res = supabase.table("profiles").select("*").eq("id", user_id).execute()
            if res.data:
                profile_data = res.data[0]
        except Exception as e:
            print("DB profile load error:", e)

    if not profile_data:
        profile_data = {
            "id": user_id,
            "student_id": session['user']['student_id'],
            "name": "",
            "grade_section": "",
            "email": session['user']['email'],
            "role": session.get('role', 'student'),
            "avatar_url": None
        }
        
    old_email = profile_data['email']
    is_email_verified = True
    unconfirmed_email = None

    # Check Supabase Auth user object for verified email status
    if supabase_auth and session.get('access_token'):
        try:
            auth_res = supabase_auth.auth.get_user(session['access_token'])
            if auth_res and auth_res.user:
                auth_user = auth_res.user
                
                # Check for unconfirmed pending new email
                unconfirmed_email = getattr(auth_user, 'new_email', None) or getattr(auth_user, 'unconfirmed_email', None)
                
                # Check if auth_user primary email is confirmed
                email_confirmed = bool(getattr(auth_user, 'email_confirmed_at', None))
                
                # If Supabase Auth primary email is confirmed and differs from DB profile email:
                if auth_user.email and auth_user.email != old_email and email_confirmed:
                    # Verified! Update DB profile & session to new email
                    supabase.table("profiles").update({"email": auth_user.email}).eq("id", user_id).execute()
                    session['user']['email'] = auth_user.email
                    profile_data['email'] = auth_user.email
                    old_email = auth_user.email
                    success = f"Email verified! Profile updated to {auth_user.email}."
                elif not email_confirmed and not unconfirmed_email:
                    is_email_verified = False
        except Exception as e:
            print("Error checking Supabase auth status:", e)

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        grade_section = request.form.get('grade_section', '').strip()
        submitted_email = request.form.get('email', '').strip().lower()

        if not name or not grade_section or not submitted_email:
            error = "All fields are required."
        elif not supabase:
            error = "Database connection unavailable."
        else:
            try:
                # Handle avatar upload
                avatar_url = profile_data.get('avatar_url')
                avatar_file = request.files.get('avatar')
                if avatar_file and avatar_file.filename:
                    ext = os.path.splitext(avatar_file.filename)[1].lower()
                    if ext in ['.jpg', '.jpeg', '.png', '.gif']:
                        try:
                            avatar_filename = f"{user_id}{ext}"
                            file_bytes = avatar_file.read()
                            try:
                                storage_remove("avatars", avatar_filename)
                            except:
                                pass
                            storage_upload("avatars", avatar_filename, file_bytes, avatar_file.content_type or "image/png")
                            avatar_url = f"{SUPABASE_URL}/storage/v1/object/public/avatars/{avatar_filename}"
                        except Exception as e:
                            print("Error uploading avatar:", e)
                            error = f"Error uploading photo: {str(e)}"

                # Check if user is attempting to change their email address
                if submitted_email != old_email:
                    email_sent = False
                    error_detail = None
                    
                    access_token = session.get('access_token')
                    if access_token:
                        # Direct HTTP call to Supabase auth/v1/user endpoint
                        auth_url = f"{SUPABASE_URL}/auth/v1/user"
                        headers = {
                            "Authorization": f"Bearer {access_token}",
                            "apikey": SUPABASE_KEY,
                            "Content-Type": "application/json"
                        }
                        redirect_url = request.url_root.rstrip('/') + url_for('profile')
                        payload = {
                            "email": submitted_email,
                            "email_redirect_to": redirect_url
                        }
                        try:
                            resp = requests.put(auth_url, headers=headers, json=payload)
                            if resp.status_code == 200:
                                email_sent = True
                            else:
                                resp_data = resp.json() if resp.text else {}
                                error_detail = resp_data.get('msg') or resp_data.get('message') or resp_data.get('error_description') or f"HTTP {resp.status_code}"
                        except Exception as ex:
                            error_detail = str(ex)
                    else:
                        error_detail = "User session expired. Please log in again."

                    # Keep/revert profile email in database to the old email until verified!
                    update_data = {
                        "name": name,
                        "grade_section": grade_section,
                        "email": old_email,
                        "avatar_url": avatar_url
                    }
                    supabase.table("profiles").update(update_data).eq("id", user_id).execute()
                    profile_data.update(update_data)
                    session['user']['name'] = name
                    session.modified = True

                    if email_sent:
                        unconfirmed_email = submitted_email
                        show_verification_modal = True
                        success = f"Verification link sent to {submitted_email}! Please check your email to confirm."
                    else:
                        error = f"Failed to send email verification: {error_detail}"
                else:
                    # Update profile normally (email unchanged)
                    update_data = {
                        "name": name,
                        "grade_section": grade_section,
                        "email": old_email,
                        "avatar_url": avatar_url
                    }
                    supabase.table("profiles").update(update_data).eq("id", user_id).execute()
                    profile_data.update(update_data)
                    session['user']['name'] = name
                    session.modified = True
                    if not error:
                        success = "Profile updated successfully!"

            except Exception as e:
                error = f"Error updating profile: {str(e)}"

    return render_template('profile.html', profile=profile_data, is_email_verified=is_email_verified, unconfirmed_email=unconfirmed_email, show_verification_modal=show_verification_modal, error=error, success=success)

@app.route('/api/resend-verification', methods=['POST'])
@login_required
def resend_verification():
    email = request.form.get('email', '').strip().lower()
    access_token = session.get('access_token')
    if not email:
        return jsonify({"success": False, "error": "Email address is required."}), 400
    if not access_token:
        return jsonify({"success": False, "error": "Session expired. Please log in again."}), 401
    
    auth_url = f"{SUPABASE_URL}/auth/v1/user"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "apikey": SUPABASE_KEY,
        "Content-Type": "application/json"
    }
    redirect_url = request.url_root.rstrip('/') + url_for('profile')
    payload = {
        "email": email,
        "email_redirect_to": redirect_url
    }
    try:
        resp = requests.put(auth_url, headers=headers, json=payload)
        if resp.status_code == 200:
            return jsonify({"success": True, "message": f"Verification email resent to {email}."})
        else:
            resp_data = resp.json() if resp.text else {}
            err = resp_data.get('msg') or resp_data.get('message') or "Failed to resend verification email."
            return jsonify({"success": False, "error": err}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/verify-email-code', methods=['POST'])
@login_required
def verify_email_code():
    email = request.form.get('email', '').strip().lower()
    token = request.form.get('token', '').strip()
    access_token = session.get('access_token')
    
    if not email or not token:
        return jsonify({"success": False, "error": "Email and 6-digit code are required."}), 400
        
    verify_url = f"{SUPABASE_URL}/auth/v1/verify"
    headers = {
        "apikey": SUPABASE_KEY,
        "Content-Type": "application/json"
    }
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    types_to_try = ["email_change", "email", "signup"]
    verified = False
    error_msg = "Invalid or expired verification code."

    for verify_type in types_to_try:
        payload = {
            "type": verify_type,
            "email": email,
            "token": token
        }
        try:
            resp = requests.post(verify_url, headers=headers, json=payload)
            if resp.status_code == 200:
                verified = True
                break
            else:
                resp_data = resp.json() if resp.text else {}
                if resp_data.get('msg') or resp_data.get('message'):
                    error_msg = resp_data.get('msg') or resp_data.get('message')
        except Exception as e:
            error_msg = str(e)

    if verified:
        user_id = session['user']['id']
        # Update profile DB & session
        supabase.table("profiles").update({"email": email}).eq("id", user_id).execute()
        session['user']['email'] = email
        return jsonify({"success": True, "message": f"Email successfully verified and updated to {email}!"})
    else:
        return jsonify({"success": False, "error": error_msg}), 400

@app.route('/bookmarks')
@login_required
@student_repository_only
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
    if is_admin_session():
        return jsonify({"success": False, "error": "Bookmarks are unavailable in the admin portal."}), 403

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
            bookmarked = False
        else:
            supabase.table("bookmarks").insert({"user_id": user_id, "paper_id": paper_id}).execute()
            bookmarked = True

        count_res = supabase.table("bookmarks").select("id", count="exact").eq("paper_id", paper_id).execute()
        bookmark_count = count_res.count if hasattr(count_res, 'count') and count_res.count is not None else len(count_res.data)
        
        return jsonify({"success": True, "bookmarked": bookmarked, "bookmark_count": bookmark_count})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/search-suggestions')
@login_required
def search_suggestions():
    if is_admin_session():
        return jsonify({"suggestions": [], "error": "Unavailable in the admin portal."}), 403

    q = request.args.get('q', '').strip().lower()
    strand_filter = request.args.get('strand', '').strip().upper()
    if len(q) < 1 or not supabase:
        return jsonify({"suggestions": []})

    try:
        query = supabase.table("research_papers").select("id, title, strand, academic_year, research_type, subject_area, authors, keywords")
        if strand_filter in ('HUMSS', 'ABM', 'STEM'):
            query = query.eq("strand", strand_filter)
        res = query.execute()
        papers = res.data or []
    except Exception as e:
        print("DB suggestion lookup error:", e)
        return jsonify({"suggestions": []})

    scored = []
    for p in papers:
        title = p.get('title') or ''
        authors = p.get('authors') or []
        keywords = p.get('keywords') or []
        subject = p.get('subject_area') or ''
        r_type = p.get('research_type') or ''
        score = 0
        hint = r_type or subject

        if q in title.lower():
            score += 5 if title.lower().startswith(q) else 3
        if any(q in (k or '').lower() for k in keywords):
            score += 2
            matched_kw = next((k for k in keywords if q in (k or '').lower()), '')
            if matched_kw:
                hint = f"Keyword: {matched_kw}"
        if any(q in (a or '').lower() for a in authors):
            score += 2
            matched_author = next((a for a in authors if q in (a or '').lower()), '')
            if matched_author:
                hint = f"Author: {matched_author}"
        if q in subject.lower() or q in r_type.lower():
            score += 1

        if score > 0:
            scored.append((
                score,
                {
                    "id": p.get("id"),
                    "title": title,
                    "strand": p.get("strand", ""),
                    "academic_year": p.get("academic_year", ""),
                    "research_type": r_type,
                    "hint": hint,
                },
            ))

    scored.sort(key=lambda item: item[0], reverse=True)
    return jsonify({"suggestions": [item[1] for item in scored[:8]]})


@app.route('/search')
@login_required
@student_repository_only
def search():
    search_query = request.args.get('q', '').strip()
    strand_filter = request.args.get('strand', '').strip().upper()
    year_filter = request.args.get('year', '').strip()
    type_filter = request.args.get('type', '').strip()
    page = request.args.get('page', 1, type=int) or 1

    all_papers = []
    academic_years = []
    research_types = list(STANDARD_RESEARCH_TYPES)

    if supabase:
        try:
            res = supabase.table("research_papers").select("*").order("created_at", desc=True).execute()
            if res.data:
                all_papers = res.data
                academic_years = sorted(
                    list(set(r['academic_year'] for r in all_papers if r.get('academic_year'))),
                    reverse=True,
                )
                research_types = get_distinct_research_types(all_papers)
        except Exception as e:
            print("DB search error:", e)

    filtered_papers = filter_papers(
        all_papers,
        search_query=search_query,
        strand_filter=strand_filter,
        year_filter=year_filter,
        type_filter=type_filter,
    )
    pagination = paginate_items(filtered_papers, page, per_page=PAPERS_PER_PAGE)

    return render_template(
        'search_results.html',
        papers=pagination['items'],
        total_count=pagination['total_count'],
        pagination=pagination,
        search_query=search_query,
        selected_strand=strand_filter,
        selected_year=year_filter,
        selected_type=type_filter,
        academic_years=academic_years,
        research_types=research_types,
    )


@app.route('/strand/<strand_name>')
@login_required
@student_repository_only
def strand(strand_name):
    strand_name = strand_name.upper()
    if strand_name not in ('HUMSS', 'ABM', 'STEM'):
        return redirect(url_for('home'))

    search_query = request.args.get('q', '').strip()
    year_filter = request.args.get('year', '').strip()
    type_filter = request.args.get('type', '').strip()
    page = request.args.get('page', 1, type=int) or 1

    all_strand_papers = []
    academic_years = []
    research_types = list(STANDARD_RESEARCH_TYPES)

    if supabase:
        try:
            res = supabase.table("research_papers").select("*").eq("strand", strand_name).order("created_at", desc=True).execute()
            if res.data:
                all_strand_papers = res.data
                academic_years = sorted(
                    list(set(r['academic_year'] for r in all_strand_papers if r.get('academic_year'))),
                    reverse=True,
                )
                research_types = get_distinct_research_types(all_strand_papers)
        except Exception as e:
            print("DB strand error:", e)

    filtered_papers = filter_papers(
        all_strand_papers,
        search_query=search_query,
        strand_filter=strand_name,
        year_filter=year_filter,
        type_filter=type_filter,
    )
    pagination = paginate_items(filtered_papers, page, per_page=PAPERS_PER_PAGE)

    return render_template(
        'strand.html',
        strand=strand_name,
        papers=pagination['items'],
        total_count=pagination['total_count'],
        pagination=pagination,
        search_query=search_query,
        selected_year=year_filter,
        selected_type=type_filter,
        academic_years=academic_years,
        research_types=research_types,
    )

@app.route('/paper/<paper_id>')
@login_required
def paper_detail(paper_id):
    paper = None
    is_bookmarked = False
    bookmark_count = 0
    recommended_papers = []
    
    if supabase:
        try:
            res = supabase.table("research_papers").select("*").eq("id", paper_id).execute()
            if res.data:
                paper = res.data[0]
            
            if paper and not is_admin_session():
                user_id = session['user']['id']
                bookmark_res = supabase.table("bookmarks").select("id").eq("user_id", user_id).eq("paper_id", paper_id).execute()
                is_bookmarked = len(bookmark_res.data) > 0

                count_res = supabase.table("bookmarks").select("id", count="exact").eq("paper_id", paper_id).execute()
                bookmark_count = count_res.count if hasattr(count_res, 'count') and count_res.count is not None else len(count_res.data)

                # Recommendation Engine: fetch candidates excluding active paper
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
        return redirect(url_for(default_portal_endpoint()))

    record_paper_view(paper_id)
    apa_citation = generate_apa_citation(paper)
    return render_template('detail.html', paper=paper, is_bookmarked=is_bookmarked, bookmark_count=bookmark_count, recommended_papers=recommended_papers, apa_citation=apa_citation)

@app.route('/api/paper/<paper_id>/pdf')
@login_required
def stream_pdf(paper_id):
    if not supabase:
        return jsonify({"error": "Database connection unavailable."}), 500
    
    try:
        res = supabase.table("research_papers").select("pdf_path").eq("id", paper_id).execute()
        if not res.data:
            return jsonify({"error": "Paper not found."}), 404
        
        pdf_path = res.data[0]['pdf_path']

        # Fast direct CDN streaming with byte-range support via signed URL
        try:
            signed_res = supabase.storage.from_("research_papers").create_signed_url(pdf_path, 3600)
            signed_url = signed_res.get('signedURL') or signed_res.get('signedUrl')
            if signed_url:
                return redirect(signed_url, code=302)
        except Exception as sign_err:
            print("[Storage Stream] Signed URL generation failed, falling back to direct download:", sign_err)

        pdf_data = storage_download("research_papers", pdf_path)
        etag = hashlib.md5(pdf_data).hexdigest()

        # Check for conditional GET (If-None-Match)
        if request.headers.get("If-None-Match") == etag:
            return Response(status=304)

        return Response(
            pdf_data,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": "inline; filename=research.pdf",
                "Cache-Control": "private, max-age=604800, immutable",
                "ETag": etag,
                "X-Content-Type-Options": "nosniff"
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

LEGAL_DOCUMENTS = {
    "privacy": {
        "title": "Privacy Policy",
        "subtitle": "How Lundayang Marians collects, safeguards, and uses school repository information.",
        "effective_date": "November 2026",
        "icon": "lock",
        "intro": (
            "Sta. Maria (Laguna) Academy Inc. respects student, faculty, and researcher privacy in alignment with "
            "the Philippine Data Privacy Act of 2012 (Republic Act No. 10173). This policy explains what information "
            "Lundayang Marians collects and how it is protected."
        ),
        "sections": [
            {
                "heading": "Information We Collect",
                "body": "When you register, sign in, or browse the repository, we process only the information required to verify school membership and operate the archive:",
                "points": [
                    "Account registration details: Student or Admin ID, full name, grade & section or department, email address, and encrypted authentication credentials.",
                    "Profile customizations: optional profile photo and saved personal bookmarks for approved research papers.",
                    "Optional usage telemetry (recorded only after opt-in cookie consent): session-scoped website visits (visit dates and visited paths) and anonymized paper view counts used exclusively in the Admin Dashboard.",
                ],
            },
            {
                "heading": "Cookies & Session Telemetry",
                "body": "Lundayang Marians uses first-party cookies and signed Flask sessions strictly to operate essential portal features and, with your permission, measure campus readership:",
                "points": [
                    "Essential cookies & session state: Flask signed session (authenticated user object, access token, and role), language selection (lang), and your saved consent choice (lm_cookie_consent stored for 180 days).",
                    "Optional analytics telemetry: selecting Accept All enables a session-scoped visitor token (visitor_id) that records non-admin page visits (site_visits) and manuscript views (paper_views); selecting Essential Only disables telemetry immediately.",
                    "No third-party ad trackers: Lundayang Marians does not deploy advertising pixels, cross-site trackers, or commercial analytics brokers, and you can adjust your preference anytime via Cookie Settings in the footer.",
                ],
            },
            {
                "heading": "How Account Information Is Used",
                "body": "Submitted registration details are reviewed by designated school administrators to confirm that accounts belong to authorized Sta. Maria (Laguna) Academy Inc. students, teachers, or staff.",
                "points": [
                    "Approve or decline pending registrations before granting access to full student research manuscripts.",
                    "Display author, adviser, strand, and award attribution on published scholarly records.",
                    "Maintain security audit logs for administrative uploads, edits, deletions, and account status changes.",
                ],
            },
            {
                "heading": "Storage, Security & View-Only Protection",
                "body": "Authentication, database records, and PDF manuscripts are hosted securely through Supabase with Row-Level Security (RLS) controls and server-side signed access.",
                "points": [
                    "Passwords are never stored in plain text and require strong complexity rules (8+ characters with uppercase, lowercase, and numeric characters).",
                    "Full PDF manuscripts are streamed to authenticated sessions through a view-only document reader rather than public indexing.",
                ],
            },
            {
                "heading": "Data Retention & Your Rights",
                "body": "Under RA 10173, registered Marian scholars and school personnel retain the right to inspect, update, or request correction of their profile data.",
                "points": [
                    "You may update your name, section, avatar photo, or email verification details at any time via My Profile, and rotate your password via Change Password.",
                    "Account deactivation, graduation archival inquiries, or correction of Student ID records can be coordinated directly with the School Library or Research Office.",
                ],
            },
        ],
    },
    "terms": {
        "title": "Terms & Conditions",
        "subtitle": "Institutional rules governing access, citations, and intellectual property on Lundayang Marians.",
        "effective_date": "November 2026",
        "icon": "file-check-2",
        "intro": (
            "By accessing Lundayang Marians, registering an account, or reading archived manuscripts, you agree to "
            "abide by the academic integrity, access control, and intellectual property guidelines of Sta. Maria "
            "(Laguna) Academy Inc."
        ),
        "sections": [
            {
                "heading": "Authorized School Access & Approval",
                "body": "Access to full research papers, bookmarks, and strand browsing is reserved for verified students, faculty, advisers, librarians, and administrators of Sta. Maria (Laguna) Academy Inc.",
                "points": [
                    "Newly created accounts enter a pending verification state and remain restricted until approved by a school administrator.",
                    "Users must provide truthful Student ID, Full Name, Grade & Section, and email information and keep their login credentials strictly personal.",
                ],
            },
            {
                "heading": "Academic Integrity & View-Only Use",
                "body": "All archived manuscripts remain the intellectual property of their student authors and Sta. Maria (Laguna) Academy Inc.",
                "points": [
                    "Studies are presented in a view-only reader for scholarly reference, literature review, and classroom learning.",
                    "Automated scraping, bulk downloading, bypassing view-only safeguards, plagiarizing, or commercially redistributing repository content is strictly prohibited.",
                ],
            },
            {
                "heading": "Citation & Attribution Standard",
                "body": "Whenever insights, frameworks, or findings from a Marian research study are referenced in academic work, proper scholarly credit must be given.",
                "points": [
                    "Each paper record includes a standardized APA 7th Edition citation block for convenient academic referencing.",
                    "Failure to attribute student researchers or misrepresenting repository studies as one's own work constitutes an academic integrity violation.",
                ],
            },
            {
                "heading": "Administration, Moderation & Policy Updates",
                "body": "School administrators and research advisers oversee repository quality, metadata accuracy, and account compliance.",
                "points": [
                    "Administrators may update research records, revoke pending or non-compliant accounts, and review administrative audit logs to protect repository integrity.",
                    "Sta. Maria (Laguna) Academy Inc. may update these Terms & Conditions and the Privacy Policy as school policies evolve; continued use after updates indicates acceptance.",
                ],
            },
        ],
    },
}


@app.route('/developers')
def developers():
    return render_template('developers.html')

@app.route('/faq')
def faq():
    return render_template('faq.html')


@app.route('/privacy-policy')
def privacy_policy():
    return render_template('legal.html', doc_key='privacy', doc=LEGAL_DOCUMENTS['privacy'])


@app.route('/terms')
def terms_conditions():
    return render_template('legal.html', doc_key='terms', doc=LEGAL_DOCUMENTS['terms'])

# ----------------- ADMIN PORTAL -----------------

AUDIT_ACTION_META = {
    "approve_user": {"label": "Approved Account", "tone": "approved", "group": "user"},
    "reject_user": {"label": "Rejected Account", "tone": "rejected", "group": "user"},
    "bulk_approve_users": {"label": "Bulk Approved", "tone": "approved", "group": "user"},
    "change_role": {"label": "Role Updated", "tone": "role", "group": "user"},
    "upload_paper": {"label": "Uploaded Paper", "tone": "upload", "group": "paper"},
    "edit_paper": {"label": "Edited Paper", "tone": "edit", "group": "paper"},
    "delete_paper": {"label": "Deleted Paper", "tone": "rejected", "group": "delete"},
}


def _csv_safe_cell(val):
    """Neutralize spreadsheet formula prefixes while formatting CSV cells."""
    text = str(val or "")
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


def _format_audit_log_entry(row):
    """Normalize an admin_audit_logs row for display and client filtering."""
    item = dict(row or {})
    raw_action = (item.get("action") or "").strip().lower()
    meta = AUDIT_ACTION_META.get(raw_action, {"label": raw_action.replace("_", " ").title() or "Action", "tone": "role", "group": "user"})
    raw_ts = str(item.get("created_at") or "")
    display_time = raw_ts[:16].replace("T", " ")
    if display_time:
        display_time += " UTC"
    item["action_label"] = meta["label"]
    item["action_tone"] = meta["tone"]
    item["action_group"] = meta["group"]
    item["display_time"] = display_time or "Just now"
    return item


def record_admin_audit(action, target_type, target_id=None, summary=""):
    """Insert an audit log record for an admin mutation; fails safely."""
    if not supabase:
        return None
    user = session.get("user") or {}
    admin_id = user.get("id")
    admin_name = user.get("student_id") or user.get("email") or "Administrator"
    try:
        if admin_id:
            prof_res = supabase.table("profiles").select("name").eq("id", admin_id).execute()
            if prof_res.data and prof_res.data[0].get("name"):
                admin_name = prof_res.data[0]["name"]
    except Exception:
        pass

    payload = {
        "admin_id": admin_id,
        "admin_name": admin_name,
        "action": action,
        "target_type": target_type,
        "target_id": str(target_id) if target_id else None,
        "summary": summary,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        res = supabase.table("admin_audit_logs").insert(payload).execute()
        saved = res.data[0] if getattr(res, "data", None) else payload
        return _format_audit_log_entry(saved)
    except Exception as e:
        print("Admin audit log insert skipped:", e)
        return _format_audit_log_entry(payload)


def _build_daily_engagement(visit_rows, view_rows, days=7):
    """Build ordered last-N-days counts and scaled chart percentages for SVG/CSS bars."""
    today = datetime.now(timezone.utc).date()
    dates = [today - timedelta(days=offset) for offset in range(days - 1, -1, -1)]
    visits_by_day = {}
    for row in (visit_rows or []):
        d_str = str(row.get("visit_date") or "")[:10]
        if d_str:
            visits_by_day[d_str] = visits_by_day.get(d_str, 0) + 1

    views_by_day = {}
    for row in (view_rows or []):
        d_str = str(row.get("created_at") or "")[:10]
        if d_str:
            views_by_day[d_str] = views_by_day.get(d_str, 0) + 1

    series = []
    max_val = 1
    for d in dates:
        key = d.isoformat()
        v_cnt = visits_by_day.get(key, 0)
        pv_cnt = views_by_day.get(key, 0)
        max_val = max(max_val, v_cnt, pv_cnt)
        series.append({
            "date": key,
            "label": d.strftime("%b %d"),
            "visits": v_cnt,
            "paper_views": pv_cnt,
        })

    for point in series:
        point["visit_pct"] = max(6, round((point["visits"] / max_val) * 100)) if point["visits"] > 0 else 0
        point["view_pct"] = max(6, round((point["paper_views"] / max_val) * 100)) if point["paper_views"] > 0 else 0
    return series


def _build_admin_paper_metrics():
    """Aggregate research papers, strand share, visits, paper views, and 7-day trends."""
    metrics = {
        "total_papers": 0,
        "strand_counts": {"STEM": 0, "ABM": 0, "HUMSS": 0},
        "total_visits": 0,
        "unique_visitors": 0,
        "today_visits": 0,
        "total_paper_views": 0,
        "pending_approvals": 0,
        "top_paper": None,
    }
    papers_with_metrics = []
    visit_rows = []
    view_rows = []
    strand_views = {"STEM": 0, "ABM": 0, "HUMSS": 0}

    if supabase:
        try:
            papers_res = supabase.table("research_papers").select("*").order("created_at", desc=True).execute()
            papers = papers_res.data or []
            metrics["total_papers"] = len(papers)
            for p in papers:
                s = (p.get("strand") or "").upper()
                if s in metrics["strand_counts"]:
                    metrics["strand_counts"][s] += 1

            # Aggregate Paper Views
            views_by_paper = {}
            try:
                views_res = supabase.table("paper_views").select("paper_id, created_at").execute()
                view_rows = views_res.data or []
                metrics["total_paper_views"] = len(view_rows)
                for vr in view_rows:
                    pid = vr.get("paper_id")
                    if pid:
                        views_by_paper[pid] = views_by_paper.get(pid, 0) + 1
            except Exception as e:
                print("Dashboard paper_views read error:", e)

            # Aggregate Bookmarks per Paper
            bookmarks_by_paper = {}
            try:
                bm_res = supabase.table("bookmarks").select("paper_id").execute()
                for br in (bm_res.data or []):
                    pid = br.get("paper_id")
                    if pid:
                        bookmarks_by_paper[pid] = bookmarks_by_paper.get(pid, 0) + 1
            except Exception as e:
                print("Dashboard bookmarks read error:", e)

            # Aggregate Site Visits
            try:
                visits_res = supabase.table("site_visits").select("visitor_token, visit_date").execute()
                visit_rows = visits_res.data or []
                metrics["total_visits"] = len(visit_rows)
                metrics["unique_visitors"] = len(set(v.get("visitor_token") for v in visit_rows if v.get("visitor_token")))
                today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                metrics["today_visits"] = sum(1 for v in visit_rows if str(v.get("visit_date", "")) == today_str)
            except Exception as e:
                print("Dashboard site_visits read error:", e)

            # Enrich papers sorted by view_count desc, then created_at desc
            for p in papers:
                pid = p.get("id")
                vc = views_by_paper.get(pid, 0)
                s = (p.get("strand") or "").upper()
                if s in strand_views:
                    strand_views[s] += vc
                p_copy = dict(p)
                p_copy["view_count"] = vc
                p_copy["bookmark_count"] = bookmarks_by_paper.get(pid, 0)
                papers_with_metrics.append(p_copy)

            papers_with_metrics.sort(key=lambda item: (item.get("view_count", 0), item.get("created_at", "")), reverse=True)
            if papers_with_metrics and papers_with_metrics[0].get("view_count", 0) > 0:
                metrics["top_paper"] = papers_with_metrics[0]
        except Exception as e:
            print("Admin paper metrics load error:", e)

    total_papers = metrics["total_papers"] or 1
    strand_stats = [
        {
            "code": code,
            "count": metrics["strand_counts"][code],
            "views": strand_views[code],
            "pct": round((metrics["strand_counts"][code] / total_papers) * 100) if metrics["total_papers"] else 0,
        }
        for code in ("STEM", "ABM", "HUMSS")
    ]
    academic_years = sorted({p.get("academic_year") for p in papers_with_metrics if p.get("academic_year")}, reverse=True)
    daily_engagement = _build_daily_engagement(visit_rows, view_rows, days=7)
    top_papers = papers_with_metrics[:5]
    return metrics, papers_with_metrics, strand_stats, daily_engagement, academic_years, top_papers


@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    metrics, papers_with_metrics, strand_stats, daily_engagement, academic_years, top_papers = _build_admin_paper_metrics()
    all_users = []
    pending_users = []
    approved_users = []
    rejected_users = []
    audit_logs = []

    if supabase:
        try:
            users_res = supabase.table("profiles").select("id, student_id, name, grade_section, email, role, status, created_at").order("created_at", desc=True).execute()
            for u in (users_res.data or []):
                u_copy = dict(u)
                u_status = (u_copy.get("status") or "approved").lower()
                u_copy["status"] = u_status
                all_users.append(u_copy)
                if u_status == "pending":
                    pending_users.append(u_copy)
                elif u_status == "rejected":
                    rejected_users.append(u_copy)
                else:
                    approved_users.append(u_copy)
            metrics["pending_approvals"] = len(pending_users)
        except Exception as e:
            print("Dashboard profiles read error:", e)

        try:
            audit_res = supabase.table("admin_audit_logs").select("*").order("created_at", desc=True).execute()
            audit_logs = [_format_audit_log_entry(r) for r in (audit_res.data or [])[:50]]
        except Exception as e:
            print("Dashboard audit_logs read skipped:", e)

    return render_template(
        'admin_dashboard.html',
        metrics=metrics,
        papers=papers_with_metrics,
        strand_stats=strand_stats,
        daily_engagement=daily_engagement,
        academic_years=academic_years,
        top_papers=top_papers,
        all_users=all_users,
        pending_users=pending_users,
        approved_users=approved_users,
        rejected_users=rejected_users,
        audit_logs=audit_logs,
        recent_audit_logs=audit_logs[:6],
        current_admin_id=session.get('user', {}).get('id'),
    )


@app.route('/admin/users/<user_id>/status', methods=['POST'])
@admin_required
def admin_update_user_status(user_id):
    if not supabase:
        return jsonify({"success": False, "error": "Database connection unavailable."}), 500

    data = request.get_json(silent=True) or request.form
    new_status = (data.get('status') or '').strip().lower()
    new_role = (data.get('role') or '').strip().lower()

    update_payload = {}
    if new_status:
        if new_status not in ('pending', 'approved', 'rejected'):
            return jsonify({"success": False, "error": "Invalid approval status."}), 400
        update_payload["status"] = new_status

    if new_role:
        if new_role not in ('student', 'admin'):
            return jsonify({"success": False, "error": "Invalid role."}), 400
        if user_id == (session.get('user') or {}).get('id') and new_role != 'admin':
            return jsonify({"success": False, "error": "You cannot remove your own admin role."}), 400
        update_payload["role"] = new_role

    if not update_payload:
        return jsonify({"success": False, "error": "No update fields provided."}), 400

    try:
        target_label = user_id
        try:
            target_res = supabase.table("profiles").select("name, student_id").eq("id", user_id).execute()
            if target_res.data:
                tr = target_res.data[0]
                target_label = f"{tr.get('name') or 'User'} ({tr.get('student_id') or user_id})"
        except Exception:
            pass

        supabase.table("profiles").update(update_payload).eq("id", user_id).execute()
        if new_status == 'approved':
            try:
                supabase.auth.admin.update_user_by_id(user_id, {"email_confirm": True})
            except Exception:
                pass

        audit_entry = None
        if new_status == 'approved':
            audit_entry = record_admin_audit("approve_user", "user", user_id, f"Approved account for {target_label}")
        elif new_status == 'rejected':
            audit_entry = record_admin_audit("reject_user", "user", user_id, f"Rejected account for {target_label}")
        elif new_role:
            audit_entry = record_admin_audit("change_role", "user", user_id, f"Changed role for {target_label} to {new_role}")

        return jsonify({
            "success": True,
            "user_id": user_id,
            "status": update_payload.get("status"),
            "role": update_payload.get("role"),
            "audit": audit_entry,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/admin/users/bulk-approve', methods=['POST'])
@admin_required
def admin_bulk_approve_users():
    if not supabase:
        return jsonify({"success": False, "error": "Database connection unavailable."}), 500

    try:
        pending_res = supabase.table("profiles").select("id, student_id, name").eq("status", "pending").execute()
        pending_rows = pending_res.data or []
        approved_ids = []
        for row in pending_rows:
            uid = row.get("id")
            if not uid:
                continue
            supabase.table("profiles").update({"status": "approved"}).eq("id", uid).execute()
            try:
                supabase.auth.admin.update_user_by_id(uid, {"email_confirm": True})
            except Exception:
                pass
            approved_ids.append(uid)

        audit_entry = None
        if approved_ids:
            audit_entry = record_admin_audit(
                "bulk_approve_users",
                "user",
                summary=f"Bulk approved {len(approved_ids)} pending account(s)",
            )

        return jsonify({
            "success": True,
            "approved_count": len(approved_ids),
            "approved_ids": approved_ids,
            "audit": audit_entry,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/admin/export/papers.csv')
@admin_required
def admin_export_papers_csv():
    _, papers_with_metrics, _, _, _, _ = _build_admin_paper_metrics()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Title",
        "Strand",
        "Academic Year",
        "Research Type",
        "Subject Area",
        "Authors",
        "Adviser",
        "Awards",
        "Views",
        "Bookmarks",
    ])
    for p in papers_with_metrics:
        writer.writerow([
            _csv_safe_cell(p.get("title", "")),
            _csv_safe_cell(p.get("strand", "")),
            _csv_safe_cell(p.get("academic_year", "")),
            _csv_safe_cell(p.get("research_type", "")),
            _csv_safe_cell(p.get("subject_area", "")),
            _csv_safe_cell("; ".join(p.get("authors") or [])),
            _csv_safe_cell(p.get("adviser", "")),
            _csv_safe_cell(p.get("awards") or ""),
            p.get("view_count", 0),
            p.get("bookmark_count", 0),
        ])

    return Response(
        "\ufeff" + buf.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="lundayang_marians_papers_report.csv"',
            "X-Content-Type-Options": "nosniff",
        },
    )

@app.route('/api/storage/sign-upload', methods=['POST'])
@admin_required
def get_signed_upload_url():
    if not supabase:
        return jsonify({"success": False, "error": "Database connection unavailable."}), 500
        
    data = request.get_json(silent=True) or request.form
    filename = data.get('filename', 'paper.pdf').strip()
    strand = data.get('strand', 'GENERAL').strip()
    academic_year = data.get('academic_year', '2025-2026').strip()
    
    # Sanitize filename
    clean_filename = "".join(c for c in filename if c.isalnum() or c in "._- ")
    if not clean_filename or not clean_filename.lower().endswith('.pdf'):
        clean_filename = "document.pdf"
        
    import time
    timestamp = int(time.time())
    safe_filename = f"{strand}/{academic_year.replace('/', '_')}_{timestamp}_{clean_filename.replace(' ', '_')}"
    
    try:
        res = supabase.storage.from_("research_papers").create_signed_upload_url(safe_filename)
        signed_url = res.get('signedUrl') or res.get('signed_url')
        if not signed_url:
            return jsonify({"success": False, "error": "Could not generate signed upload URL."}), 500
            
        return jsonify({
            "success": True,
            "signed_url": signed_url,
            "pdf_path": safe_filename
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

def _wants_json_response():
    """Return True when the caller prefers a structured JSON response (modal AJAX)."""
    accept = request.headers.get("Accept", "")
    return "application/json" in accept or request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _parse_paper_form(require_pdf=False):
    """Extract and validate upload/edit paper metadata and PDF inputs."""
    title = request.form.get('title', '').strip()
    abstract = request.form.get('abstract', '').strip()
    strand = request.form.get('strand', '').strip().upper()
    academic_year = request.form.get('academic_year', '').strip()
    research_type = request.form.get('research_type', '').strip()
    subject_area = request.form.get('subject_area', '').strip()
    adviser = request.form.get('adviser', '').strip()
    awards = request.form.get('awards', '').strip() or None
    authors = [a.strip() for a in request.form.get('authors', '').split(',') if a.strip()]
    keywords = [k.strip() for k in request.form.get('keywords', '').split(',') if k.strip()]
    pdf_path = request.form.get('pdf_path', '').strip()
    pdf_file = request.files.get('pdf_file')

    if not title or not abstract or not strand or not academic_year or not research_type or not subject_area or not adviser or not authors:
        return None, "All fields except Awards are required."
    if strand not in ('HUMSS', 'ABM', 'STEM'):
        return None, "Please select a valid academic strand."
    if require_pdf and not pdf_path and not (pdf_file and pdf_file.filename):
        return None, "All fields except Awards are required, including the PDF file."
    if pdf_file and pdf_file.filename and not pdf_file.filename.lower().endswith('.pdf'):
        return None, "File must be a PDF."

    return {
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
        "pdf_path": pdf_path,
        "pdf_file": pdf_file,
    }, None


@app.route('/admin/upload', methods=['GET', 'POST'])
@admin_required
def admin_upload():
    if request.method == 'GET':
        return redirect(url_for('admin_dashboard') + '#upload-paper')

    parsed, error = _parse_paper_form(require_pdf=True)
    if error:
        if _wants_json_response():
            return jsonify({"success": False, "error": error}), 400
        return redirect(url_for('admin_dashboard') + '#upload-paper')

    if not supabase:
        err_msg = "Database connection unavailable."
        return jsonify({"success": False, "error": err_msg}), 500 if _wants_json_response() else redirect(url_for('admin_dashboard'))

    try:
        final_pdf_path = parsed["pdf_path"]
        pdf_file = parsed["pdf_file"]
        if not final_pdf_path and pdf_file:
            safe_filename = f"{parsed['strand']}/{parsed['academic_year'].replace('/', '_')}_{pdf_file.filename.replace(' ', '_')}"
            storage_upload("research_papers", safe_filename, pdf_file.read(), "application/pdf")
            final_pdf_path = safe_filename

        now_iso = datetime.now(timezone.utc).isoformat()
        insert_payload = {
            "title": parsed["title"],
            "abstract": parsed["abstract"],
            "strand": parsed["strand"],
            "academic_year": parsed["academic_year"],
            "research_type": parsed["research_type"],
            "subject_area": parsed["subject_area"],
            "authors": parsed["authors"],
            "adviser": parsed["adviser"],
            "awards": parsed["awards"],
            "keywords": parsed["keywords"],
            "pdf_path": final_pdf_path,
            "created_by": session['user']['id'],
            "created_at": now_iso,
        }
        insert_res = supabase.table("research_papers").insert(insert_payload).execute()
        created_paper = dict(insert_res.data[0]) if getattr(insert_res, "data", None) else dict(insert_payload)
        created_paper.setdefault("view_count", 0)
        created_paper.setdefault("bookmark_count", 0)

        audit_entry = record_admin_audit(
            "upload_paper",
            "paper",
            created_paper.get("id"),
            f"Uploaded \"{parsed['title']}\" ({parsed['strand']})",
        )
        msg = "Research paper successfully uploaded and indexed!"
        if _wants_json_response():
            return jsonify({"success": True, "paper": created_paper, "audit": audit_entry, "message": msg})
        return redirect(url_for('admin_dashboard'))
    except Exception as e:
        if _wants_json_response():
            return jsonify({"success": False, "error": f"Upload failed: {str(e)}"}), 500
        return redirect(url_for('admin_dashboard'))


@app.route('/admin/paper/<paper_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_paper(paper_id):
    if request.method == 'GET':
        return redirect(f"{url_for('admin_dashboard')}#edit={paper_id}")

    if not supabase:
        if _wants_json_response():
            return jsonify({"success": False, "error": "Database connection unavailable."}), 500
        return jsonify({"error": "Database connection unavailable."}), 500

    try:
        paper_res = supabase.table("research_papers").select("*").eq("id", paper_id).execute()
        if not paper_res.data:
            if _wants_json_response():
                return jsonify({"success": False, "error": "Paper not found."}), 404
            return redirect(url_for('admin_dashboard'))

        paper = dict(paper_res.data[0])
        parsed, error = _parse_paper_form(require_pdf=False)
        if error:
            if _wants_json_response():
                return jsonify({"success": False, "error": error}), 400
            return redirect(url_for('admin_dashboard'))

        final_pdf_path = paper.get('pdf_path', '')
        pdf_path_new = parsed["pdf_path"]
        pdf_file = parsed["pdf_file"]
        if pdf_path_new and pdf_path_new != final_pdf_path:
            final_pdf_path = pdf_path_new
        elif pdf_file and pdf_file.filename:
            storage_upload("research_papers", final_pdf_path, pdf_file.read(), "application/pdf")

        updated_values = {
            "title": parsed["title"],
            "abstract": parsed["abstract"],
            "strand": parsed["strand"],
            "academic_year": parsed["academic_year"],
            "research_type": parsed["research_type"],
            "subject_area": parsed["subject_area"],
            "authors": parsed["authors"],
            "adviser": parsed["adviser"],
            "awards": parsed["awards"],
            "keywords": parsed["keywords"],
            "pdf_path": final_pdf_path,
        }

        supabase.table("research_papers").update(updated_values).eq("id", paper_id).execute()
        paper.update(updated_values)
        audit_entry = record_admin_audit("edit_paper", "paper", paper_id, f"Updated \"{parsed['title']}\" ({parsed['strand']})")
        msg = "Research paper updated successfully."

        if _wants_json_response():
            return jsonify({"success": True, "paper": paper, "audit": audit_entry, "message": msg})
        return redirect(url_for('admin_dashboard'))
    except Exception as e:
        if _wants_json_response():
            return jsonify({"success": False, "error": f"Update failed: {str(e)}"}), 500
        return jsonify({"error": str(e)}), 500

@app.route('/admin/paper/<paper_id>/delete', methods=['POST'])
@admin_required
def delete_paper(paper_id):
    if not supabase:
        return jsonify({"success": False, "error": "Database connection unavailable."}), 500
        
    try:
        # 1. Fetch paper details to get the pdf_path and audit metadata
        res = supabase.table("research_papers").select("pdf_path, title, strand").eq("id", paper_id).execute()
        if not res.data:
            return jsonify({"success": False, "error": "Paper not found."}), 404
            
        pdf_path = res.data[0]['pdf_path']
        deleted_title = res.data[0].get('title') or paper_id
        deleted_strand = res.data[0].get('strand') or ''
        
        # 2. Delete the PDF file from storage
        try:
            storage_remove("research_papers", pdf_path)
        except Exception as e:
            print("Failed to delete PDF from storage:", e)
            
        # 3. Delete database row (bookmarks cascade automatically)
        supabase.table("research_papers").delete().eq("id", paper_id).execute()
        audit_entry = record_admin_audit("delete_paper", "paper", paper_id, f"Deleted \"{deleted_title}\" ({deleted_strand})")
        
        return jsonify({"success": True, "audit": audit_entry, "strand": deleted_strand})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000, host="0.0.0.0")
