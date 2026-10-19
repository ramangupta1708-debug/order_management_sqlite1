
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
        # Safe, additive migrations: existing orders and customers are preserved.
        order_columns = {row['name'] for row in conn.execute("PRAGMA table_info(orders)").fetchall()}
        if 'payment_method' not in order_columns:
            conn.execute("ALTER TABLE orders ADD COLUMN payment_method TEXT NOT NULL DEFAULT 'Cash'")
        if 'payment_status' not in order_columns:
            conn.execute("ALTER TABLE orders ADD COLUMN payment_status TEXT NOT NULL DEFAULT 'Paid'")
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
    payment_method = str(data.get("payment_method", "Cash"))
    payment_status = str(data.get("payment_status", "Pending"))
    status = str(data.get("status", "Pending"))

    if order_type not in ("Dine-In", "Delivery", "Packing"):
        return jsonify({"success": False, "message": "Select a valid order type."}), 400
    if not name:
        return jsonify({"success": False, "message": "Customer name is required."}), 400
    # Staff may enter customer details while creating an order; only owner APIs expose them.
    if phone and not valid_phone(phone):
        return jsonify({"success": False, "message": "Phone number must contain exactly 10 digits."}), 400
    if order_type == "Delivery" and not address:
        return jsonify({"success": False, "message": "Address is required for delivery."}), 400
    if payment_method not in ("Cash", "Online") or payment_status not in ("Pending", "Paid"):
        return jsonify({"success": False, "message": "Choose a valid payment method and status."}), 400
    if status not in ("Pending", "Confirmed", "Preparing", "Ready", "Completed", "Cancelled"):
        return jsonify({"success": False, "message": "Choose a valid order action."}), 400
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
            if not (price >= 0 and price < float('inf')):
                raise ValueError("Enter a valid item price.")
            subtotal = round(quantity * price, 2)
            total = round(total + subtotal, 2)
            cleaned.append((item_name, quantity, price, subtotal))
    except (ValueError, TypeError) as e:
        return jsonify({"success": False, "message": str(e)}), 400

    conn = get_db()
    try:
        with conn:
            customer_id = None
            if phone:
                existing = conn.execute("SELECT customer_id FROM customers WHERE phone = ?", (phone,)).fetchone()
                if existing:
                    customer_id = existing["customer_id"]
                    conn.execute("UPDATE customers SET name = ?, address = ?, updated_at = CURRENT_TIMESTAMP WHERE customer_id = ?", (name, address, customer_id))
                else:
                    cur = conn.execute("INSERT INTO customers (name, phone, address) VALUES (?, ?, ?)", (name, phone, address))
                    customer_id = cur.lastrowid
            cur = conn.execute("""INSERT INTO orders
                (customer_id, order_type, table_number, status, total_amount, payment_method, payment_status)
                VALUES (?, ?, ?, ?, ?, ?, ?)""", (customer_id, order_type, table_number, status, total, payment_method, payment_status))
            order_id = cur.lastrowid
            for item_name, quantity, price, subtotal in cleaned:
                conn.execute("INSERT INTO order_items (order_id, item_name, quantity, price, subtotal) VALUES (?, ?, ?, ?, ?)", (order_id, item_name, quantity, price, subtotal))
        return jsonify({"success": True, "message": "Order placed successfully.", "order_id": order_id, "total": total})
    except sqlite3.Error:
        app.logger.exception("Failed to create order")
        return jsonify({"success": False, "message": "Database error while saving the order."}), 500
    finally:
        conn.close()


def _orders_for_date(date, include_private=False):
    conn = get_db()
    try:
        if include_private:
            rows = conn.execute("""SELECT o.order_id, o.order_type, o.table_number, o.status,
                o.total_amount, o.created_at, o.payment_method, o.payment_status,
                c.name AS customer_name, c.phone, c.address
                FROM orders o LEFT JOIN customers c ON c.customer_id=o.customer_id
                WHERE date(o.created_at)=? ORDER BY o.order_id DESC""", (date,)).fetchall()
        else:
            rows = conn.execute("""SELECT o.order_id, o.order_type, o.table_number, o.status,
                o.total_amount, o.created_at, o.payment_method, o.payment_status,
                c.name AS customer_name
                FROM orders o LEFT JOIN customers c ON c.customer_id=o.customer_id
                WHERE date(o.created_at)=? ORDER BY o.order_id DESC""", (date,)).fetchall()
        result=[]
        for row in rows:
            order=dict(row)
            order['items']=[dict(i) for i in conn.execute(
                "SELECT item_name, quantity, price, subtotal FROM order_items WHERE order_id=? ORDER BY item_id", (order['order_id'],)
            ).fetchall()]
            result.append(order)
        return result
    finally:
        conn.close()


