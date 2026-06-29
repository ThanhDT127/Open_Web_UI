#!/usr/bin/env python3
"""
Database Migration Verification Script
=======================================
Compares SQLite and PostgreSQL data to verify migration integrity.

Usage:
    python verify_migration.py
"""

import os
import sys
import sqlite3
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

SQLITE_DB = PROJECT_ROOT / "openwebui_data" / "webui.db"

# PostgreSQL settings
PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = os.getenv("PG_PORT", "5432")
PG_USER = os.getenv("POSTGRES_USER", "openwebui_user")
PG_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
PG_DATABASE = os.getenv("POSTGRES_DB", "openwebui")


def get_pg_connection():
    """Get PostgreSQL connection"""
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
        return None
    except Exception as e:
        print(f"❌ Cannot connect to PostgreSQL: {e}")
        return None


def get_pg_tables(pg_conn):
    """Get list of tables from PostgreSQL"""
    cursor = pg_conn.cursor()
    cursor.execute("""
        SELECT table_name FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
    """)
    return [row[0] for row in cursor.fetchall()]


def get_pg_table_count(pg_conn, table_name):
    """Get row count for a PostgreSQL table"""
    cursor = pg_conn.cursor()
    try:
        cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
        return cursor.fetchone()[0]
    except:
        return 0


def get_sqlite_tables(sqlite_conn):
    """Get list of tables from SQLite"""
    cursor = sqlite_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    return [row[0] for row in cursor.fetchall()]


def get_sqlite_table_count(sqlite_conn, table_name):
    """Get row count for a SQLite table"""
    try:
        cursor = sqlite_conn.execute(f"SELECT COUNT(*) FROM {table_name}")
        return cursor.fetchone()[0]
    except:
        return 0


def verify_pgvector():
    """Verify PGVector extension is installed"""
    pg_conn = get_pg_connection()
    if not pg_conn:
        return False
    
    cursor = pg_conn.cursor()
    cursor.execute("SELECT * FROM pg_extension WHERE extname = 'vector'")
    result = cursor.fetchone()
    pg_conn.close()
    
    return result is not None


def main():
    """Main verification workflow"""
    print("=" * 60)
    print("Database Migration Verification")
    print("=" * 60)
    
    # Check PGVector
    print("\n🔍 Checking PGVector extension...")
    if verify_pgvector():
        print("  ✅ PGVector extension is installed")
    else:
        print("  ❌ PGVector extension NOT found!")
    
    # Connect to PostgreSQL
    print("\n🔍 Checking PostgreSQL...")
    pg_conn = get_pg_connection()
    if not pg_conn:
        print("  ❌ Cannot connect to PostgreSQL")
        return
    print("  ✅ PostgreSQL connection successful")
    
    # Get PostgreSQL tables
    pg_tables = get_pg_tables(pg_conn)
    print(f"\n📊 PostgreSQL Tables ({len(pg_tables)}):")
    print("-" * 40)
    
    for table in sorted(pg_tables):
        count = get_pg_table_count(pg_conn, table)
        print(f"  {table:<30} {count:>8} rows")
    
    pg_conn.close()
    
    # Compare with SQLite if exists
    if SQLITE_DB.exists():
        print(f"\n📊 SQLite Comparison:")
        print("-" * 40)
        
        sqlite_conn = sqlite3.connect(SQLITE_DB)
        sqlite_tables = get_sqlite_tables(sqlite_conn)
        
        for table in sorted(sqlite_tables):
            sqlite_count = get_sqlite_table_count(sqlite_conn, table)
            pg_count = get_pg_table_count(get_pg_connection(), table) if get_pg_connection() else 0
            
            status = "✅" if sqlite_count == pg_count else "⚠️"
            print(f"  {table:<20} SQLite: {sqlite_count:>6} | PG: {pg_count:>6} {status}")
        
        sqlite_conn.close()
    else:
        print("\n📝 SQLite database not found (fresh installation)")
    
    print("\n✅ Verification complete")


if __name__ == "__main__":
    main()
