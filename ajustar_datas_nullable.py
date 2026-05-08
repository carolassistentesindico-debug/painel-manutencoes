import sqlite3
import os

DB_PATH = os.path.join("instance", "painel.db")

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute("PRAGMA foreign_keys=off;")

cursor.execute("""
CREATE TABLE manutencao_nova (
    id INTEGER PRIMARY KEY,
    condominio_id INTEGER NOT NULL,
    descricao VARCHAR(200) NOT NULL,
    data_inicio DATE NULL,
    duracao_meses INTEGER NULL,
    data_vencimento DATE NULL,
    empresa_ultima VARCHAR(120),
    telefone_empresa VARCHAR(30),
    valor_servico FLOAT,
    FOREIGN KEY(condominio_id) REFERENCES condominio (id)
);
""")

cursor.execute("""
INSERT INTO manutencao_nova (
    id,
    condominio_id,
    descricao,
    data_inicio,
    duracao_meses,
    data_vencimento,
    empresa_ultima,
    telefone_empresa,
    valor_servico
)
SELECT
    id,
    condominio_id,
    descricao,
    data_inicio,
    duracao_meses,
    data_vencimento,
    empresa_ultima,
    telefone_empresa,
    valor_servico
FROM manutencao;
""")

cursor.execute("DROP TABLE manutencao;")
cursor.execute("ALTER TABLE manutencao_nova RENAME TO manutencao;")

cursor.execute("PRAGMA foreign_keys=on;")

conn.commit()
conn.close()

print("Tabela manutencao ajustada com sucesso.")