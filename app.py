# ============================================================
# Lost & Found — Iteration 1
# ============================================================

from flask import Flask, render_template, request, redirect
from flask import url_for, session, flash, jsonify
import json
import os
import re
import uuid
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
try:
    from supabase import create_client
except Exception:
    create_client = None
try:
    from PIL import Image, ImageFilter
    import pytesseract
    import numpy as np
    OCR_AVAILABLE = True
except Exception:
    Image = None
    ImageFilter = None
    pytesseract = None
    np = None
    OCR_AVAILABLE = False

# ============================================================
# TESSERACT PATH
# ============================================================
if OCR_AVAILABLE and pytesseract is not None:
    tesseract_cmd = os.getenv("TESSERACT_CMD", "").strip()
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    elif os.name == "nt":
        default_tesseract = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        if os.path.exists(default_tesseract):
            pytesseract.pytesseract.tesseract_cmd = default_tesseract

app = Flask(__name__)
app.secret_key = "lostfound_iter1_secret"

# ============================================================
# PATHS
# ============================================================

UPLOAD_FOLDER      = os.path.join("static", "uploads")
DATA_FILE          = "data.json"
EMAIL_SETTINGS_FILE = "email_settings.json"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()
SUPABASE_STATE_TABLE = os.getenv("SUPABASE_STATE_TABLE", "app_state").strip() or "app_state"
SUPABASE_STATE_ROW_ID = os.getenv("SUPABASE_STATE_ROW_ID", "main").strip() or "main"
SUPABASE_STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "lost-found-uploads").strip() or "lost-found-uploads"
SUPABASE_DATA_OBJECT_KEY = os.getenv(
    "SUPABASE_DATA_OBJECT_KEY",
    f"state/{SUPABASE_STATE_ROW_ID}.json"
).strip()
SUPABASE_EMAIL_SETTINGS_OBJECT_KEY = os.getenv(
    "SUPABASE_EMAIL_SETTINGS_OBJECT_KEY",
    "email_settings.json"
).strip()
_SUPABASE_CLIENT = None
DEPARTMENTS = [
    "Admin Office",
    "Admission Office",
    "One-Stop Office",
    "Library"
]

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


def get_supabase_client():
    """Create and cache Supabase client when environment is configured."""
    global _SUPABASE_CLIENT
    if _SUPABASE_CLIENT is not None:
        return _SUPABASE_CLIENT

    if create_client is None or not SUPABASE_URL or not SUPABASE_KEY:
        return None

    try:
        _SUPABASE_CLIENT = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"Supabase initialization failed: {e}")
        _SUPABASE_CLIENT = None
    return _SUPABASE_CLIENT

# ============================================================
# EMAIL SETTINGS — stored in email_settings.json
# So the admin can change them from the web UI without
# editing app.py manually.
# ============================================================

def load_email_settings():
    """
    Read Gmail credentials.

    Priority:
    1) Supabase Storage object (persisted on Vercel)
    2) Local `email_settings.json` fallback (dev)
    """
    client = get_supabase_client()
    if client:
        try:
            raw = client.storage.from_(SUPABASE_STORAGE_BUCKET).download(
                SUPABASE_EMAIL_SETTINGS_OBJECT_KEY
            )
            if raw:
                return json.loads(raw.decode("utf-8"))
        except Exception as e:
            print(f"Supabase email-settings load failed; falling back to local file. Error: {e}")

    if os.path.exists(EMAIL_SETTINGS_FILE):
        with open(EMAIL_SETTINGS_FILE, "r") as f:
            return json.load(f)

    return {
        "sender":   "",
        "password": "",
        "enabled":  False
    }


def save_email_settings(settings):
    """
    Persist Gmail credentials.

    Priority:
    1) Supabase Storage object
    2) Local `email_settings.json` fallback
    """
    client = get_supabase_client()
    if client:
        try:
            client.storage.from_(SUPABASE_STORAGE_BUCKET).upload(
                SUPABASE_EMAIL_SETTINGS_OBJECT_KEY,
                json.dumps(settings).encode("utf-8"),
                {
                    "content-type": "application/json",
                    "x-upsert": "true"
                }
            )
            return
        except Exception as e:
            print(f"Supabase email-settings save failed; falling back to local file. Error: {e}")

    with open(EMAIL_SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=4)


# ============================================================
# DATA STORAGE (Supabase with local fallback)
# ============================================================

def _load_local_data():
    """Read data.json safely."""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                content = f.read().strip()
                if not content:
                    # File exists but is empty — return blank structure
                    return {"users": [], "items": []}
                return json.loads(content)
        except json.JSONDecodeError:
            # File is corrupt — return blank structure
            print("WARNING: data.json is corrupt. Starting fresh.")
            return {"users": [], "items": []}
    return {"users": [], "items": []}


def _save_local_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)


def load_data():
    """Read app data from Supabase Storage; fallback to local json if unavailable."""
    client = get_supabase_client()
    if client:
        try:
            raw = client.storage.from_(SUPABASE_STORAGE_BUCKET).download(SUPABASE_DATA_OBJECT_KEY)
            if raw:
                return json.loads(raw.decode("utf-8"))
        except Exception as e:
            print(f"Supabase data load failed; falling back to local data.json. Error: {e}")

    local_data = _load_local_data()

    # Bootstrap storage on first run (so future invocations persist).
    if client:
        try:
            client.storage.from_(SUPABASE_STORAGE_BUCKET).upload(
                SUPABASE_DATA_OBJECT_KEY,
                json.dumps(local_data).encode("utf-8"),
                {
                    "content-type": "application/json",
                    "x-upsert": "true"
                }
            )
        except Exception as e:
            print(f"Supabase data bootstrap failed; continuing with local data.json. Error: {e}")

    return local_data


def save_data(data):
    client = get_supabase_client()
    if client:
        try:
            client.storage.from_(SUPABASE_STORAGE_BUCKET).upload(
                SUPABASE_DATA_OBJECT_KEY,
                json.dumps(data).encode("utf-8"),
                {
                    "content-type": "application/json",
                    "x-upsert": "true"
                }
            )
            return
        except Exception as e:
            print(f"Supabase data save failed; writing local data.json. Error: {e}")

    _save_local_data(data)


