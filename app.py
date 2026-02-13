import os
import sqlite3
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import units
import shutil

# ===============================
# CONFIGURATION FLASK
# ===============================
app = Flask(__name__)
app.secret_key = os.environ.get("HOTELDESK_SECRET", "hoteldeskpro_secret_key_2026_x9!#")

# ===============================
# DATABASE
# ===============================
DATABASE = "hotel.db"
BACKUP_DIR = "backups"

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# ===============================
# INIT DATABASE
# ===============================
def init_db():
    conn = get_db_connection()
    c = conn.cursor()

    # Table utilisateurs
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT
    )
    """)

    # Table clients
    c.execute("""
    CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        phone TEXT
    )
    """)

    # Table chambres
    c.execute("""
    CREATE TABLE IF NOT EXISTS rooms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        number TEXT UNIQUE,
        type TEXT,
        price REAL,
        status TEXT DEFAULT 'Disponible'
    )
    """)

    # Table réservations
    c.execute("""
    CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER,
        room_id INTEGER,
        checkin TEXT,
        checkout TEXT,
        total REAL,
        FOREIGN KEY(client_id) REFERENCES clients(id),
        FOREIGN KEY(room_id) REFERENCES rooms(id)
    )
    """)

    # Crée admin par défaut si inexistant
    admin = c.execute("SELECT * FROM users WHERE username='admin'").fetchone()
    if not admin:
        hashed = generate_password_hash("admin123")
        c.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                  ("admin", hashed, "admin"))

    conn.commit()
    conn.close()

    # Crée dossier backup si inexistant
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)

# ===============================
# BACKUP AUTOMATIQUE
# ===============================
def backup_db():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(BACKUP_DIR, f"hotel_backup_{timestamp}.db")
    shutil.copy2(DATABASE, backup_file)

# ===============================
# LOGIN REQUIRED DECORATOR
# ===============================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ===============================
# ROUTES UTILISATEURS
# ===============================
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            return redirect(url_for("dashboard"))
        else:
            error = "Nom d'utilisateur ou mot de passe incorrect"
    return render_template("login.html", error=error)

@app.route("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))

# ===============================
# DASHBOARD
# ===============================
@app.route("/")
@login_required
def dashboard():
    conn = get_db_connection()
    total_rooms = conn.execute("SELECT COUNT(*) FROM rooms").fetchone()[0]
    occupied_rooms = conn.execute("SELECT COUNT(*) FROM rooms WHERE status='Occupée'").fetchone()[0]
    available_rooms = total_rooms - occupied_rooms
    revenue = conn.execute("SELECT SUM(total) FROM bookings").fetchone()[0] or 0
    conn.close()
    return render_template("dashboard.html",
                           total_rooms=total_rooms,
                           occupied_rooms=occupied_rooms,
                           available_rooms=available_rooms,
                           revenue=revenue)

# ===============================
# GESTION CLIENTS
# ===============================
@app.route("/clients", methods=["GET", "POST"])
@login_required
def clients():
    conn = get_db_connection()
    if request.method == "POST":
        name = request.form["name"]
        phone = request.form["phone"]
        conn.execute("INSERT INTO clients (name, phone) VALUES (?, ?)", (name, phone))
        conn.commit()
    all_clients = conn.execute("SELECT * FROM clients").fetchall()
    conn.close()
    return render_template("clients.html", clients=all_clients)

# ===============================
# GESTION CHAMBRES
# ===============================
@app.route("/rooms", methods=["GET", "POST"])
@login_required
def rooms():
    conn = get_db_connection()
    if request.method == "POST":
        number = request.form["number"]
        room_type = request.form["type"]
        price = request.form["price"]
        conn.execute("INSERT INTO rooms (number, type, price) VALUES (?, ?, ?)",
                     (number, room_type, price))
        conn.commit()
    all_rooms = conn.execute("SELECT * FROM rooms").fetchall()
    conn.close()
    return render_template("rooms.html", rooms=all_rooms)

# ===============================
# GESTION RÉSERVATIONS
# ===============================
@app.route("/bookings", methods=["GET", "POST"])
@login_required
def bookings():
    conn = get_db_connection()
    clients = conn.execute("SELECT * FROM clients").fetchall()
    rooms = conn.execute("SELECT * FROM rooms WHERE status='Disponible'").fetchall()
    if request.method == "POST":
        client_id = request.form["client_id"]
        room_id = request.form["room_id"]
        checkin = request.form["checkin"]
        checkout = request.form["checkout"]
        price = conn.execute("SELECT price FROM rooms WHERE id=?", (room_id,)).fetchone()[0]
        total_days = (datetime.strptime(checkout, "%Y-%m-%d") - datetime.strptime(checkin, "%Y-%m-%d")).days
        total = price * total_days
        conn.execute("INSERT INTO bookings (client_id, room_id, checkin, checkout, total) VALUES (?, ?, ?, ?, ?)",
                     (client_id, room_id, checkin, checkout, total))
        conn.execute("UPDATE rooms SET status='Occupée' WHERE id=?", (room_id,))
        conn.commit()
    all_bookings = conn.execute("""
        SELECT b.id, c.name as client_name, r.number as room_number, b.checkin, b.checkout, b.total
        FROM bookings b
        JOIN clients c ON b.client_id = c.id
        JOIN rooms r ON b.room_id = r.id
    """).fetchall()
    conn.close()
    return render_template("bookings.html", bookings=all_bookings, clients=clients, rooms=rooms)

# ===============================
# GÉNÉRATION PDF FACTURE
# ===============================
@app.route("/invoice/<int:booking_id>")
@login_required
def invoice(booking_id):
    conn = get_db_connection()
    booking = conn.execute("""
        SELECT b.id, c.name as client_name, c.phone, r.number as room_number, r.type, b.checkin, b.checkout, b.total
        FROM bookings b
        JOIN clients c ON b.client_id = c.id
        JOIN rooms r ON b.room_id = r.id
        WHERE b.id=?
    """, (booking_id,)).fetchone()
    conn.close()

    if not booking:
        return "Réservation introuvable"

    filename = f"invoice_{booking_id}.pdf"
    doc = SimpleDocTemplate(filename)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("FACTURE HÔTEL", styles["Title"]))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"Client: {booking['client_name']} - {booking['phone']}", styles["Normal"]))
    elements.append(Paragraph(f"Chambre: {booking['room_number']} - {booking['type']}", styles["Normal"]))
    elements.append(Paragraph(f"Check-in: {booking['checkin']}", styles["Normal"]))
    elements.append(Paragraph(f"Check-out: {booking['checkout']}", styles["Normal"]))
    elements.append(Paragraph(f"Total: {booking['total']} €", styles["Normal"]))

    doc.build(elements)
    return send_file(filename, as_attachment=True)

# ===============================
# LANCER L'APPLICATION
# ===============================
if __name__ == "__main__":
    init_db()
    backup_db()  # Backup automatique au lancement
    app.run(debug=False)