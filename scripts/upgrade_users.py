import sqlite3
import os

db_path = 'data/suspensionlab.db'
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE users SET tier = 'ENTERPRISE'")
    conn.commit()
    conn.close()
    print('All users upgraded to ENTERPRISE!')
else:
    print('Database not found at', db_path)
