ORDER MANAGEMENT SYSTEM — SQLITE VERSION

MySQL is not required. SQLite is included with Python, and the app creates its database automatically at:
instance/order_management.db

SETUP
1. Extract this ZIP into a folder.
2. Open that folder in PyCharm.
3. Open the PyCharm Terminal in the project folder.
4. Install dependencies:
   pip install -r requirements.txt
5. Create owner and staff login accounts once:
   python setup_users.py
   Enter separate usernames and passwords when prompted.
6. Start the app:
   python app.py
7. Open http://127.0.0.1:5000

The SQLite database is created automatically when app.py starts. schema.sql is included for reference; you do not need MySQL Workbench or to run schema.sql manually.

OWNER: can save and view customer phone/address and search purchase history by date.
STAFF: can create orders, but cannot view customer phone/address or owner purchase history.

IMPORTANT:
- Keep instance/order_management.db safe; it contains your data and user accounts.
- Do not delete the instance folder if you want to keep your database.
- Change FLASK_SECRET_KEY before deploying publicly.
