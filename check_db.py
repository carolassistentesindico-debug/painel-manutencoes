import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "instance", "painel.db")

print("Usando banco:", DB_PATH)

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

try:
    cur.execute("ALTER TABLE sindico ADD COLUMN arquivado INTEGER DEFAULT 0")
    conn.commit()
    print("✅ Coluna 'arquivado' criada com sucesso!")
except Exception as e:
    print("⚠️ Erro:", e)

cur.execute("PRAGMA table_info(sindico)")
print("📋 Estrutura da tabela sindico:")
for col in cur.fetchall():
    print(col)

conn.close()