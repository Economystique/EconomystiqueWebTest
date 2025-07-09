import sqlite3
import os

output_file = "sqlite_schema.sql"

with open(output_file, "w") as out:
    for root, _, files in os.walk("db"):
        for file in files:
            if file.endswith(".db"):
                db_path = os.path.join(root, file)
                try:
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
                    tables = cursor.fetchall()

                    out.write(f"\n-- Schema from: {db_path}\n")
                    for (sql,) in tables:
                        if sql:
                            out.write(sql + ";\n")
                    conn.close()
                    print(f"[✓] Extracted schema from {db_path}")
                except Exception as e:
                    print(f"[!] Error in {db_path}: {e}")

print("\n✅ All SQLite schemas extracted to sqlite_schema.sql")