def ensure_item_defaults(item):
    """Backfill newly introduced workflow fields for older item records."""
    if "submitted_to" not in item:
        item["submitted_to"] = "self"
    if "submitted_department" not in item:
        item["submitted_department"] = ""
    if "holder_contact" not in item:
        item["holder_contact"] = ""
    if "department_verification_status" not in item:
        item["department_verification_status"] = "not_required"
    if "department_verified_by" not in item:
        item["department_verified_by"] = ""
    if "department_verified_at" not in item:
        item["department_verified_at"] = ""
    if "claim_status" not in item:
        item["claim_status"] = "none"
    if "claim_requested_by" not in item:
        item["claim_requested_by"] = ""
    if "claim_requested_at" not in item:
        item["claim_requested_at"] = ""
    if "claim_description" not in item:
        item["claim_description"] = ""
    if "claim_reviewed_by" not in item:
        item["claim_reviewed_by"] = ""
    if "claim_reviewed_at" not in item:
        item["claim_reviewed_at"] = ""
    if "claim_review_notes" not in item:
        item["claim_review_notes"] = ""


def ensure_data_defaults(data):
    changed = False
    for item in data.get("items", []):
        before = dict(item)
        ensure_item_defaults(item)
        if before != item:
            changed = True
    if changed:
        save_data(data)


# ============================================================
# POINTS SYSTEM
# Points awarded when a user submits a report:
#   Found item  → +50 points
#   Lost item   → +25 points
# ============================================================

POINTS_FOR_FOUND = 50
POINTS_FOR_LOST  = 25


def award_points(user_id, status):
    """
    Add reward points to a user's account.
    Called every time they successfully submit a report.
    """
    data = load_data()

    for user in data["users"]:
        if user["id"] == user_id:
            # Add points field if it doesn't exist yet (old accounts)
            if "points" not in user:
                user["points"] = 0

            if status == "found":
                user["points"] = user["points"] + POINTS_FOR_FOUND
                print(f"Awarded {POINTS_FOR_FOUND} pts to {user['name']} (found item)")
            else:
                user["points"] = user["points"] + POINTS_FOR_LOST
                print(f"Awarded {POINTS_FOR_LOST} pts to {user['name']} (lost item)")
            break

    save_data(data)


# ============================================================
# AUTO-ARCHIVING
# Items that are still "found" or "lost" after 60 days
# are automatically moved to status = "archived".
# This function runs on every page load — no cron job needed.
# ============================================================

ARCHIVE_AFTER_DAYS = 60


def run_archiving():
    """
    Check all items and archive any that are older than 60 days.
    Only affects items with status 'found' or 'lost'.
    Items already 'recovered' or 'archived' are left alone.
    """
    data    = load_data()
    today   = datetime.now().date()
    changed = 0

    for item in data["items"]:
        # Skip already-archived or recovered items
        if item["status"] in ("archived", "recovered"):
            continue

        # Get the date the item was submitted
        date_str = item.get("date_submitted", "")
        if not date_str:
            continue

        try:
            # date_submitted format is "YYYY-MM-DD HH:MM"
            submitted_date = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        except ValueError:
            continue

        # Calculate how many days old this item is
        age_days = (today - submitted_date).days

        if age_days >= ARCHIVE_AFTER_DAYS:
            item["status"] = "archived"
            changed += 1

    if changed > 0:
        save_data(data)
        print(f"Auto-archived {changed} item(s) older than {ARCHIVE_AFTER_DAYS} days.")


# ============================================================
# STUDENT DATABASE (26 students)
# Roll on card : 22I-1898   →   Email : i221898@isb.nu.edu.pk
# ============================================================

STUDENT_DB = [
    {"roll": "24i-0001", "name": "Ali Hassan",      "email": "i240001@isb.nu.edu.pk"},
    {"roll": "24i-0002", "name": "Sara Khan",        "email": "i240002@isb.nu.edu.pk"},
    {"roll": "24i-0003", "name": "Ahmed Raza",       "email": "i240003@isb.nu.edu.pk"},
    {"roll": "24i-0004", "name": "Fatima Malik",     "email": "i240004@isb.nu.edu.pk"},
    {"roll": "24i-0005", "name": "Usman Tariq",      "email": "i240005@isb.nu.edu.pk"},
    {"roll": "24i-0006", "name": "Zainab Siddiqui",  "email": "i240006@isb.nu.edu.pk"},
    {"roll": "24i-0007", "name": "Hamza Sheikh",     "email": "i240007@isb.nu.edu.pk"},
    {"roll": "24i-0008", "name": "Ayesha Nawaz",     "email": "i240008@isb.nu.edu.pk"},
    {"roll": "24i-0009", "name": "Omar Khalid",      "email": "i240009@isb.nu.edu.pk"},
    {"roll": "24i-0010", "name": "Hira Baig",        "email": "i240010@isb.nu.edu.pk"},
    {"roll": "24i-0031", "name": "Musa Javed",       "email": "i240031@isb.nu.edu.pk"},
    {"roll": "24i-0129", "name": "Ashhad Saeed",     "email": "i240129@isb.nu.edu.pk"},
    {"roll": "24i-2071", "name": "Fahad Farooq",     "email": "i242071@isb.nu.edu.pk"},
    {"roll": "23i-0101", "name": "Bilal Ahmed",      "email": "i230101@isb.nu.edu.pk"},
    {"roll": "23i-0202", "name": "Nadia Iqbal",      "email": "i230202@isb.nu.edu.pk"},
    {"roll": "23i-0303", "name": "Tariq Mehmood",    "email": "i230303@isb.nu.edu.pk"},
    {"roll": "23i-0404", "name": "Sana Rashid",      "email": "i230404@isb.nu.edu.pk"},
    {"roll": "23i-0505", "name": "Kamran Butt",      "email": "i230505@isb.nu.edu.pk"},
    {"roll": "22i-0011", "name": "Rabia Zahid",      "email": "i220011@isb.nu.edu.pk"},
    {"roll": "22i-0022", "name": "Daniyal Chaudhry", "email": "i220022@isb.nu.edu.pk"},
    {"roll": "22i-0033", "name": "Maham Farhan",     "email": "i220033@isb.nu.edu.pk"},
    {"roll": "22i-0044", "name": "Saad Mirza",       "email": "i220044@isb.nu.edu.pk"},
    {"roll": "21i-0111", "name": "Iqra Nasir",       "email": "i210111@isb.nu.edu.pk"},
    {"roll": "21i-0222", "name": "Faizan Ali",       "email": "i210222@isb.nu.edu.pk"},
    {"roll": "21i-0333", "name": "Mehreen Aslam",    "email": "i210333@isb.nu.edu.pk"},
    {"roll": "22i-1898", "name": "Sufyan Nasr",      "email": "i221898@isb.nu.edu.pk"},
]


