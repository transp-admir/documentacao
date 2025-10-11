import sqlite3

conn = sqlite3.connect("app.db")
cursor = conn.cursor()

cursor.execute("SELECT id, razao_social, cnpj, status FROM empresas")
rows = cursor.fetchall()

for row in rows:
    print(row)

conn.close()
