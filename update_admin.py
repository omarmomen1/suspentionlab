import sqlite3

conn = sqlite3.connect('data/suspensionlab.db')
hash_val = "$2b$12$1Js8NN5xrw/GsXoqAfx4YuDcCg5/0VdNAEwxnntWfWZS80JtuZ05m"
conn.execute("UPDATE users SET password_hash=?, plan='ENTERPRISE', tier='ENTERPRISE', onboarding_complete=1 WHERE email='admin@suspensionlab.pro'", (hash_val,))
conn.commit()
print("Admin updated.")
