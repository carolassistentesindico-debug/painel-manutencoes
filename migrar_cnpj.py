import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "instance", "painel.db")

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

try:
    cur.execute("ALTER TABLE condominio ADD COLUMN cnpj TEXT")
    conn.commit()
    print("✅ Coluna cnpj adicionada em condominio")
except Exception as e:
    print("⚠️", e)

cur.execute("PRAGMA table_info(condominio)")
print("📋 Estrutura condominio:")
for col in cur.fetchall():
    print(col)

conn.close()