def setup_sample_data():
    """Create sample accounts on first run, including admin"""
    data = load_data()

    if len(data["users"]) == 0:
        sample_users = [
            # ---- ADMIN account ----
            {
                "id":       "admin",
                "name":     "Admin",
                "email":    "admin@lostfound.com",
                "password": "admin123",
                "is_admin": True
            },
            # ---- Regular student accounts ----
            {"id": "u001", "name": "Ali Hassan",  "email": "i24-0001@isb.nu.edu.pk", "password": "password123", "is_admin": False, "points": 150},
            {"id": "u002", "name": "Sara Khan",   "email": "i24-0002@isb.nu.edu.pk", "password": "password123", "is_admin": False, "points": 200},
            {"id": "u003", "name": "Ahmed Raza",  "email": "i24-0003@isb.nu.edu.pk", "password": "password123", "is_admin": False, "points": 75},
            {"id": "u004", "name": "Fatima Malik","email": "i24-0004@isb.nu.edu.pk", "password": "password123", "is_admin": False, "points": 320},
            {"id": "u005", "name": "Usman Tariq", "email": "i24-0005@isb.nu.edu.pk", "password": "password123", "is_admin": False, "points": 90},
            {"id": "u006", "name": "Musa Javed",  "email": "i24-0031@isb.nu.edu.pk", "password": "password123", "is_admin": False, "points": 50},
            {"id": "u007", "name": "Ashhad Saeed","email": "i24-0129@isb.nu.edu.pk", "password": "password123", "is_admin": False, "points": 25},
            {"id": "u008", "name": "Fahad Farooq","email": "i24-2071@isb.nu.edu.pk", "password": "password123", "is_admin": False, "points": 100},
        ]
        data["users"] = sample_users
        save_data(data)


# ============================================================
# EMAIL — actual Gmail SMTP sending
# ============================================================

def send_email_notification(recipient_email, recipient_name, item_location, reporter_name):
    """
    Send a real email via Gmail SMTP.
    Credentials come from email_settings.json (set by admin in the UI).
    If not configured, just prints to console.
    """
    settings = load_email_settings()

    subject = "[Lost & Found FAST NUCES] Your ID Card has been found!"
    body = (
        f"Assalam o Alaikum {recipient_name},\n\n"
        f"Great news! Your FAST NUCES ID card has been found on campus.\n\n"
        f"Found at : {item_location}\n"
        f"Found by : {reporter_name}\n\n"
        f"Please visit the Lost & Found desk or contact the reporter to\n"
        f"collect your card. Bring any other ID for verification.\n\n"
        f"---\n"
        f"FAST NUCES Islamabad — Lost & Found System\n"
        f"(This is an automated notification. Do not reply to this email.)"
    )

    if not settings.get("enabled") or not settings.get("sender") or not settings.get("password"):
        # Not configured — simulate in console
        print("")
        print("=" * 55)
        print("  EMAIL (simulated — configure via Admin > Email Settings)")
        print(f"  To      : {recipient_email}")
        print(f"  Name    : {recipient_name}")
        print(f"  Found at: {item_location}")
        print("=" * 55)
        return True, "simulated"

    try:
        msg = MIMEMultipart()
        msg["From"]    = settings["sender"]
        msg["To"]      = recipient_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(settings["sender"], settings["password"])
        server.sendmail(settings["sender"], recipient_email, msg.as_string())
        server.quit()

        print(f"Email sent to {recipient_email}")
        return True, "sent"

    except Exception as e:
        print(f"Email sending failed: {e}")
        return False, str(e)


# ============================================================
# OCR HELPERS
# ============================================================

def allowed_file(filename):
    if "." not in filename:
        return False
    return filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_uploaded_image(file):
    if not file or file.filename == "":
        return None
    if not allowed_file(file.filename):
        return None
    ext = file.filename.rsplit(".", 1)[1].lower()
    unique_name = str(uuid.uuid4())[:12] + "." + ext

    # Try Supabase Storage first when configured.
    client = get_supabase_client()
    if client:
        try:
            file_bytes = file.read()
            file.stream.seek(0)
            path = f"uploads/{unique_name}"
            content_type = "image/jpeg" if ext == "jpg" else f"image/{ext}"
            client.storage.from_(SUPABASE_STORAGE_BUCKET).upload(
                path,
                file_bytes,
                {"content-type": content_type}
            )
            public_url = client.storage.from_(SUPABASE_STORAGE_BUCKET).get_public_url(path)
            if public_url:
                return public_url
        except Exception as e:
            print(f"Supabase image upload failed; storing locally. Error: {e}")

    file.save(os.path.join(UPLOAD_FOLDER, unique_name))
    return unique_name


def roll_number_to_email(roll):
    """22i-1898 → i221898@isb.nu.edu.pk"""
    roll = roll.strip().lower()
    match = re.search(r"(\d{2})([a-z])-?(\d{4})", roll)
    if not match:
        return None
    return f"{match.group(2)}{match.group(1)}{match.group(3)}@isb.nu.edu.pk"


def lookup_student_by_roll(roll_number):
    roll_clean = roll_number.strip().lower().replace(" ", "")
    for student in STUDENT_DB:
        if student["roll"].strip().lower().replace(" ", "") == roll_clean:
            return student
    return None


