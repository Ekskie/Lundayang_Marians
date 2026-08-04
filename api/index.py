import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response
from supabase import create_client, Client
from dotenv import load_dotenv
import io
import requests
import hashlib

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

# In-memory PDF Cache: stores {paper_id: {"data": bytes, "etag": str}}
PDF_CACHE = {}

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

# ----------------- TRANSLATION SYSTEM -----------------
TRANSLATIONS = {
    'tl': {
        "English": "English",
        "Tagalog": "Tagalog",
        "Home": "Tahanan",
        "Developers": "Mga Tagapag-unlad",
        "FAQ": "Mga Madalas Itanong",
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

@app.context_processor
def inject_translations():
    lang = session.get('lang', 'en')
    def t(key):
        if lang == 'tl' and key in TRANSLATIONS.get('tl', {}):
            return TRANSLATIONS['tl'][key]
        return key
    return dict(t=t)

@app.route('/set-language/<lang>')
def set_language(lang):
    if lang in ['en', 'tl']:
        session['lang'] = lang
    referrer = request.referrer
    if referrer:
        return redirect(referrer)
    return redirect(url_for('home'))

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
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        role = "student"

        if not student_id or not name or not grade_section or not email or not password or not confirm_password:
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
                return redirect(url_for('login', msg="Account created successfully! Please check your email for confirmation or log in."))
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
        login_input = request.form.get('student_id', '').strip()
        password = request.form.get('password', '')

        if not login_input or not password:
            error = "Student ID/Email and Password are required."
        elif not supabase or not supabase_auth:
            error = "Database connection unavailable. Please try again later."
        else:
            try:
                profile_res = supabase.table("profiles").select("id, email, role, student_id").or_(f"student_id.eq.{login_input},email.eq.{login_input.lower()}").execute()
                
                email_to_use = None
                student_id_to_use = login_input
                role = "student"

                if profile_res.data:
                    profile = profile_res.data[0]
                    email_to_use = profile['email']
                    student_id_to_use = profile['student_id']
                    role = profile['role']
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
                        session['user'] = {
                            'id': auth_res.user.id,
                            'email': auth_res.user.email,
                            'student_id': student_id_to_use
                        }
                        session['access_token'] = auth_res.session.access_token
                        session['role'] = role
                        return redirect(url_for('home'))
                    else:
                        error = "Incorrect password."
            except Exception as e:
                error = f"Login failed: {str(e)}"
                
    return render_template('login.html', error=error, msg=msg)

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if is_logged_in():
        return redirect(url_for('home'))
        
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

        if not password or not confirm_password:
            error = "All fields are required."
        elif password != confirm_password:
            error = "Passwords do not match."
        elif len(password) < 6:
            error = "Password must be at least 6 characters."
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
                sorted_best = sorted(best_res.data, key=lambda p: (p.get('academic_year', ''), p.get('created_at', '')), reverse=True)
                best_in_research = sorted_best[:3]
        except Exception as e:
            print("DB read failed:", e)
            
    return render_template('home.html', recent_papers=recent_papers, best_in_research=best_in_research)

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
        pdf_data = None
        etag = None

        if paper_id in PDF_CACHE:
            cached = PDF_CACHE[paper_id]
            pdf_data = cached["data"]
            etag = cached["etag"]
        else:
            res = supabase.table("research_papers").select("pdf_path").eq("id", paper_id).execute()
            if not res.data:
                return jsonify({"error": "Paper not found."}), 404
            
            pdf_path = res.data[0]['pdf_path']
            pdf_data = storage_download("research_papers", pdf_path)
            etag = hashlib.md5(pdf_data).hexdigest()
            PDF_CACHE[paper_id] = {
                "data": pdf_data,
                "etag": etag
            }

        # Check for conditional GET (If-None-Match)
        if request.headers.get("If-None-Match") == etag:
            return Response(status=304)

        return Response(
            io.BytesIO(pdf_data),
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
                        PDF_CACHE.pop(paper_id, None)

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
    app.run(debug=True, port=5000, host="0.0.0.0")
