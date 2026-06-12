import sqlite3
conn = sqlite3.connect('data/suspensionlab.db')
for row in conn.execute("SELECT name, sql FROM sqlite_master WHERE type='table'"):
    print(row[0])
    print(row[1])
    print("---")
