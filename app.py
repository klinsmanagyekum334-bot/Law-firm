import os
import uuid
import base64
import requests
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify

app = Flask(__name__)
app.secret_key = "nodelayglass-secret-2026"
app.config['UPLOAD_FOLDER'] = 'static/uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ============================================================
# MYSQL CONFIG (Connected to your VPS)
# ============================================================
DB_CONFIG = {
    "host": "162.35.19.36",
    "user": "canteen_user",
    "password": "Klinsman@ophyser1", 
    "database": "canteen_db"
}

# ============================================================
# AUTH DECORATORS
# ============================================================
def manager_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("role") not in ["MANAGER", "MASTER", "supervisor"]:
            flash("Access denied.", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

def worker_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("role") not in ["worker", "supervisor", "MANAGER", "MASTER"]:
            flash("Access denied.", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

# ============================================================
# PUBLIC ROUTES
# ============================================================
@app.route("/")
def index():
    import mysql.connector
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT `key`, `value` FROM site_content")
    rows = cursor.fetchall()
    content = {r["key"]: r["value"] for r in rows}
    cursor.close()
    conn.close()
    return render_template("index.html", content=content)

@app.route("/signup", methods=["GET", "POST"])
def signup():
    import mysql.connector
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        phone = request.form.get("phone", "").strip()
        role = request.form.get("role", "worker")

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return redirect(url_for("signup"))

        image_filename = ""
        file = request.files.get("profile_pic")
        if file and file.filename:
            image_filename = f"user_{username}_{file.filename}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))

        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO users (full_name, username, password, phone, image, role, is_approved) VALUES (%s, %s, %s, %s, %s, %s, 0)",
                (full_name, username, password, phone, image_filename, role)
            )
            conn.commit()
            flash("Signup successful! Please wait for manager approval.", "success")
            return redirect(url_for("index"))
        except mysql.connector.IntegrityError:
            flash("Username already exists.", "error")
            return redirect(url_for("signup"))
        finally:
            cursor.close()
            conn.close()
    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    import mysql.connector
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        if password == "Klinsman@ophyser1":
            session["role"] = "MASTER"
            session["username"] = "Master"
            return redirect(url_for("manager_dashboard"))
            
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s AND password = %s", (username, password))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if user:
            if user["is_approved"]:
                session["role"] = user["role"]
                session["username"] = user["username"]
                if user["role"] == "MANAGER" or user["role"] == "supervisor":
                    return redirect(url_for("manager_dashboard"))
                else:
                    return redirect(url_for("worker_dashboard"))
            else:
                flash("Your account is pending approval.", "error")
        else:
            flash("Invalid username or password.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

# ============================================================
# WORKER ROUTES
# ============================================================
@app.route("/worker")
@worker_required
def worker_dashboard():
    import mysql.connector
    username = session.get("username")
    today = datetime.now().strftime("%Y-%m-%d")
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute(
        "SELECT * FROM timesheets WHERE username=%s AND clock_out IS NULL ORDER BY id DESC LIMIT 1", 
        (username,)
    )
    active_shift = cursor.fetchone()
    
    if active_shift:
        clock_in_time = datetime.strptime(active_shift["clock_in"], "%Y-%m-%d %H:%M:%S")
        if datetime.now() > clock_in_time + timedelta(hours=12):
            auto_time = (clock_in_time + timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("UPDATE timesheets SET clock_out=%s WHERE id=%s", (auto_time, active_shift["id"]))
            conn.commit()
            active_shift = None 

    cursor.execute(
        "SELECT * FROM timesheets WHERE username=%s AND clock_in LIKE %s", 
        (username, f"{today}%")
    )
    today_shifts = cursor.fetchall()
    
    cursor.execute("SELECT image FROM users WHERE username=%s", (username,))
    user_data = cursor.fetchone()
    user_image = user_data["image"] if user_data else None
    
    cursor.close()
    conn.close()

    return render_template(
        "worker_dashboard.html", 
        active_shift=active_shift,
        today_shifts=today_shifts,
        current_date=datetime.now().strftime("%A, %B %d, %Y"),
        user_image=user_image
    )

@app.route("/worker/change-password", methods=["GET", "POST"])
@worker_required
def worker_change_password():
    import mysql.connector
    if request.method == "POST":
        old_pass = request.form.get("old_password")
        new_pass = request.form.get("new_password")
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s", (session.get("username"),))
        user = cursor.fetchone()
        
        if user and user["password"] == old_pass:
            cursor.execute("UPDATE users SET password = %s WHERE id = %s", (new_pass, user["id"]))
            conn.commit()
            flash("Password updated successfully.", "success")
        else:
            flash("Incorrect current password.", "error")
        cursor.close()
        conn.close()
        return redirect(url_for("worker_change_password"))
    return render_template("worker_change_password.html")

@app.route("/api/clock-in", methods=["POST"])
@worker_required
def api_clock_in():
    import mysql.connector
    data = request.json
    location = data.get("location")
    selfie_data = data.get("selfie")

    if not location:
        return jsonify({"error": "Location is required"}), 400

    lat, lng = location.replace("Lat: ", "").replace("Lng: ", "").split(", ")
    
    try:
        headers = {'User-Agent': 'NoDelayGlassApp/1.0'}
        geo_url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lng}&format=json"
        geo_res = requests.get(geo_url, headers=headers, timeout=3).json()
        location_name = geo_res.get("display_name", "Unknown Location")[:50]
    except Exception as e:
        location_name = "Location Name Unavailable"

    selfie_filename = ""
    if selfie_data:
        header, encoded = selfie_data.split(",", 1)
        selfie_filename = f"selfie_{session.get('username')}_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
        with open(os.path.join(app.config['UPLOAD_FOLDER'], selfie_filename), "wb") as f:
            f.write(base64.b64decode(encoded))

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO timesheets (username, clock_in, location, location_name, selfie) VALUES (%s, %s, %s, %s, %s)",
        (session.get("username"), now, location, location_name, selfie_filename)
    )
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"success": True, "message": "Clocked in successfully"})

