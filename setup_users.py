\
from werkzeug.security import generate_password_hash
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "instance" / "order_management.db"
DB_PATH.parent.mkdir(exist_ok=True)

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
conn.execute("PRAGMA foreign_keys = ON")
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
owner_username = input("Owner username [owner]: ").strip() or "owner"
owner_password = input("Owner password: ")
staff_username = input("Staff username [staff]: ").strip() or "staff"
staff_password = input("Staff password: ")
if not owner_password or not staff_password:
    conn.close()
    raise SystemExit("Both passwords are required.")
if owner_username == staff_username:
    conn.close()
    raise SystemExit("Owner and staff usernames must be different.")
if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
    conn.close()
    raise SystemExit("Users already exist. Do not run setup again.")
conn.execute("INSERT INTO users (username,password_hash,role) VALUES (?,?,'owner')", (owner_username, generate_password_hash(owner_password)))
conn.execute("INSERT INTO users (username,password_hash,role) VALUES (?,?,'staff')", (staff_username, generate_password_hash(staff_password)))
conn.commit()
conn.close()
print("Owner and staff accounts created successfully.")
