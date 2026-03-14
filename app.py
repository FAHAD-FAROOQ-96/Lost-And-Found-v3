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
from PIL import Image, ImageFilter
import pytesseract
import numpy as np

# ============================================================
# TESSERACT PATH — required on Windows
# ============================================================
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

app = Flask(__name__)
app.secret_key = "lostfound_iter1_secret"

# ============================================================
# PATHS
# ============================================================

UPLOAD_FOLDER      = os.path.join("static", "uploads")
DATA_FILE          = "data.json"
EMAIL_SETTINGS_FILE = "email_settings.json"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# ============================================================
# EMAIL SETTINGS — stored in email_settings.json
# So the admin can change them from the web UI without
# editing app.py manually.
# ============================================================

def load_email_settings():
    """Read Gmail credentials from file"""
    if os.path.exists(EMAIL_SETTINGS_FILE):
        with open(EMAIL_SETTINGS_FILE, "r") as f:
            return json.load(f)
    return {
        "sender":   "",
        "password": "",
        "enabled":  False
    }


def save_email_settings(settings):
    """Write Gmail credentials to file"""
    with open(EMAIL_SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=4)


# ============================================================
# DATA FILE
# ============================================================

def load_data():
    """Read data.json — handles missing, empty, or corrupt file safely"""
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


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)


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
            {"id": "u001", "name": "Ali Hassan",  "email": "i24-0001@isb.nu.edu.pk", "password": "password123", "is_admin": False},
            {"id": "u002", "name": "Sara Khan",   "email": "i24-0002@isb.nu.edu.pk", "password": "password123", "is_admin": False},
            {"id": "u003", "name": "Ahmed Raza",  "email": "i24-0003@isb.nu.edu.pk", "password": "password123", "is_admin": False},
            {"id": "u004", "name": "Fatima Malik","email": "i24-0004@isb.nu.edu.pk", "password": "password123", "is_admin": False},
            {"id": "u005", "name": "Usman Tariq", "email": "i24-0005@isb.nu.edu.pk", "password": "password123", "is_admin": False},
            {"id": "u006", "name": "Musa Javed",  "email": "i24-0031@isb.nu.edu.pk", "password": "password123", "is_admin": False},
            {"id": "u007", "name": "Ashhad Saeed","email": "i24-0129@isb.nu.edu.pk", "password": "password123", "is_admin": False},
            {"id": "u008", "name": "Fahad Farooq","email": "i24-2071@isb.nu.edu.pk", "password": "password123", "is_admin": False},
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
    data         = load_data()
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
    current_user = get_logged_in_user()
    data         = load_data()
    items        = list(reversed(data["items"]))
    return render_template("submissions.html", current_user=current_user, items=items)


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
        scanned_roll      = request.form.get("scanned_roll", "").strip()
        scanned_email     = request.form.get("scanned_email", "").strip()
        scanned_name      = request.form.get("scanned_name", "").strip()
        uploaded_filename = request.form.get("uploaded_filename", "").strip()
        # This is set to "yes" / "no" by the confirmation UI in the browser
        send_email_choice = request.form.get("send_email_choice", "").strip()

        if not title or not category or not location or not description:
            flash("Please fill in all required fields.", "error")
            return render_template("report.html", current_user=current_user)

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
            "date_submitted":    datetime.now().strftime("%Y-%m-%d %H:%M")
        }

        data = load_data()
        data["items"].append(new_item)
        save_data(data)

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

    return render_template("report.html", current_user=current_user)


# ============================================================
# ROUTE — AJAX: scan ID card image
# ============================================================

@app.route("/scan-id-card", methods=["POST"])
def scan_id_card():
    if "image" not in request.files:
        return jsonify({"success": False, "message": "No image received"})

    file     = request.files["image"]
    filename = save_uploaded_image(file)

    if not filename:
        return jsonify({"success": False, "message": "Invalid image file"})

    image_path    = os.path.join(UPLOAD_FOLDER, filename)
    roll, student = ocr_scan_id_card(image_path)

    if student:
        return jsonify({
            "success":  True,
            "roll":     roll,
            "name":     student["name"],
            "email":    student["email"],
            "filename": filename
        })
    elif roll:
        guessed_email = roll_number_to_email(roll)
        return jsonify({
            "success":  True,
            "roll":     roll,
            "name":     "Student",
            "email":    guessed_email or "unknown",
            "filename": filename
        })
    else:
        return jsonify({
            "success":  False,
            "message":  "No roll number detected in image",
            "filename": filename
        })


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
# ADMIN ROUTES
# ============================================================

@app.route("/admin")
@require_admin
def admin_panel():
    """Admin dashboard — overview of everything"""
    current_user = get_logged_in_user()
    data         = load_data()
    settings     = load_email_settings()

    total_users = len(data["users"])
    total_items = len(data["items"])
    found_items = sum(1 for i in data["items"] if i["status"] == "found")
    lost_items  = sum(1 for i in data["items"] if i["status"] == "lost")

    return render_template("admin.html",
        current_user=current_user,
        users=data["users"],
        items=list(reversed(data["items"])),
        total_users=total_users,
        total_items=total_items,
        found_items=found_items,
        lost_items=lost_items,
        email_settings=settings
    )


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
        save_data(data)
        flash("Item updated.", "success")
        return redirect(url_for("admin_panel"))

    return render_template("admin_edit_item.html",
        current_user=current_user,
        item=target
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

        if not title or not category or not location or not description:
            flash("Please fill in all required fields.", "error")
            return render_template("admin_add_item.html", current_user=current_user)

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
            "date_submitted":    datetime.now().strftime("%Y-%m-%d %H:%M")
        }

        data = load_data()
        data["items"].append(new_item)
        save_data(data)
        flash("Item added successfully.", "success")
        return redirect(url_for("admin_panel"))

    return render_template("admin_add_item.html", current_user=current_user)


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
    print("  i24-0001@isb.nu.edu.pk")
    print("  i24-0031@isb.nu.edu.pk  (Musa)")
    print("  i24-0129@isb.nu.edu.pk  (Ashhad)")
    print("  i24-2071@isb.nu.edu.pk  (Fahad)")
    print("")
    print("  Email: configure at /admin/email-settings")
    print("=" * 55)
    print("")

    app.run(debug=True, port=5000)