import sqlite3

conn = sqlite3.connect('data/suspensionlab.db')

try:
    conn.execute('ALTER TABLE users RENAME COLUMN stripe_customer_id TO lemon_customer_id')
    print("Renamed lemon_customer_id")
except Exception as e:
    print(e)

try:
    conn.execute('ALTER TABLE users RENAME COLUMN stripe_subscription_id TO lemon_subscription_id')
    print("Renamed lemon_subscription_id")
except Exception as e:
    print(e)
    
try:
    conn.execute('ALTER TABLE stripe_events RENAME TO lemon_events')
    print("Renamed lemon_events")
except Exception as e:
    print(e)
    
conn.commit()
conn.close()
