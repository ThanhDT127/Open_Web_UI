#!/usr/bin/env python3
"""
SQLite to PostgreSQL Migration Script for Open WebUI
=====================================================
Migrates data from SQLite (webui.db) to PostgreSQL container.

Usage:
    python migrate_sqlite_to_postgres.py

Requirements:
    pip install psycopg2-binary python-dotenv

Note: Run this AFTER docker-compose is started but BEFORE first login to Open WebUI
"""

import os
import sys
import sqlite3
import json
import shutil
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

# Load environment variables
load_dotenv(PROJECT_ROOT / ".env")

# Paths
SQLITE_DB = PROJECT_ROOT / "openwebui_data" / "webui.db"
BACKUP_DIR = PROJECT_ROOT / "openwebui_data" / "backups"

# PostgreSQL connection (from Docker environment)
PG_HOST = os.getenv("PG_HOST", "localhost") 
PG_PORT = os.getenv("PG_PORT", "5432")
PG_USER = os.getenv("POSTGRES_USER", "openwebui_user")
PG_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
PG_DATABASE = os.getenv("POSTGRES_DB", "openwebui")


def get_pg_connection():
    """Get PostgreSQL connection using psycopg2"""
    try:
        import psycopg2
        return psycopg2.connect(
            host=PG_HOST,
            port=PG_PORT,
            user=PG_USER,
            password=PG_PASSWORD,
            database=PG_DATABASE
        )
    except ImportError:
        print("❌ psycopg2 not installed. Run: pip install psycopg2-binary")
        sys.exit(1)


def backup_sqlite():
    """Create backup of SQLite database"""
    if not SQLITE_DB.exists():
        print(f"⚠️  SQLite database not found: {SQLITE_DB}")
        return False
    
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"webui.db.backup_{timestamp}"
    
    print(f"📦 Backing up SQLite database to {backup_path}")
    shutil.copy2(SQLITE_DB, backup_path)
    print(f"✅ Backup created: {backup_path}")
    return True


def get_sqlite_tables(sqlite_conn):
    """Get list of tables from SQLite"""
    cursor = sqlite_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    return [row[0] for row in cursor.fetchall()]


def get_table_schema(sqlite_conn, table_name):
    """Get column info for a table"""
    cursor = sqlite_conn.execute(f"PRAGMA table_info({table_name})")
    return cursor.fetchall()


def get_table_count(sqlite_conn, table_name):
    """Get row count for a table"""
    cursor = sqlite_conn.execute(f"SELECT COUNT(*) FROM {table_name}")
    return cursor.fetchone()[0]


def export_table_data(sqlite_conn, table_name):
    """Export all data from a table"""
    cursor = sqlite_conn.execute(f"SELECT * FROM {table_name}")
    columns = [description[0] for description in cursor.description]
    rows = cursor.fetchall()
    return columns, rows


def analyze_database():
    """Analyze SQLite database structure"""
    if not SQLITE_DB.exists():
        print(f"❌ SQLite database not found: {SQLITE_DB}")
        return None
    
    print(f"\n📊 Analyzing SQLite database: {SQLITE_DB}")
    
    sqlite_conn = sqlite3.connect(SQLITE_DB)
    tables = get_sqlite_tables(sqlite_conn)
    
    analysis = {}
    total_rows = 0
    
    print(f"\n{'Table':<30} {'Rows':<10} {'Columns'}")
    print("-" * 60)
    
    for table in tables:
        count = get_table_count(sqlite_conn, table)
        schema = get_table_schema(sqlite_conn, table)
        col_names = [col[1] for col in schema]
        
        analysis[table] = {
            "count": count,
            "columns": col_names
        }
        total_rows += count
        
        print(f"{table:<30} {count:<10} {len(col_names)}")
    
    print("-" * 60)
    print(f"{'Total':<30} {total_rows:<10}")
    
    sqlite_conn.close()
    return analysis


def export_to_json():
    """Export all SQLite data to JSON files for inspection"""
    if not SQLITE_DB.exists():
        print(f"❌ SQLite database not found: {SQLITE_DB}")
        return
    
    export_dir = PROJECT_ROOT / "openwebui_data" / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n📤 Exporting data to JSON: {export_dir}")
    
    sqlite_conn = sqlite3.connect(SQLITE_DB)
    sqlite_conn.row_factory = sqlite3.Row
    tables = get_sqlite_tables(sqlite_conn)
    
    for table in tables:
        cursor = sqlite_conn.execute(f"SELECT * FROM {table}")
        rows = [dict(row) for row in cursor.fetchall()]
        
        # Handle binary/blob data
        for row in rows:
            for key, value in row.items():
                if isinstance(value, bytes):
                    row[key] = f"<binary:{len(value)} bytes>"
        
        export_file = export_dir / f"{table}.json"
        with open(export_file, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"  ✅ {table}: {len(rows)} rows")
    
    sqlite_conn.close()
    print(f"\n✅ Export complete. Check {export_dir}/")


def main():
    """Main migration workflow"""
    print("=" * 60)
    print("Open WebUI SQLite to PostgreSQL Migration")
    print("=" * 60)
    
    # Step 1: Check SQLite exists
    if not SQLITE_DB.exists():
        print(f"\n⚠️  No SQLite database found at: {SQLITE_DB}")
        print("   This is normal for fresh installations.")
        print("   Open WebUI will create data directly in PostgreSQL.")
        return
    
    # Step 2: Backup
    backup_sqlite()
    
    # Step 3: Analyze
    analysis = analyze_database()
    
    if not analysis:
        return
    
    # Step 4: Export to JSON for manual inspection
    export_to_json()
    
    # Step 5: Migration note
    print("\n" + "=" * 60)
    print("📝 Migration Notes:")
    print("=" * 60)
    print("""
Open WebUI's schema may differ between SQLite and PostgreSQL.
The safest migration approach is:

1. Export important data (users, chats) from JSON files
2. Start fresh with PostgreSQL (Open WebUI will create tables)
3. Manually import critical data if needed

For automatic migration, consider using Open WebUI's built-in
database migration if available in future versions.

Exported JSON files are in: openwebui_data/export/
Backup SQLite file is in: openwebui_data/backups/
""")


if __name__ == "__main__":
    main()