def extract_roll_from_text(text):
    """
    Parse OCR text to find a FAST NUCES roll number.
    Handles OCR confusion: I → 1, l, L, |
    """
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Normalise: 22[1/l/L] → 22I
        normalised = re.sub(r"(\d{2})[1lL\|](-\d{4})", r"\1I\2", line)
        normalised = re.sub(r"(\d{2})[1lL\|](\d{4})",  r"\1I-\2", normalised)
        match = re.search(r"(\d{2}[iI]-\d{4})", normalised, re.IGNORECASE)
        if match:
            roll = re.sub(r"(\d{2})[Ii]", lambda m: m.group(0)[:-1] + "i", match.group(1))
            print(f"Roll extracted: {roll}  (line: {repr(line)})")
            return roll
    return None


def ocr_scan_id_card(image_path):
    """
    Multi-pass OCR scan for FAST NUCES ID cards.
    Returns (roll_string_or_None, student_dict_or_None)
    """
    if not OCR_AVAILABLE:
        print("OCR dependencies are unavailable in this environment.")
        return None, None

    try:
        img = Image.open(image_path)
        w, h = img.size
        print(f"\nScanning: {w}x{h}")

        # Ensure minimum width for OCR accuracy
        if w < 1200:
            scale = 1200 / w
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
            w, h = img.size

        arr = np.array(img)

        # Pass 1: standard greyscale
        grey_big = img.convert("L").resize((w * 2, h * 2), Image.LANCZOS)
        text1 = pytesseract.image_to_string(grey_big, config="--psm 6 --oem 3")
        print(f"Pass 1:\n{text1}")
        roll = extract_roll_from_text(text1)
        if roll:
            return roll, lookup_student_by_roll(roll)

        # Pass 2+: G-channel adaptive threshold
        # Roll number = dark navy text on dark green bg → isolate with G channel
        sources = [
            ("full",      arr),
            ("bottom30%", arr[int(h * 0.70):, :, :]),
            ("bottom20%", arr[int(h * 0.80):, :, :]),
        ]

        for source_name, source_arr in sources:
            g = source_arr[:, :, 1].astype(float)
            mean_g = g.mean()

            for factor in [0.50, 0.55, 0.60, 0.65, 0.70, 0.75]:
                thresh = mean_g * factor
                mask = np.where(g < thresh, 0, 255).astype(np.uint8)
                mh, mw = mask.shape
                scale_up = max(4000, mw) / mw
                big = Image.fromarray(mask).resize(
                    (int(mw * scale_up), int(mh * scale_up)), Image.NEAREST
                )
                for cfg in ["--psm 6 --oem 3", "--psm 11 --oem 3"]:
                    text = pytesseract.image_to_string(big, config=cfg)
                    roll = extract_roll_from_text(text)
                    if roll:
                        print(f"Found in {source_name}, factor={factor}")
                        return roll, lookup_student_by_roll(roll)

        # Pass 3: blur then threshold
        arr2 = np.array(img.filter(ImageFilter.GaussianBlur(1)))
        g2 = arr2[:, :, 1].astype(float)
        mean_g2 = g2.mean()
        for factor in [0.50, 0.55, 0.60, 0.65, 0.70]:
            thresh = mean_g2 * factor
            mask = np.where(g2 < thresh, 0, 255).astype(np.uint8)
            mh, mw = mask.shape
            big = Image.fromarray(mask).resize((mw * 4, mh * 4), Image.NEAREST)
            text = pytesseract.image_to_string(big, config="--psm 6 --oem 3")
            roll = extract_roll_from_text(text)
            if roll:
                return roll, lookup_student_by_roll(roll)

        print("No roll number found.")
        return None, None

    except Exception as e:
        print(f"OCR error: {e}")
        import traceback
        traceback.print_exc()
        return None, None


# ============================================================
# AUTH HELPERS
# ============================================================

def get_logged_in_user():
    if "user_id" not in session:
        return None
    data = load_data()
    for user in data["users"]:
        if user["id"] == session["user_id"]:
            return user
    return None


def require_admin(f):
    """Decorator — redirects non-admins away from admin pages"""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_logged_in_user()
        if not user or not user.get("is_admin"):
            flash("Admin access required.", "error")
            return redirect(url_for("home"))
        return f(*args, **kwargs)
    return decorated


# ============================================================
# ROUTES — PUBLIC
# ============================================================

