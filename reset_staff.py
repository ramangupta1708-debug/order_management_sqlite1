
from getpass import getpass
from werkzeug.security import generate_password_hash
from app import app, get_db

with app.app_context():
    conn = get_db()

    try:
        staff = conn.execute(
            "SELECT username FROM users WHERE role = 'staff'"
        ).fetchall()

        if not staff:
            print("No staff account found in database.")
        else:
            print("Existing staff usernames:")
            for row in staff:
                print("-", row["username"])

            username = input("Enter the staff username from above: ").strip()
            new_password = input("Enter your new staff password: ")

            if not username or not new_password:
                print("Username and password cannot be empty.")
            else:
                result = conn.execute(
                    """UPDATE users
                       SET password_hash = ?
                       WHERE username = ? AND role = 'staff'""",
                    (generate_password_hash(new_password), username)
                )

                if result.rowcount == 1:
                    conn.commit()
                    print("Staff password reset successfully.")
                else:
                    conn.rollback()
                    print("Staff username not found. No changes made.")

    finally:
        conn.close()
