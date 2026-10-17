
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import re
import os
from pathlib import Path

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "CHANGE_THIS_TO_A_LONG_RANDOM_SECRET")
BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
INSTANCE_DIR.mkdir(exist_ok=True)
DB_PATH = Path(os.environ.get("ORDER_DB_PATH", INSTANCE_DIR / "order_management.db"))


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    try:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('owner','staff')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS customers (
            customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT UNIQUE,
            address TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER,
            order_type TEXT NOT NULL CHECK (order_type IN ('Dine-In','Delivery','Packing')),
            table_number INTEGER,
            status TEXT NOT NULL DEFAULT 'Completed',
            total_amount REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS order_items (
            item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            price REAL NOT NULL,
            subtotal REAL NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE CASCADE
        );
        ''')
        conn.commit()
    finally:
        conn.close()


def valid_phone(phone):
    return bool(re.fullmatch(r"\d{10}", phone or ""))


def logged_in():
    return "user_id" in session


def is_owner():
    return session.get("role") == "owner"


def require_login():
    if not logged_in():
        return jsonify({"success": False, "message": "Login required."}), 401
    return None


@app.route("/")
def index():
    if not logged_in():
        return redirect(url_for("login"))
    return render_template("index.html", role=session["role"], username=session["username"])


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if logged_in():
            return redirect(url_for("index"))
        return render_template("login.html")
    data = request.get_json(silent=True) or request.form
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    if not username or not password:
        return jsonify({"success": False, "message": "Username and password are required."}), 400
    conn = get_db()
    try:
        user = conn.execute("SELECT user_id, username, password_hash, role FROM users WHERE username = ?", (username,)).fetchone()
        if not user or not check_password_hash(user["password_hash"], password):
            return jsonify({"success": False, "message": "Invalid username or password."}), 401
        session.clear()
        session["user_id"] = user["user_id"]
        session["username"] = user["username"]
        session["role"] = user["role"]
        return jsonify({"success": True, "role": user["role"], "redirect": url_for("index")})
    finally:
        conn.close()


@app.route("/logout", methods=["POST", "GET"])
def logout():
    session.clear()
    if request.method == "GET":
        return redirect(url_for("login"))
    return jsonify({"success": True, "redirect": url_for("login")})


@app.route("/api/me")
def me():
    if not logged_in():
        return jsonify({"success": False}), 401
    return jsonify({"success": True, "username": session["username"], "role": session["role"]})


@app.route("/api/customers/<phone>", methods=["GET", "PUT", "DELETE"])
def customer_by_phone(phone):
    auth = require_login()
    if auth:
        return auth
    if not is_owner():
        return jsonify({"success": False, "message": "Only the owner can access customer phone numbers and addresses."}), 403
    if not valid_phone(phone):
        return jsonify({"success": False, "message": "Phone number must contain exactly 10 digits."}), 400
    conn = get_db()
    try:
        if request.method == "GET":
            row = conn.execute("SELECT customer_id, name, phone, address, created_at, updated_at FROM customers WHERE phone = ?", (phone,)).fetchone()
            if not row:
                return jsonify({"success": False, "message": "Customer not found."}), 404
            return jsonify({"success": True, "customer": dict(row)})
        if request.method == "PUT":
            data = request.get_json(silent=True) or {}
            name = str(data.get("name", "")).strip()
            address = str(data.get("address", "")).strip()
            if not name:
                return jsonify({"success": False, "message": "Name is required."}), 400
            cur = conn.execute("UPDATE customers SET name = ?, address = ?, updated_at = CURRENT_TIMESTAMP WHERE phone = ?", (name, address, phone))
            conn.commit()
            if cur.rowcount == 0:
                return jsonify({"success": False, "message": "Customer not found."}), 404
            return jsonify({"success": True, "message": "Customer updated successfully."})
        cur = conn.execute("DELETE FROM customers WHERE phone = ?", (phone,))
        conn.commit()
        if cur.rowcount == 0:
            return jsonify({"success": False, "message": "Customer not found."}), 404
        return jsonify({"success": True, "message": "Customer deleted successfully."})
    finally:
        conn.close()


@app.route("/api/orders", methods=["POST"])
def create_order():
    auth = require_login()
    if auth:
        return auth
    data = request.get_json(silent=True) or {}
    order_type = data.get("order_type")
    name = str(data.get("name", "")).strip()
    phone = str(data.get("phone", "") or "").strip()
    address = str(data.get("address", "") or "").strip()
    table_number = data.get("table_number")
    items = data.get("items", [])
    owner = is_owner()
    if order_type not in ("Dine-In", "Delivery", "Packing"):
        return jsonify({"success": False, "message": "Select a valid order type."}), 400
    if not name:
        return jsonify({"success": False, "message": "Customer name is required."}), 400
    if owner and not valid_phone(phone):
        return jsonify({"success": False, "message": "Phone number must contain exactly 10 digits."}), 400
    if not owner:
        phone, address = "", ""
    if order_type == "Delivery" and owner and not address:
        return jsonify({"success": False, "message": "Address is required for delivery."}), 400
    if order_type == "Dine-In":
        try:
            table_number = int(table_number)
            if table_number <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"success": False, "message": "A valid table number is required for dine-in."}), 400
    else:
        table_number = None
    if not isinstance(items, list) or not items:
        return jsonify({"success": False, "message": "Add at least one item."}), 400
    cleaned, total = [], 0.0
    try:
        for item in items:
            item_name = str(item.get("item_name", "")).strip()
            quantity = int(item.get("quantity", 0))
            price = float(item.get("price", 0))
            if not item_name:
                raise ValueError("Item name is required.")
            if quantity <= 0:
                raise ValueError("Quantity must be greater than 0.")
            if price < 0:
                raise ValueError("Price cannot be negative.")
            subtotal = round(quantity * price, 2)
            total = round(total + subtotal, 2)
            cleaned.append((item_name, quantity, price, subtotal))
    except (ValueError, TypeError) as e:
        return jsonify({"success": False, "message": str(e)}), 400
    conn = get_db()
    try:
        with conn:
            customer_id = None
            if owner:
                existing = conn.execute("SELECT customer_id FROM customers WHERE phone = ?", (phone,)).fetchone()
                if existing:
                    customer_id = existing["customer_id"]
                    conn.execute("UPDATE customers SET name = ?, address = ?, updated_at = CURRENT_TIMESTAMP WHERE customer_id = ?", (name, address, customer_id))
                else:
                    cur = conn.execute("INSERT INTO customers (name, phone, address) VALUES (?, ?, ?)", (name, phone, address))
                    customer_id = cur.lastrowid
            cur = conn.execute("INSERT INTO orders (customer_id, order_type, table_number, status, total_amount) VALUES (?, ?, ?, 'Completed', ?)", (customer_id, order_type, table_number, total))
            order_id = cur.lastrowid
            for item_name, quantity, price, subtotal in cleaned:
                conn.execute("INSERT INTO order_items (order_id, item_name, quantity, price, subtotal) VALUES (?, ?, ?, ?, ?)", (order_id, item_name, quantity, price, subtotal))
        return jsonify({"success": True, "message": "Order completed successfully.", "order_id": order_id, "total": total})
    except sqlite3.Error as e:
        return jsonify({"success": False, "message": "Database error: " + str(e)}), 500
    finally:
        conn.close()


@app.route("/api/orders-by-date/<date>", methods=["GET"])
def orders_by_date(date):
    auth = require_login()
    if auth:
        return auth
    if not is_owner():
        return jsonify({"success": False, "message": "Only the owner can view purchase history."}), 403
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        return jsonify({"success": False, "message": "Select a valid date."}), 400
    conn = get_db()
    try:
        rows = conn.execute('''
            SELECT o.order_id, o.order_type, o.table_number, o.status, o.total_amount, o.created_at,
                   c.name AS customer_name, c.phone, c.address
            FROM orders o LEFT JOIN customers c ON c.customer_id = o.customer_id
            WHERE date(o.created_at) = ? ORDER BY o.order_id DESC
        ''', (date,)).fetchall()
        result = []
        for row in rows:
            order = dict(row)
            order["items"] = [dict(i) for i in conn.execute(
                "SELECT item_name, quantity, price, subtotal FROM order_items WHERE order_id = ? ORDER BY item_id", (order["order_id"],)
            ).fetchall()]
            result.append(order)
        return jsonify({"success": True, "orders": result})
    finally:
        conn.close()


@app.route("/api/setup-users", methods=["POST"])
def setup_users():
    data = request.get_json(silent=True) or {}
    setup_key = str(data.get("setup_key", ""))
    if setup_key != os.environ.get("USER_SETUP_KEY", "FIRST_SETUP_ONLY_CHANGE_ME"):
        return jsonify({"success": False, "message": "Invalid setup key."}), 403
    owner_username = str(data.get("owner_username", "owner")).strip()
    owner_password = str(data.get("owner_password", ""))
    staff_username = str(data.get("staff_username", "staff")).strip()
    staff_password = str(data.get("staff_password", ""))
    if not owner_password or not staff_password:
        return jsonify({"success": False, "message": "Both passwords are required."}), 400
    if owner_username == staff_username:
        return jsonify({"success": False, "message": "Owner and staff usernames must be different."}), 400
    conn = get_db()
    try:
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
            return jsonify({"success": False, "message": "Users already exist. Setup is disabled."}), 409
        with conn:
            conn.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'owner')", (owner_username, generate_password_hash(owner_password)))
            conn.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'staff')", (staff_username, generate_password_hash(staff_password)))
        return jsonify({"success": True, "message": "Owner and staff accounts created."})
    except sqlite3.Error as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
else:
    init_db()
