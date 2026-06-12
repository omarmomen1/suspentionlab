import sqlite3
conn = sqlite3.connect('data/suspensionlab.db')
conn.execute("UPDATE alembic_version SET version_num='7e44398ceef5'")
conn.commit()
conn.close()
