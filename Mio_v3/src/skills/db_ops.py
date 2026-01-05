import sqlite3
import os
import time
import csv
import json
import hashlib
import datetime
from src.skills.file_ops import FileSkills

class DbSkills:
    @staticmethod
    def _log_activity(operation, db_name, details, success):
        """V5: Audit Logging for Database Operations."""
        log_dir = os.path.join(os.getcwd(), "data")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "db_audit.log")
        
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status = "SUCCESS" if success else "FAILED"
        entry = f"[{timestamp}] {status} | {operation} | {db_name} | {details}\n"
        
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(entry)
        except: pass

    @staticmethod
    def _add_safety_limit(query):
        """V5: Adds LIMIT smarty (avoids breaking 'ORDER BY' or existing limits)."""
        q_upper = query.upper().strip()
        
        # Don't touch if not a SELECT
        if not q_upper.startswith("SELECT"): return query
        
        # Don't touch if LIMIT exists
        if "LIMIT" in q_upper: return query
        
        # Append LIMIT correctly
        if query.rstrip().endswith(";"):
            return query.rstrip()[:-1] + " LIMIT 1000;"
        else:
            return query + " LIMIT 1000"

    @staticmethod
    def _is_safe_query(query, allow_mod=False):
        """V5: Validates query safety. allow_mod=True permits CREATE/INDEX."""
        q_upper = query.strip().upper()
        
        # Read-Only Allowlist
        READ_ONLY = ("SELECT", "PRAGMA", "EXPLAIN")
        if q_upper.startswith(READ_ONLY):
            return True, ""
            
        # Dangerous Blocklist (Always Blocked)
        ALWAYS_BLOCKED = ["DROP", "DELETE", "TRUNCATE", "VACUUM"]
        if any(cmd in q_upper for cmd in ALWAYS_BLOCKED):
            return False, "❌ Safety Lock: Destructive operations (DROP/DELETE) are strictly blocked."

        # Schema Mod Allowlist (Only if allow_mod=True)
        SCHEMA_MOD = ("CREATE TABLE", "CREATE INDEX", "ALTER TABLE", "INSERT", "UPDATE")
        if q_upper.startswith(SCHEMA_MOD):
            if allow_mod: return True, ""
            return False, "⚠️ Write operations blocked. Use [DB_MOD] for Schema changes."
            
        return False, "❌ Unknown or Unsafe SQL command."

    @staticmethod
    def backup_db(args):
        """V5: Uses SQLite Native Backup API."""
        db_path = args.strip()
        if not os.path.exists(db_path): return "❌ DB not found"
        if not FileSkills._is_safe_path(db_path): return "❌ Security Alert: Unsafe path."

        try:
            timestamp = int(time.time() * 1000)
            backup_path = f"{db_path}.backup_{timestamp}.db"
            
            # Read-only source connection
            source_conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            dest_conn = sqlite3.connect(backup_path)
            
            source_conn.backup(dest_conn)
            
            dest_conn.close()
            source_conn.close()
            
            size_kb = os.path.getsize(backup_path) // 1024
            DbSkills._log_activity("BACKUP", os.path.basename(db_path), f"Size: {size_kb}KB", True)
            return f"✅ Backup created: {os.path.basename(backup_path)} ({size_kb} KB)"
        except Exception as e:
            DbSkills._log_activity("BACKUP", os.path.basename(db_path), str(e), False)
            return f"❌ Backup failed: {e}"

    @staticmethod
    def query_sqlite(args):
        """V5: Safe Querying with Smart LIMIT."""
        try:
            if "|" not in args: return "❌ Usage: path/to.db | QUERY"
            db_path, query = [x.strip() for x in args.split("|", 1)]
            
            if not os.path.exists(db_path): return f"❌ Database not found"
            if not FileSkills._is_safe_path(db_path): return "❌ Security Alert: Unsafe path."

            is_safe, msg = DbSkills._is_safe_query(query, allow_mod=False)
            if not is_safe: return msg

            clean_query = DbSkills._add_safety_limit(query)
            
            start_time = time.time()
            conn = sqlite3.connect(db_path, timeout=5.0)
            cursor = conn.cursor()
            
            cursor.execute(clean_query)
            rows = cursor.fetchall()
            
            names = [desc[0] for desc in cursor.description] if cursor.description else []
            conn.close()
            
            duration = time.time() - start_time
            DbSkills._log_activity("QUERY", os.path.basename(db_path), f"Rows: {len(rows)}", True)
            
            if not rows: return f"📭 Query executed in {duration:.2f}s (0 rows)."
            
            result = f"📊 Results ({len(rows)} rows, {duration:.2f}s):\n"
            if names: result += " | ".join(names) + "\n" + "-"*30 + "\n"
            
            for row in rows[:10]: result += str(row) + "\n"
            if len(rows) > 10: result += f"...and {len(rows)-10} more."
            
            return result

        except Exception as e:
            DbSkills._log_activity("QUERY", os.path.basename(db_path) if 'db_path' in locals() else "Unknown", str(e), False)
            return f"❌ Error: {e}"

    @staticmethod
    def modify_schema(args):
        """V5: [DB_MOD] Allows CREATE/INSERT/UPDATE."""
        try:
            if "|" not in args: return "❌ Usage: path/to.db | SQL_COMMAND"
            db_path, query = [x.strip() for x in args.split("|", 1)]
            
            if not FileSkills._is_safe_path(db_path): return "❌ Unsafe path."
            
            # Allow modification commands
            is_safe, msg = DbSkills._is_safe_query(query, allow_mod=True)
            if not is_safe: return msg
            
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(query)
            conn.commit()
            
            rows_affected = cursor.rowcount
            conn.close()
            
            DbSkills._log_activity("MODIFY", os.path.basename(db_path), query[:50], True)
            return f"✅ Schema Modified. Rows affected: {rows_affected}"
            
        except Exception as e: return f"❌ Modification failed: {e}"

    @staticmethod
    def export_data(args):
        """V5: [DB_EXPORT] db_path | query | out.csv OR out.json"""
        try:
            parts = [x.strip() for x in args.split("|")]
            if len(parts) != 3: return "❌ Usage: [DB_EXPORT] db_path | query | output.(csv/json)"
            
            db_path, query, out_path = parts
            
            if not FileSkills._is_safe_path(db_path): return "❌ Unsafe DB path."
            
            out_full = FileSkills._resolve_path(out_path)
            if not FileSkills._is_safe_path(out_full): return "❌ Unsafe Output path."
            
            # Execute Query (Safe Mode)
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(query)
            
            rows = cursor.fetchall()
            headers = [d[0] for d in cursor.description]
            conn.close()
            
            if not rows: return "⚠️ No data to export."
            
            # JSON Export
            if out_full.lower().endswith(".json"):
                data = [dict(zip(headers, row)) for row in rows]
                with open(out_full, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, default=str)
                    
            # CSV Export
            else:
                with open(out_full, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(headers)
                    writer.writerows(rows)
            
            DbSkills._log_activity("EXPORT", os.path.basename(db_path), f"To: {os.path.basename(out_full)}", True)
            return f"✅ Exported {len(rows)} rows to: {out_full}"

        except Exception as e: return f"❌ Export failed: {e}"

    @staticmethod
    def db_info(args):
        """V5: Detailed DB Stats."""
        db_path = args.strip()
        if not os.path.exists(db_path): return "❌ DB not found"
        
        try:
            info = []
            size_kb = os.path.getsize(db_path) / 1024
            info.append(f"📁 File: {os.path.basename(db_path)} ({size_kb:.2f} KB)")

            conn = sqlite3.connect(db_path, timeout=2.0)
            cursor = conn.cursor()
            
            cursor.execute("SELECT count(*) FROM sqlite_master WHERE type='table'")
            info.append(f"📋 Tables: {cursor.fetchone()[0]}")
            
            cursor.execute("PRAGMA integrity_check(1)")
            status = "✅ Healthy" if cursor.fetchone()[0] == "ok" else "⚠️ Issues Found"
            info.append(f"🏥 Status: {status}")
            
            conn.close()
            return "\n".join(info)
        except Exception as e: return f"❌ Info failed: {e}"

    @staticmethod
    def schema_view(args):
        # Uses standard query but formats nicely (handled by Brain)
        return DbSkills.query_sqlite(f"{args} | SELECT type, name, sql FROM sqlite_master WHERE type='table'")