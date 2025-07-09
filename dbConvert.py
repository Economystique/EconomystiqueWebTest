import re

def convert_sqlite_to_mysql(sqlite_input, mysql_output):
    with open(sqlite_input, 'r') as infile:
        content = infile.read()

    # Replace " with `
    content = re.sub(r'"([^"]+)"', r'`\1`', content)

    # Replace AUTOINCREMENT
    content = content.replace("AUTOINCREMENT", "AUTO_INCREMENT")

    # Replace data types
    content = re.sub(r'\bINTEGER\b', 'INT', content)
    content = re.sub(r'\bREAL\b', 'FLOAT', content)
    content = re.sub(r'\bTEXT\b', 'VARCHAR(255)', content)
    content = re.sub(r'\bBLOB\b', 'LONGBLOB', content)
    content = re.sub(r'\bBOOLEAN\b', 'TINYINT(1)', content)

    # Remove SQLite-only keywords
    content = re.sub(r'WITHOUT ROWID', '', content)
    content = re.sub(r'COLLATE NOCASE', '', content)
    content = re.sub(r'DEFAULT \(datetime\(\)\)', 'DEFAULT CURRENT_TIMESTAMP', content)

    # Add ENGINE and CHARSET to each table
    content = re.sub(r';\s*', ' ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;\n\n', content)

    # Clean up multiple newlines
    content = re.sub(r'\n{3,}', '\n\n', content)

    # Write output
    with open(mysql_output, 'w') as outfile:
        outfile.write('-- MySQL Converted Schema\n')
        outfile.write(content)

    print(f"✅ Converted schema saved to {mysql_output}")

# Convert it
convert_sqlite_to_mysql('sqlite_schema.sql', 'mysql_schema.sql')