"""Fast migration using PostgreSQL COPY protocol — 10-50x faster than INSERT."""
import os, sys, csv, io, sqlite3
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2

DB_URL = os.environ.get("SUPABASE_DATABASE_URL")
if not DB_URL:
    print("Set SUPABASE_DATABASE_URL"); sys.exit(1)

SQLITE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "dental_pe_tracker.db")

# Table definitions: (table_name, columns_list)
TABLES = [
    ("practices", None),  # None = auto-detect all columns
    ("deals", None),
    ("zip_scores", None),
    ("watched_zips", None),
    ("dso_locations", None),
    ("ada_hpi_benchmarks", None),
    ("pe_sponsors", None),
    ("platforms", None),
    ("zip_overviews", None),
    ("practice_changes", None),  # Must be after practices (FK)
]

def get_columns(sqlite_cur, table_name):
    sqlite_cur.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in sqlite_cur.fetchall()]

def copy_table(sqlite_conn, pg_conn, table_name):
    sqlite_cur = sqlite_conn.cursor()
    pg_cur = pg_conn.cursor()
    
    columns = get_columns(sqlite_cur, table_name)
    col_str = ", ".join(columns)
    
    # Count rows
    sqlite_cur.execute(f"SELECT COUNT(*) FROM {table_name}")
    total = sqlite_cur.fetchone()[0]
    if total == 0:
        print(f"  [{table_name}] 0 rows — skipping")
        return 0
    
    # Truncate Postgres table
    pg_cur.execute(f"TRUNCATE TABLE {table_name} RESTART IDENTITY CASCADE")
    
    # Read all rows from SQLite
    sqlite_cur.execute(f"SELECT {col_str} FROM {table_name}")
    
    # Build CSV in memory and use COPY
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter='\t', quoting=csv.QUOTE_MINIMAL)
    
    batch_size = 50000
    rows_written = 0
    
    while True:
        rows = sqlite_cur.fetchmany(batch_size)
        if not rows:
            break
        for row in rows:
            # Convert None to \N (Postgres NULL for COPY)
            cleaned = []
            for val in row:
                if val is None:
                    cleaned.append('\\N')
                else:
                    s = str(val)
                    # Escape tabs, newlines, backslashes for COPY format
                    s = s.replace('\\', '\\\\').replace('\t', '\\t').replace('\n', '\\n').replace('\r', '\\r')
                    cleaned.append(s)
            writer.writerow(cleaned)
        
        rows_written += len(rows)
        
        # Flush buffer to COPY
        buf.seek(0)
        pg_cur.copy_expert(
            f"COPY {table_name} ({col_str}) FROM STDIN WITH (FORMAT csv, DELIMITER E'\\t', NULL '\\N', QUOTE '\"')",
            buf
        )
        pg_conn.commit()
        buf.truncate(0)
        buf.seek(0)
        
        pct = rows_written / total * 100
        print(f"  [{table_name}] {rows_written:,} / {total:,} rows ({pct:.1f}%)")
    
    # Reset sequence
    pg_cur.execute(f"SELECT setval('{table_name}_id_seq', COALESCE((SELECT MAX(id) FROM {table_name}), 0))")
    pg_conn.commit()
    
    return rows_written

def main():
    print("=" * 60)
    print("Fast Migration: SQLite → Supabase (COPY protocol)")
    print("=" * 60)
    
    # Connect SQLite
    print("Connecting to SQLite...")
    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    
    # Connect Postgres
    print("Connecting to Postgres...")
    pg_conn = psycopg2.connect(DB_URL)
    pg_conn.autocommit = False
    
    pg_cur = pg_conn.cursor()
    pg_cur.execute("SELECT version()")
    print(f"Postgres: {pg_cur.fetchone()[0][:60]}")
    
    start = datetime.now()
    total_rows = 0
    
    for table_name, _ in TABLES:
        t0 = datetime.now()
        try:
            rows = copy_table(sqlite_conn, pg_conn, table_name)
            elapsed = (datetime.now() - t0).total_seconds()
            rate = rows / elapsed if elapsed > 0 else 0
            print(f"  [{table_name}] Done: {rows:,} rows in {elapsed:.1f}s ({rate:,.0f} rows/s)")
            total_rows += rows
        except Exception as e:
            pg_conn.rollback()
            print(f"  [{table_name}] ERROR: {e}")
            raise
    
    # Initialize sync_metadata
    pg_cur = pg_conn.cursor()
    pg_cur.execute("TRUNCATE TABLE sync_metadata RESTART IDENTITY")
    now = datetime.now().isoformat()
    for table_name, _ in TABLES:
        sqlite_cur = sqlite_conn.cursor()
        sqlite_cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        cnt = sqlite_cur.fetchone()[0]
        pg_cur.execute(
            "INSERT INTO sync_metadata (table_name, last_sync_at, last_sync_value, rows_synced, sync_type, notes) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (table_name, now, str(cnt), cnt, "initial_migration", f"Migrated {cnt} rows")
        )
    pg_conn.commit()
    print(f"\nSync metadata initialized for {len(TABLES)} tables")
    
    # Verify
    print("\n" + "=" * 60)
    print("VERIFICATION — Row count comparison")
    print("=" * 60)
    all_match = True
    for table_name, _ in TABLES:
        sqlite_cur = sqlite_conn.cursor()
        sqlite_cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        sqlite_count = sqlite_cur.fetchone()[0]
        
        pg_cur = pg_conn.cursor()
        pg_cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        pg_count = pg_cur.fetchone()[0]
        
        match = "OK" if sqlite_count == pg_count else "MISMATCH"
        if sqlite_count != pg_count:
            all_match = False
        print(f"  {table_name:25s}  SQLite: {sqlite_count:>10,}  Postgres: {pg_count:>10,}  {match}")
    
    elapsed_total = (datetime.now() - start).total_seconds()
    print(f"\nTotal: {total_rows:,} rows migrated in {elapsed_total:.0f}s")
    print(f"Result: {'ALL COUNTS MATCH' if all_match else 'SOME MISMATCHES — check above'}")
    
    sqlite_conn.close()
    pg_conn.close()

if __name__ == "__main__":
    main()