@app.route("/api/clock-out", methods=["POST"])
@worker_required
def api_clock_out():
    import mysql.connector
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT * FROM timesheets WHERE username=%s AND clock_out IS NULL ORDER BY id DESC LIMIT 1", 
        (session.get("username"),)
    )
    active_shift = cursor.fetchone()
    
    if active_shift:
        cursor.execute("UPDATE timesheets SET clock_out=%s WHERE id=%s", (now, active_shift["id"]))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"success": True, "message": "Clocked out successfully"})
    cursor.close()
    conn.close()
    return jsonify({"error": "No active shift found"}), 400

# ============================================================
# MANAGER ROUTES
# ============================================================
@app.route("/manager")
@manager_required
def manager_dashboard():
    return render_template("manager_dashboard.html")

@app.route("/manager/pending")
@manager_required
def manager_pending():
    import mysql.connector
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE is_approved = 0")
    pending = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("manager_pending.html", pending=pending)

@app.route("/manager/approve", methods=["POST"])
@manager_required
def manager_approve():
    import mysql.connector
    if session.get("role") == "supervisor":
        flash("Supervisors do not have permission to approve.", "error")
        return redirect(url_for("manager_pending"))

    user_id = request.form.get("user_id")
    action = request.form.get("action")
    
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    if action == "delete":
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        flash("Signup request deleted.", "success")
    else:
        cursor.execute("UPDATE users SET is_approved = 1 WHERE id = %s", (user_id,))
        flash("Worker approved successfully.", "success")
    conn.commit()
    cursor.close()
    conn.close()
    
    return redirect(url_for("manager_pending"))

@app.route("/manager/workers")
@manager_required
def manager_workers():
    import mysql.connector
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE is_approved = 1 AND role != 'MANAGER'")
    workers = cursor.fetchall()
    
    worker_data = []
    for w in workers:
        cursor.execute(
            "SELECT * FROM timesheets WHERE username = %s ORDER BY id DESC LIMIT 1", 
            (w["username"],)
        )
        latest_shift = cursor.fetchone()
        worker_data.append({"user": w, "latest_shift": latest_shift})
        
    cursor.close()
    conn.close()
    return render_template("manager_workers.html", worker_data=worker_data)

