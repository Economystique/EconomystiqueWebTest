import sqlite3
import os

def clear_sqlite_database(db_path):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Get all user tables
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name NOT LIKE 'sqlite_%';
        """)
        tables = cursor.fetchall()

        for (table_name,) in tables:
            cursor.execute(f"DELETE FROM `{table_name}`;")
            print(f"[✓] Cleared table `{table_name}` in {db_path}")

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[!] Failed to clear {db_path}: {e}")

def clear_all_databases(base_folder):
    for root, _, files in os.walk(base_folder):
        for file in files:
            if file.endswith('.db'):
                db_path = os.path.join(root, file)
                clear_sqlite_database(db_path)

# Run the function on your db directory
clear_all_databases('db')

print("\n✅ All databases emptied. Schema preserved.")