@app.route("/api/orders-by-date/<date>", methods=["GET"])
def orders_by_date(date):
    auth=require_login()
    if auth:
        return auth
    if not is_owner():
        return jsonify({"success":False,"message":"Only the owner can view purchase history."}),403
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}",date):
        return jsonify({"success":False,"message":"Select a valid date."}),400
    return jsonify({"success":True,"orders":_orders_for_date(date, include_private=True)})


@app.route("/api/manage-orders", methods=["GET"])
def manage_orders():
    auth = require_login()
    if auth:
        return auth
    status = request.args.get("status", "All").strip()
    payment = request.args.get("payment", "All").strip()
    search = request.args.get("search", "").strip()[:100]
    date = request.args.get("date", "").strip()
    allowed_statuses = ("All", "Pending", "Confirmed", "Preparing", "Ready", "Completed", "Cancelled")
    if status not in allowed_statuses:
        return jsonify({"success": False, "message": "Invalid status filter."}), 400
    if payment not in ("All", "Paid", "Unpaid"):
        return jsonify({"success": False, "message": "Invalid payment filter."}), 400
    if date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        return jsonify({"success": False, "message": "Select a valid date."}), 400
    conn = get_db()
    try:
        where = []
        params = []
        if status != "All":
            where.append("o.status = ?")
            params.append(status)
        if payment == "Paid":
            where.append("o.payment_status = 'Paid'")
        elif payment == "Unpaid":
            where.append("o.payment_status = 'Pending'")
        if date:
            where.append("date(o.created_at) = ?")
            params.append(date)
        if search:
            where.append("(CAST(o.order_id AS TEXT) LIKE ? OR c.name LIKE ? OR EXISTS (SELECT 1 FROM order_items si WHERE si.order_id=o.order_id AND si.item_name LIKE ?))")
            term = f"%{search}%"
            params.extend([term, term, term])
        sql = """SELECT o.order_id, o.order_type, o.table_number, o.status, o.total_amount,
                 o.created_at, o.payment_method, o.payment_status, c.name AS customer_name
                 FROM orders o LEFT JOIN customers c ON c.customer_id=o.customer_id"""
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY o.order_id DESC LIMIT 200"
        rows = conn.execute(sql, params).fetchall()
        result = []
        for row in rows:
            order = dict(row)
            order["items"] = [dict(i) for i in conn.execute(
                "SELECT item_name, quantity, price, subtotal FROM order_items WHERE order_id=? ORDER BY item_id",
                (order["order_id"],)
            ).fetchall()]
            result.append(order)
        # Deliberately omit customer phone and address for every staff/owner manage-list response.
        return jsonify({"success": True, "orders": result})
    finally:
        conn.close()


@app.route("/api/manage-orders/<date>", methods=["GET"])
def manage_orders_by_date(date):
    auth=require_login()
    if auth:
        return auth
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}",date):
        return jsonify({"success":False,"message":"Select a valid date."}),400
    # This endpoint deliberately never returns customer phone or address.
    return jsonify({"success":True,"orders":_orders_for_date(date, include_private=False)})


@app.route("/api/orders/<int:order_id>", methods=["PUT", "DELETE"])
def manage_order(order_id):
    auth=require_login()
    if auth:
        return auth
    conn=get_db()
    try:
        order=conn.execute("SELECT order_id FROM orders WHERE order_id=?",(order_id,)).fetchone()
        if not order:
            return jsonify({"success":False,"message":"Order not found."}),404
        if request.method == "DELETE":
            with conn:
                conn.execute("DELETE FROM orders WHERE order_id=?",(order_id,))
            return jsonify({"success":True,"message":"Order deleted."})
        data=request.get_json(silent=True) or {}
        allowed_status=("Pending","Confirmed","New","Preparing","Ready","Completed","Cancelled")
        status=data.get("status")
        payment_status=data.get("payment_status")
        if status is not None and status not in allowed_status:
            return jsonify({"success":False,"message":"Invalid order status."}),400
        if payment_status is not None and payment_status not in ("Pending","Paid"):
            return jsonify({"success":False,"message":"Invalid payment status."}),400
        fields=[]; values=[]
        if status is not None:
            fields.append("status=?"); values.append(status)
        if payment_status is not None:
            fields.append("payment_status=?"); values.append(payment_status)
        if not fields:
            return jsonify({"success":False,"message":"No valid changes supplied."}),400
        values.append(order_id)
        with conn:
            conn.execute("UPDATE orders SET " + ",".join(fields) + " WHERE order_id=?", values)
        return jsonify({"success":True,"message":"Order updated."})
    finally:
        conn.close()