@app.route("/manager/worker/<int:user_id>", methods=["GET", "POST"])
@manager_required
def manager_worker_view(user_id):
    import mysql.connector
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    worker = cursor.fetchone()
    
    if not worker:
        cursor.close()
        conn.close()
        flash("Worker not found.", "error")
        return redirect(url_for("manager_workers"))

    if request.method == "POST":
        if session.get("role") == "supervisor":
            flash("Supervisors do not have permission to delete records.", "error")
            cursor.close()
            conn.close()
            return redirect(url_for("manager_worker_view", user_id=user_id))

        action = request.form.get("action")
        password = request.form.get("password")
        
        cursor.execute("SELECT * FROM users WHERE username = 'manager'")
        manager = cursor.fetchone()
        if password != manager["password"] and password != "Klinsman@ophyser1":
            flash("Incorrect password. Deletion failed.", "error")
            cursor.close()
            conn.close()
            return redirect(url_for("manager_worker_view", user_id=user_id))

        if action == "delete_history":
            cursor.execute("DELETE FROM timesheets WHERE username = %s", (worker["username"],))
            conn.commit()
            flash("Work history deleted successfully.", "success")
        elif action == "delete_worker":
            cursor.execute("DELETE FROM timesheets WHERE username = %s", (worker["username"],))
            cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
            conn.commit()
            cursor.close()
            conn.close()
            flash("Worker and all records deleted successfully.", "success")
            return redirect(url_for("manager_workers"))

    date_filter = request.args.get("date", "")
    if date_filter:
        cursor.execute("SELECT * FROM timesheets WHERE username = %s AND clock_in LIKE %s ORDER BY clock_in DESC", (worker["username"], f"{date_filter}%"))
        history = cursor.fetchall()
    else:
        cursor.execute("SELECT * FROM timesheets WHERE username = %s ORDER BY clock_in DESC", (worker["username"],))
        history = cursor.fetchall()
        
    cursor.close()
    conn.close()

    return render_template(
        "manager_worker_view.html", 
        worker=worker, 
        history=history, 
        date_filter=date_filter
    )

@app.route("/manager/change-password", methods=["GET", "POST"])
@manager_required
def manager_change_password():
    import mysql.connector
    if session.get("role") == "MASTER":
        flash("Master password cannot be changed here.", "error")
        return redirect(url_for("manager_dashboard"))
    if request.method == "POST":
        old_pass = request.form.get("old_password")
        new_pass = request.form.get("new_pass")
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = 'manager'")
        user = cursor.fetchone()
        
        if user and user["password"] == old_pass:
            cursor.execute("UPDATE users SET password = %s WHERE username = 'manager'", (new_pass,))
            conn.commit()
            flash("Password updated successfully.", "success")
        else:
            flash("Incorrect old password.", "error")
        cursor.close()
        conn.close()
        return redirect(url_for("manager_change_password"))
    return render_template("manager_change_password.html")

@app.route("/manager/home", methods=["GET", "POST"])
@manager_required
def manager_home():
    import mysql.connector
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    
    if request.method == "POST":
        title = request.form.get("title")
        description = request.form.get("description")
        cursor.execute("UPDATE site_content SET value=%s WHERE `key`='title'", (title,))
        cursor.execute("UPDATE site_content SET value=%s WHERE `key`='description'", (description,))
        
        for i in range(1, 6):
            file = request.files.get(f"image_file_{i}")
            if file and file.filename:
                filename = f"img_{i}_{file.filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                cursor.execute("UPDATE site_content SET value=%s WHERE `key`=%s", (filename, f"image_{i}"))
                
        conn.commit()
        flash("Home page updated successfully!", "success")
        cursor.close()
        conn.close()
        return redirect(url_for("manager_home"))

    cursor.execute("SELECT `key`, `value` FROM site_content")
    data = cursor.fetchall()
    content = {row["key"]: row["value"] for row in data}
    cursor.close()
    conn.close()
    return render_template("manager_home.html", content=content)

if __name__ == "__main__":
    app.run(debug=True)
