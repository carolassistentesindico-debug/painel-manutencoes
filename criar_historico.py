import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "instance", "painel.db")

print("Usando banco:", DB_PATH)
print("Banco existe?", os.path.exists(DB_PATH))

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS historico_manutencao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    manutencao_id INTEGER NOT NULL,
    data_execucao DATE NOT NULL,
    empresa VARCHAR(120),
    telefone_empresa VARCHAR(30),
    valor_servico FLOAT,
    observacao VARCHAR(300),
    FOREIGN KEY (manutencao_id) REFERENCES manutencao (id)
)
""")

conn.commit()

cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
print("Tabelas:", cur.fetchall())

cur.execute("PRAGMA table_info(historico_manutencao)")
print("Colunas de historico_manutencao:")
for col in cur.fetchall():
    print(col)

print("✅ Tabela historico_manutencao criada/verificada com sucesso!")

conn.close()