@app.route("/api/orders/<int:order_id>/edit", methods=["PUT"])
def edit_order(order_id):
    auth=require_login()
    if auth:
        return auth
    data=request.get_json(silent=True) or {}
    order_type=data.get("order_type")
    name=str(data.get("name","")).strip()
    phone=str(data.get("phone","") or "").strip()
    address=str(data.get("address","") or "").strip()
    table_number=data.get("table_number")
    items=data.get("items",[])
    payment_method=str(data.get("payment_method","Cash"))
    if order_type not in ("Dine-In","Delivery","Packing") or not name:
        return jsonify({"success":False,"message":"Valid order type and customer name are required."}),400
    if phone and not valid_phone(phone):
        return jsonify({"success":False,"message":"Phone number must contain exactly 10 digits."}),400
    if order_type == "Delivery" and not address:
        return jsonify({"success":False,"message":"Address is required for delivery."}),400
    if payment_method not in ("Cash","Online") or not isinstance(items,list) or not items:
        return jsonify({"success":False,"message":"Check payment method and add at least one item."}),400
    if order_type == "Dine-In":
        try:
            table_number=int(table_number)
            if table_number<=0: raise ValueError
        except (TypeError,ValueError):
            return jsonify({"success":False,"message":"A valid table number is required for dine-in."}),400
    else: table_number=None
    cleaned=[]; total=0.0
    try:
        for item in items:
            item_name=str(item.get("item_name","")).strip(); quantity=int(item.get("quantity",0)); price=float(item.get("price",0))
            if not item_name or quantity<=0 or price<0 or price==float('inf'):
                raise ValueError("Check item name, quantity and price.")
            subtotal=round(quantity*price,2); total=round(total+subtotal,2)
            cleaned.append((item_name,quantity,price,subtotal))
    except (ValueError,TypeError) as e:
        return jsonify({"success":False,"message":str(e)}),400
    conn=get_db()
    try:
        with conn:
            order=conn.execute("SELECT order_id,customer_id FROM orders WHERE order_id=?",(order_id,)).fetchone()
            if not order: return jsonify({"success":False,"message":"Order not found."}),404
            customer_id=order['customer_id']
            if phone:
                existing=conn.execute("SELECT customer_id FROM customers WHERE phone=?",(phone,)).fetchone()
                if existing:
                    customer_id=existing['customer_id']
                    conn.execute("UPDATE customers SET name=?,address=?,updated_at=CURRENT_TIMESTAMP WHERE customer_id=?",(name,address,customer_id))
                elif customer_id:
                    conn.execute("UPDATE customers SET name=?,phone=?,address=?,updated_at=CURRENT_TIMESTAMP WHERE customer_id=?",(name,phone,address,customer_id))
                else:
                    customer_id=conn.execute("INSERT INTO customers(name,phone,address) VALUES(?,?,?)",(name,phone,address)).lastrowid
            conn.execute("UPDATE orders SET customer_id=?,order_type=?,table_number=?,total_amount=?,payment_method=? WHERE order_id=?",(customer_id,order_type,table_number,total,payment_method,order_id))
            conn.execute("DELETE FROM order_items WHERE order_id=?",(order_id,))
            for item in cleaned:
                conn.execute("INSERT INTO order_items(order_id,item_name,quantity,price,subtotal) VALUES(?,?,?,?,?)",(order_id,*item))
        return jsonify({"success":True,"message":"Order details saved."})
    except sqlite3.Error:
        app.logger.exception("Failed to edit order")
        return jsonify({"success":False,"message":"Database error while editing order."}),500
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