@app.route("/")
def home():
    run_archiving()   # archive items older than 60 days on every home page visit
    data         = load_data()
    ensure_data_defaults(data)
    current_user = get_logged_in_user()
    recent_items = list(reversed(data["items"][-3:]))
    total        = len(data["items"])
    return render_template("home.html",
        current_user=current_user,
        recent_items=recent_items,
        total=total
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if get_logged_in_user():
        return redirect(url_for("home"))

    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        if not email or not password:
            flash("Please fill in all fields.", "error")
            return render_template("login.html")

        data = load_data()
        matched = None
        for user in data["users"]:
            if user["email"].lower() == email and user["password"] == password:
                matched = user
                break

        if matched:
            session["user_id"] = matched["id"]
            flash(f"Welcome back, {matched['name']}!", "success")
            # Send admin to admin panel directly
            if matched.get("is_admin"):
                return redirect(url_for("admin_panel"))
            return redirect(url_for("home"))
        else:
            flash("Incorrect email or password.", "error")

    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if get_logged_in_user():
        return redirect(url_for("home"))

    if request.method == "POST":
        name     = request.form.get("name", "").strip()
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()
        confirm  = request.form.get("confirm_password", "").strip()

        if not name or not email or not password or not confirm:
            flash("Please fill in all fields.", "error")
            return render_template("signup.html")

        if "@isb.nu.edu.pk" not in email and "@nu.edu.pk" not in email:
            flash("Please use your FAST NUCES email (e.g. i24-XXXX@isb.nu.edu.pk).", "error")
            return render_template("signup.html")

        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("signup.html")

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("signup.html")

        data = load_data()
        for user in data["users"]:
            if user["email"].lower() == email:
                flash("An account with this email already exists.", "error")
                return render_template("signup.html")

        new_user = {
            "id":       "u_" + str(uuid.uuid4())[:8],
            "name":     name,
            "email":    email,
            "password": password,
            "is_admin": False
        }
        data["users"].append(new_user)
        save_data(data)

        session["user_id"] = new_user["id"]
        flash(f"Account created! Welcome, {name}!", "success")
        return redirect(url_for("home"))

    return render_template("signup.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("home"))


@app.route("/submissions")
def submissions():
    run_archiving()   # archive items older than 60 days
    current_user = get_logged_in_user()
    data         = load_data()
    ensure_data_defaults(data)

    q = request.args.get("q", "").strip().lower()
    category = request.args.get("category", "").strip()
    item_status = request.args.get("status", "").strip()
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()
    submitted_to = request.args.get("submitted_to", "").strip()

    filtered = []
    for item in data["items"]:
        haystack = " ".join([
            item.get("title", ""),
            item.get("description", ""),
            item.get("category", ""),
            item.get("location", ""),
            item.get("reported_by_name", "")
        ]).lower()
        if q and q not in haystack:
            continue
        if category and item.get("category") != category:
            continue
        if item_status and item.get("status") != item_status:
            continue
        if submitted_to and item.get("submitted_to", "self") != submitted_to:
            continue

        submitted_day = item.get("date_submitted", "")[:10]
        if date_from and submitted_day and submitted_day < date_from:
            continue
        if date_to and submitted_day and submitted_day > date_to:
            continue

        filtered.append(item)

    items = list(reversed(filtered))
    categories = sorted({i.get("category", "") for i in data["items"] if i.get("category")})
    return render_template("submissions.html",
        current_user=current_user,
        items=items,
        categories=categories,
        departments=DEPARTMENTS,
        search_filters={
            "q": q,
            "category": category,
            "status": item_status,
            "date_from": date_from,
            "date_to": date_to,
            "submitted_to": submitted_to
        }
    )


@app.route("/submissions/<item_id>", methods=["GET", "POST"])
def submission_detail(item_id):
    current_user = get_logged_in_user()
    data = load_data()
    ensure_data_defaults(data)

    target = None
    for item in data["items"]:
        if item["id"] == item_id:
            target = item
            break

    if not target:
        flash("Submission not found.", "error")
        return redirect(url_for("submissions"))

    if request.method == "POST":
        if not current_user:
            flash("Please log in to request a claim.", "error")
            return redirect(url_for("login"))

        claim_description = request.form.get("claim_description", "").strip()
        if not claim_description:
            flash("Please provide claim details for verification.", "error")
            return redirect(url_for("submission_detail", item_id=item_id))

        if target.get("claim_status") == "pending":
            flash("A claim is already pending admin review.", "info")
            return redirect(url_for("submission_detail", item_id=item_id))

        target["claim_status"] = "pending"
        target["claim_requested_by"] = current_user["name"]
        target["claim_requested_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        target["claim_description"] = claim_description
        target["claim_reviewed_by"] = ""
        target["claim_reviewed_at"] = ""
        target["claim_review_notes"] = ""
        save_data(data)
        flash("Claim request submitted. Admin will verify your details.", "success")
        return redirect(url_for("submission_detail", item_id=item_id))

    return render_template("submission_detail.html",
        current_user=current_user,
        item=target
    )


# ============================================================
# ROUTE — REPORT ITEM (with email confirm flow)
# ============================================================

@app.route("/report", methods=["GET", "POST"])
def report():
    current_user = get_logged_in_user()
    if not current_user:
        flash("Please log in to report an item.", "error")
        return redirect(url_for("login"))

    if request.method == "POST":
        title             = request.form.get("title", "").strip()
        category          = request.form.get("category", "").strip()
        location          = request.form.get("location", "").strip()
        date_found        = request.form.get("date_found", "").strip()
        description       = request.form.get("description", "").strip()
        status            = request.form.get("status", "found").strip()
        submitted_to      = request.form.get("submitted_to", "self").strip()
        submitted_department = request.form.get("submitted_department", "").strip()
        holder_contact    = request.form.get("holder_contact", "").strip()
        scanned_roll      = request.form.get("scanned_roll", "").strip()
        scanned_email     = request.form.get("scanned_email", "").strip()
        scanned_name      = request.form.get("scanned_name", "").strip()
        uploaded_filename = request.form.get("uploaded_filename", "").strip()
        # This is set to "yes" / "no" by the confirmation UI in the browser
        send_email_choice = request.form.get("send_email_choice", "").strip()

        if not title or not category or not location or not description:
            flash("Please fill in all required fields.", "error")
            return render_template("report.html", current_user=current_user, departments=DEPARTMENTS)

        if status == "found":
            if submitted_to == "department":
                if submitted_department not in DEPARTMENTS:
                    flash("Please choose a valid department for submission.", "error")
                    return render_template("report.html", current_user=current_user, departments=DEPARTMENTS)
                holder_contact = ""
            else:
                submitted_to = "self"
                submitted_department = ""
                if not holder_contact:
                    flash("Contact number is required when you keep the item yourself.", "error")
                    return render_template("report.html", current_user=current_user, departments=DEPARTMENTS)

        # Handle image
        image_filename = uploaded_filename or None
        if not image_filename:
            file = request.files.get("image")
            if file and file.filename:
                image_filename = save_uploaded_image(file)

        # Save item
        new_item = {
            "id":                "item_" + str(uuid.uuid4())[:8],
            "title":             title,
            "category":          category,
            "location":          location,
            "date_found":        date_found,
            "description":       description,
            "status":            status,
            "image":             image_filename,
            "reported_by_id":    current_user["id"],
            "reported_by_name":  current_user["name"],
            "reported_by_email": current_user["email"],
            "date_submitted":    datetime.now().strftime("%Y-%m-%d %H:%M"),
            "submitted_to":      submitted_to,
            "submitted_department": submitted_department,
            "holder_contact":    holder_contact,
            "department_verification_status": "pending" if (status == "found" and submitted_to == "department") else "not_required",
            "department_verified_by": "",
            "department_verified_at": "",
            "claim_status": "none",
            "claim_requested_by": "",
            "claim_requested_at": "",
            "claim_description": "",
            "claim_reviewed_by": "",
            "claim_reviewed_at": "",
            "claim_review_notes": ""
        }

        data = load_data()
        data["items"].append(new_item)
        save_data(data)

        # ---- AWARD POINTS ----
        # Give the reporter points for submitting this report
        award_points(current_user["id"], status)

        # ---- EMAIL FLOW ----
        is_id_card = (category == "ID Card") or ("id card" in title.lower())

        if status == "found" and is_id_card and scanned_email and scanned_email != "unknown":
            # User confirmed they want to send email ("yes") or declined ("no")
            if send_email_choice == "yes":
                success, mode = send_email_notification(
                    recipient_email=scanned_email,
                    recipient_name=scanned_name or "Student",
                    item_location=location,
                    reporter_name=current_user["name"]
                )
                if success and mode == "sent":
                    flash(f"Item reported! Email sent to {scanned_email}.", "success")
                elif success and mode == "simulated":
                    flash(
                        f"Item reported! Owner identified: {scanned_name} ({scanned_email}). "
                        f"Email not sent — configure Gmail in Admin → Email Settings.",
                        "success"
                    )
                else:
                    flash(f"Item reported. Email failed to send: {mode}", "error")
            else:
                # User chose not to send email
                flash("Item reported successfully. No email was sent.", "success")
        else:
            flash("Item reported successfully!", "success")

        return redirect(url_for("submissions"))

    return render_template("report.html", current_user=current_user, departments=DEPARTMENTS)


# ============================================================
# ROUTE — AJAX: scan ID card image
# ============================================================

@app.route("/scan-id-card", methods=["POST"])
def scan_id_card():
    if "image" not in request.files:
        return jsonify({"success": False, "message": "No image received"})

    file = request.files["image"]
    if not file or not file.filename or not allowed_file(file.filename):
        return jsonify({"success": False, "message": "Invalid image file"})

    ext = file.filename.rsplit(".", 1)[1].lower()
    temp_name = "scan_" + str(uuid.uuid4())[:12] + "." + ext
    image_path = os.path.join(UPLOAD_FOLDER, temp_name)
    file.save(image_path)

    # Store uploaded image in persistent storage for later submission flow.
    persisted_filename = temp_name
    client = get_supabase_client()
    if client:
        try:
            with open(image_path, "rb") as f:
                file_bytes = f.read()
            path = f"uploads/{str(uuid.uuid4())[:12]}.{ext}"
            content_type = "image/jpeg" if ext == "jpg" else f"image/{ext}"
            client.storage.from_(SUPABASE_STORAGE_BUCKET).upload(
                path,
                file_bytes,
                {"content-type": content_type}
            )
            public_url = client.storage.from_(SUPABASE_STORAGE_BUCKET).get_public_url(path)
            if public_url:
                persisted_filename = public_url
        except Exception as e:
            print(f"Supabase scan-image upload failed; using local file. Error: {e}")

    roll, student = ocr_scan_id_card(image_path)

    if student:
        return jsonify({
            "success":  True,
            "roll":     roll,
            "name":     student["name"],
            "email":    student["email"],
            "filename": persisted_filename
        })
    elif roll:
        guessed_email = roll_number_to_email(roll)
        return jsonify({
            "success":  True,
            "roll":     roll,
            "name":     "Student",
            "email":    guessed_email or "unknown",
            "filename": persisted_filename
        })
    else:
        return jsonify({
            "success":  False,
            "message":  "No roll number detected in image",
            "filename": persisted_filename
        })


@app.context_processor
def inject_template_helpers():
    def image_src(image_value):
        if not image_value:
            return ""
        value = str(image_value)
        if value.startswith("http://") or value.startswith("https://"):
            return value
        return url_for("static", filename="uploads/" + value)
    return {"image_src": image_src}


# ============================================================
# ROUTE — AJAX: send email (called from report page confirmation)
# ============================================================

@app.route("/send-notification", methods=["POST"])
def send_notification():
    """
    AJAX endpoint — called when user clicks 'Yes, Send Email'
    on the report form after OCR detects a roll number.
    """
    current_user = get_logged_in_user()
    if not current_user:
        return jsonify({"success": False, "message": "Not logged in"})

    body = request.get_json()
    if not body:
        return jsonify({"success": False, "message": "No data received"})

    recipient_email = body.get("email", "")
    recipient_name  = body.get("name", "Student")
    item_location   = body.get("location", "Campus")
    reporter_name   = current_user["name"]

    if not recipient_email:
        return jsonify({"success": False, "message": "No email address"})

    success, mode = send_email_notification(
        recipient_email=recipient_email,
        recipient_name=recipient_name,
        item_location=item_location,
        reporter_name=reporter_name
    )

    settings = load_email_settings()
    is_configured = settings.get("enabled") and settings.get("sender")

    if success and mode == "sent":
        return jsonify({
            "success": True,
            "message": f"Email sent to {recipient_email}",
            "mode":    "sent"
        })
    elif success and mode == "simulated":
        return jsonify({
            "success": True,
            "message": "Simulated (Gmail not configured). Go to Admin → Email Settings.",
            "mode":    "simulated"
        })
    else:
        return jsonify({
            "success": False,
            "message": f"Failed: {mode}"
        })


# ============================================================
# LEADERBOARD ROUTE
# ============================================================

@app.route("/leaderboard")
def leaderboard():
    """
    Shows all users ranked by their reward points.
    Highest points = top of the list.
    """
    run_archiving()
    current_user = get_logged_in_user()
    data         = load_data()

    # Build leaderboard: only non-admin users, sorted by points descending
    board = []
    for user in data["users"]:
        if user.get("is_admin"):
            continue   # admin does not appear on leaderboard
        board.append({
            "id":     user["id"],
            "name":   user["name"],
            "email":  user["email"],
            "points": user.get("points", 0)
        })

    # Sort highest points first
    board.sort(key=lambda u: u["points"], reverse=True)

    return render_template("Leaderboard.html",
        current_user=current_user,
        board=board
    )


# ============================================================
# ARCHIVE ROUTE — view all archived items
# ============================================================

@app.route("/archive")
def archive():
    """
    Shows items that have been automatically archived after 60 days.
    """
    run_archiving()
    current_user = get_logged_in_user()
    data         = load_data()

    archived_items = [i for i in data["items"] if i["status"] == "archived"]
    archived_items = list(reversed(archived_items))

    return render_template("Archive.html",
        current_user=current_user,
        items=archived_items
    )


# ============================================================
# ADMIN ROUTES
# ============================================================

@app.route("/admin")
@require_admin
def admin_panel():
    """Admin dashboard — overview of everything"""
    current_user = get_logged_in_user()
    data         = load_data()
    ensure_data_defaults(data)
    settings     = load_email_settings()

    total_users    = len(data["users"])
    total_items    = len(data["items"])
    found_items    = sum(1 for i in data["items"] if i["status"] == "found")
    lost_items     = sum(1 for i in data["items"] if i["status"] == "lost")
    archived_items = sum(1 for i in data["items"] if i["status"] == "archived")
    pending_department_items = sum(1 for i in data["items"] if i.get("department_verification_status") == "pending")
    pending_claim_items = sum(1 for i in data["items"] if i.get("claim_status") == "pending")

    return render_template("admin.html",
        current_user=current_user,
        users=data["users"],
        items=list(reversed(data["items"])),
        total_users=total_users,
        total_items=total_items,
        found_items=found_items,
        lost_items=lost_items,
        archived_items=archived_items,
        pending_department_items=pending_department_items,
        pending_claim_items=pending_claim_items,
        departments=DEPARTMENTS,
        email_settings=settings
    )


@app.route("/admin/verify-department/<item_id>", methods=["POST"])
@require_admin
def admin_verify_department(item_id):
    current_user = get_logged_in_user()
    data = load_data()
    ensure_data_defaults(data)

    for item in data["items"]:
        if item["id"] == item_id:
            if item.get("submitted_to") != "department":
                flash("This item is not submitted to a department.", "error")
                return redirect(url_for("admin_panel"))
            item["department_verification_status"] = "verified"
            item["department_verified_by"] = current_user["name"]
            item["department_verified_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            save_data(data)
            flash(f"Department verification recorded for {item['title']}.", "success")
            return redirect(url_for("admin_panel"))

    flash("Item not found.", "error")
    return redirect(url_for("admin_panel"))


@app.route("/admin/review-claim/<item_id>", methods=["POST"])
@require_admin
def admin_review_claim(item_id):
    current_user = get_logged_in_user()
    decision = request.form.get("decision", "").strip()
    notes = request.form.get("notes", "").strip()

    if decision not in ("approved", "rejected"):
        flash("Invalid claim decision.", "error")
        return redirect(url_for("admin_panel"))

    data = load_data()
    ensure_data_defaults(data)

    for item in data["items"]:
        if item["id"] == item_id:
            if item.get("claim_status") != "pending":
                flash("No pending claim exists for this item.", "error")
                return redirect(url_for("admin_panel"))

            if item.get("submitted_to") == "self":
                flash("Self-held items are handled directly between users and cannot be admin-verified.", "info")
                return redirect(url_for("admin_panel"))

            item["claim_status"] = decision
            item["claim_reviewed_by"] = current_user["name"]
            item["claim_reviewed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            item["claim_review_notes"] = notes

            if decision == "approved":
                item["status"] = "recovered"

            save_data(data)
            flash(f"Claim {decision} for {item['title']}.", "success")
            return redirect(url_for("admin_panel"))

    flash("Item not found.", "error")
    return redirect(url_for("admin_panel"))


@app.route("/admin/delete-item/<item_id>", methods=["POST"])
@require_admin
def admin_delete_item(item_id):
    """Admin: delete any item"""
    data = load_data()
    before = len(data["items"])
    data["items"] = [i for i in data["items"] if i["id"] != item_id]
    save_data(data)
    if len(data["items"]) < before:
        flash("Item deleted.", "success")
    else:
        flash("Item not found.", "error")
    return redirect(url_for("admin_panel"))


@app.route("/admin/edit-item/<item_id>", methods=["GET", "POST"])
@require_admin
def admin_edit_item(item_id):
    """Admin: edit any item's details"""
    current_user = get_logged_in_user()
    data         = load_data()
    ensure_data_defaults(data)

    # Find the item
    target = None
    for item in data["items"]:
        if item["id"] == item_id:
            target = item
            break

    if not target:
        flash("Item not found.", "error")
        return redirect(url_for("admin_panel"))

    if request.method == "POST":
        target["title"]       = request.form.get("title", target["title"]).strip()
        target["category"]    = request.form.get("category", target["category"]).strip()
        target["location"]    = request.form.get("location", target["location"]).strip()
        target["description"] = request.form.get("description", target["description"]).strip()
        target["status"]      = request.form.get("status", target["status"]).strip()
        target["date_found"]  = request.form.get("date_found", target.get("date_found", "")).strip()
        target["submitted_to"] = request.form.get("submitted_to", target.get("submitted_to", "self")).strip()
        target["submitted_department"] = request.form.get("submitted_department", target.get("submitted_department", "")).strip()
        target["holder_contact"] = request.form.get("holder_contact", target.get("holder_contact", "")).strip()

        if target["submitted_to"] == "department":
            if target["submitted_department"] not in DEPARTMENTS:
                flash("Please select a valid department.", "error")
                return render_template("admin_edit_item.html", current_user=current_user, item=target, departments=DEPARTMENTS)
            target["holder_contact"] = ""
            if target.get("department_verification_status") == "not_required":
                target["department_verification_status"] = "pending"
        else:
            target["submitted_to"] = "self"
            target["submitted_department"] = ""
            if not target["holder_contact"]:
                flash("Contact number is required for self-held items.", "error")
                return render_template("admin_edit_item.html", current_user=current_user, item=target, departments=DEPARTMENTS)
            target["department_verification_status"] = "not_required"
            target["department_verified_by"] = ""
            target["department_verified_at"] = ""

        save_data(data)
        flash("Item updated.", "success")
        return redirect(url_for("admin_panel"))

    return render_template("admin_edit_item.html",
        current_user=current_user,
        item=target,
        departments=DEPARTMENTS
    )


@app.route("/admin/delete-user/<user_id>", methods=["POST"])
@require_admin
def admin_delete_user(user_id):
    """Admin: delete any user (cannot delete own account)"""
    current_user = get_logged_in_user()
    if user_id == current_user["id"]:
        flash("You cannot delete your own admin account.", "error")
        return redirect(url_for("admin_panel"))

    data = load_data()
    before = len(data["users"])
    data["users"] = [u for u in data["users"] if u["id"] != user_id]
    save_data(data)

    if len(data["users"]) < before:
        flash("User deleted.", "success")
    else:
        flash("User not found.", "error")

    return redirect(url_for("admin_panel"))


@app.route("/admin/toggle-admin/<user_id>", methods=["POST"])
@require_admin
def admin_toggle_admin(user_id):
    """Admin: grant or revoke admin access for a user"""
    current_user = get_logged_in_user()
    if user_id == current_user["id"]:
        flash("Cannot change your own admin status.", "error")
        return redirect(url_for("admin_panel"))

    data = load_data()
    for user in data["users"]:
        if user["id"] == user_id:
            user["is_admin"] = not user.get("is_admin", False)
            status = "granted" if user["is_admin"] else "revoked"
            flash(f"Admin access {status} for {user['name']}.", "success")
            break

    save_data(data)
    return redirect(url_for("admin_panel"))


@app.route("/admin/email-settings", methods=["GET", "POST"])
@require_admin
def admin_email_settings():
    """Admin: configure Gmail SMTP credentials"""
    current_user = get_logged_in_user()
    settings     = load_email_settings()

    if request.method == "POST":
        sender   = request.form.get("sender", "").strip()
        password = request.form.get("password", "").strip()
        enabled  = request.form.get("enabled") == "on"

        # Keep existing password if field left blank
        if not password:
            password = settings.get("password", "")

        settings = {
            "sender":   sender,
            "password": password,
            "enabled":  enabled
        }
        save_email_settings(settings)
        flash("Email settings saved.", "success")

        # Test the connection if enabled
        if enabled and sender and password:
            try:
                server = smtplib.SMTP("smtp.gmail.com", 587)
                server.starttls()
                server.login(sender, password)
                server.quit()
                flash("Gmail connection test passed! Emails will be sent.", "success")
            except Exception as e:
                flash(f"Gmail connection test FAILED: {e}", "error")

        return redirect(url_for("admin_email_settings"))

    return render_template("admin_email_settings.html",
        current_user=current_user,
        settings=settings
    )


@app.route("/admin/add-item", methods=["GET", "POST"])
@require_admin
def admin_add_item():
    """Admin: manually add any item"""
    current_user = get_logged_in_user()

    if request.method == "POST":
        title       = request.form.get("title", "").strip()
        category    = request.form.get("category", "").strip()
        location    = request.form.get("location", "").strip()
        description = request.form.get("description", "").strip()
        status      = request.form.get("status", "found").strip()
        date_found  = request.form.get("date_found", "").strip()
        submitted_to = request.form.get("submitted_to", "department").strip()
        submitted_department = request.form.get("submitted_department", "").strip()
        holder_contact = request.form.get("holder_contact", "").strip()

        if not title or not category or not location or not description:
            flash("Please fill in all required fields.", "error")
            return render_template("admin_add_item.html", current_user=current_user, departments=DEPARTMENTS)

        if status == "found" and submitted_to == "department" and submitted_department not in DEPARTMENTS:
            flash("Please choose a valid department.", "error")
            return render_template("admin_add_item.html", current_user=current_user, departments=DEPARTMENTS)

        if status == "found" and submitted_to != "department" and not holder_contact:
            flash("Contact number is required when holder keeps the item.", "error")
            return render_template("admin_add_item.html", current_user=current_user, departments=DEPARTMENTS)

        if submitted_to == "department":
            holder_contact = ""
        else:
            submitted_to = "self"
            submitted_department = ""

        new_item = {
            "id":                "item_" + str(uuid.uuid4())[:8],
            "title":             title,
            "category":          category,
            "location":          location,
            "date_found":        date_found,
            "description":       description,
            "status":            status,
            "image":             None,
            "reported_by_id":    current_user["id"],
            "reported_by_name":  "Admin",
            "reported_by_email": current_user["email"],
            "date_submitted":    datetime.now().strftime("%Y-%m-%d %H:%M"),
            "submitted_to":      submitted_to,
            "submitted_department": submitted_department,
            "holder_contact":    holder_contact,
            "department_verification_status": "pending" if (status == "found" and submitted_to == "department") else "not_required",
            "department_verified_by": "",
            "department_verified_at": "",
            "claim_status": "none",
            "claim_requested_by": "",
            "claim_requested_at": "",
            "claim_description": "",
            "claim_reviewed_by": "",
            "claim_reviewed_at": "",
            "claim_review_notes": ""
        }

        data = load_data()
        data["items"].append(new_item)
        save_data(data)
        flash("Item added successfully.", "success")
        return redirect(url_for("admin_panel"))

    return render_template("admin_add_item.html", current_user=current_user, departments=DEPARTMENTS)


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    setup_sample_data()

    print("")
    print("=" * 55)
    print("  Lost & Found — Iteration 1")
    print("  Open: http://localhost:5000")
    print("=" * 55)
    print("")
    print("  ADMIN login:")
    print("  admin@lostfound.com  /  admin123")
    print("  → Goes to /admin panel automatically")
    print("")
    print("  Student accounts (all password123):")
    print("  i240001@isb.nu.edu.pk")
    print("  i240031@isb.nu.edu.pk  (Musa)")
    print("  i240129@isb.nu.edu.pk  (Ashhad)")
    print("  i242071@isb.nu.edu.pk  (Fahad)")
    print("")
    print("  Email: configure at /admin/email-settings")
    print("")
    print("  New features:")
    print("  /leaderboard  — Points leaderboard")
    print("  /archive      — Items archived after 60 days")
    print("  Points: +50 for found item, +25 for lost item")
    print("=" * 55)
    print("")

    app.run(debug=True, port=5000)