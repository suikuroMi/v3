import sqlite3
import json
import os
import time
import atexit
import queue
import shutil
from typing import Any, List, Dict, Optional, Union
from contextlib import contextmanager

MEMORY_DB = os.path.join("data", "mio_memory.db")
LEGACY_JSON = os.path.join("data", "long_term_memory.json")
BACKUP_DIR = os.path.join("data", "backups")
CURRENT_DB_VERSION = 3

class HealthyConnectionPool:
    """
    Enterprise V6 Pool:
    - Deadlock prevention (Timeouts)
    - Self-Healing (Health checks on return)
    - Monitoring (Usage stats)
    """
    def __init__(self, db_path, max_connections=5):
        self.db_path = db_path
        self.max_conn = max_connections
        self._pool = queue.Queue(maxsize=max_connections)
        self.stats = {
            "created": 0, "borrows": 0, "returns": 0, 
            "dead": 0, "timeouts": 0
        }
        
        # Warmup: Pre-fill pool to avoid cold start latency
        for _ in range(max_connections):
            self._pool.put(self._create_connection())

    def _create_connection(self):
        """Creates a fresh optimized connection."""
        # check_same_thread=False is safe because the Pool ensures exclusive access
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=20.0)
        conn.row_factory = sqlite3.Row
        
        # Performance Tuning
        conn.execute("PRAGMA journal_mode=WAL;")  # Better concurrency
        conn.execute("PRAGMA synchronous=NORMAL;") # Faster writes, safe enough with WAL
        conn.execute("PRAGMA foreign_keys=ON;")    # Data integrity
        conn.execute("PRAGMA cache_size=-64000;")  # 64MB Cache
        
        self.stats["created"] += 1
        return conn

    def get(self, timeout=5.0):
        """Get connection with timeout to prevent deadlocks."""
        try:
            conn = self._pool.get(timeout=timeout)
            self.stats["borrows"] += 1
            return conn
        except queue.Empty:
            self.stats["timeouts"] += 1
            raise TimeoutError("Database connection pool exhausted! Too many concurrent threads.")

    def put(self, conn):
        """Return connection with strict health check."""
        try:
            # Health Check: Is it still alive?
            conn.execute("SELECT 1")
            self._pool.put(conn)
            self.stats["returns"] += 1
        except Exception:
            # Connection died, replace it silently
            try: conn.close()
            except: pass
            self.stats["dead"] += 1
            try:
                self._pool.put(self._create_connection())
            except: pass # Should not happen unless DB file is locked/deleted

    def close_all(self):
        """Clean shutdown."""
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                conn.close()
            except: pass

    def get_stats(self):
        return {
            **self.stats,
            "pool_size": self._pool.qsize(),
            "in_use": self.max_conn - self._pool.qsize()
        }

class MemoryCore:
    """
    Enterprise V6: The Immortal Database.
    Features: Pooled IO, FTS5, Caching, Time-based Rotation, Maintenance Ops.
    """
    
    def __init__(self):
        os.makedirs("data", exist_ok=True)
        os.makedirs(BACKUP_DIR, exist_ok=True)
        
        self.pool = HealthyConnectionPool(MEMORY_DB, max_connections=5)
        
        # L1 Cache (RAM) - TTL based
        self._pref_cache = {} 
        self._cache_ttl = 60

        self._init_db()
        self._migrate_legacy_json()
        
        atexit.register(self.pool.close_all)

    @contextmanager
    def get_db(self):
        """Safe transaction wrapper."""
        conn = self.pool.get(timeout=5.0)
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            self.pool.put(conn)

    def _init_db(self):
        """Schema Management & Migrations."""
        with self.get_db() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER)")
            
            row = conn.execute("SELECT version FROM schema_version").fetchone()
            version = row[0] if row else 0

            if version < 1: self._migrate_to_v1(conn)
            if version < 2: self._migrate_to_v2(conn)
            if version < 3: self._migrate_to_v3(conn)

    # --- MIGRATIONS ---
    def _migrate_to_v1(self, conn):
        print("📦 DB: Applying Migration V1 (Base)...")
        conn.execute("CREATE TABLE IF NOT EXISTS user_profile (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS preferences (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS projects (path TEXT PRIMARY KEY, last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE IF NOT EXISTS snippets (name TEXT PRIMARY KEY, code TEXT, language TEXT, description TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("DELETE FROM schema_version")
        conn.execute("INSERT INTO schema_version (version) VALUES (1)")

    def _migrate_to_v2(self, conn):
        print("📦 DB: Applying Migration V2 (FTS5)...")
        try:
            conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS snippets_fts USING fts5(name, code, content='snippets', content_rowid='rowid')")
            conn.execute("INSERT INTO snippets_fts(rowid, name, code) SELECT rowid, name, code FROM snippets")
        except: print("⚠️ FTS5 not supported on this system.")
        conn.execute("UPDATE schema_version SET version = 2")

    def _migrate_to_v3(self, conn):
        print("📦 DB: Applying Migration V3 (Indexes)...")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_last_accessed ON projects(last_accessed)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_snippets_language ON snippets(language)")
        conn.execute("UPDATE schema_version SET version = 3")

    def _migrate_legacy_json(self):
        if not os.path.exists(LEGACY_JSON): return
        with self.get_db() as conn:
            if conn.execute("SELECT count(*) FROM user_profile").fetchone()[0] > 0: return 
        
        print("📦 Importing Legacy Data...")
        try:
            with open(LEGACY_JSON, 'r', encoding='utf-8') as f: data = json.load(f)
            with self.get_db() as conn:
                for k,v in data.get("user_profile", {}).items():
                    conn.execute("INSERT OR REPLACE INTO user_profile (key, value) VALUES (?, ?)", (k, json.dumps(v)))
                for k,v in data.get("preferences", {}).items():
                    conn.execute("INSERT OR REPLACE INTO preferences (key, value) VALUES (?, ?)", (k, json.dumps(v)))
                for p in data.get("project_history", []):
                    conn.execute("INSERT OR REPLACE INTO projects (path) VALUES (?)", (p,))
                for n,c in data.get("snippets", {}).items():
                    conn.execute("INSERT OR REPLACE INTO snippets (name, code, language) VALUES (?, ?, ?)", (n, c, "text"))
            os.rename(LEGACY_JSON, LEGACY_JSON + ".bak")
            print("✅ Import Complete.")
        except Exception as e: print(f"❌ Import Failed: {e}")

    # --- VALIDATION & DETECTION ---
    def _validate_input(self, text, field_name):
        if not text or not isinstance(text, str) or not text.strip():
            raise ValueError(f"Invalid {field_name}: Cannot be empty.")
        return text.strip()

    def _detect_language(self, name: str, code: str) -> str:
        """Heuristic language detection."""
        name = name.lower()
        # Extension Check
        if any(name.endswith(x) for x in ['.py', '.pyw']): return 'python'
        if any(name.endswith(x) for x in ['.js', '.ts', '.jsx']): return 'javascript'
        if any(name.endswith(x) for x in ['.java', '.kt']): return 'java'
        if any(name.endswith(x) for x in ['.rs']): return 'rust'
        if any(name.endswith(x) for x in ['.go']): return 'go'
        if any(name.endswith(x) for x in ['.html', '.css']): return 'web'
        if any(name.endswith(x) for x in ['.sql']): return 'sql'
        
        # Content Check
        if 'def ' in code and ':' in code: return 'python'
        if 'function ' in code or 'const ' in code: return 'javascript'
        if 'public class ' in code: return 'java'
        if 'SELECT ' in code and 'FROM ' in code: return 'sql'
        
        return 'text'

    # --- CORE API ---
    def update_profile(self, key: str, value: Any):
        val_str = json.dumps(value)
        with self.get_db() as conn:
            conn.execute("INSERT OR REPLACE INTO user_profile (key, value) VALUES (?, ?)", (key, val_str))

    def get_profile(self, key: str) -> Any:
        with self.get_db() as conn:
            row = conn.execute("SELECT value FROM user_profile WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def add_project(self, path: str):
        path = self._validate_input(path, "project path")
        with self.get_db() as conn:
            conn.execute("INSERT OR REPLACE INTO projects (path, last_accessed) VALUES (?, CURRENT_TIMESTAMP)", (path,))
            conn.execute("DELETE FROM projects WHERE path NOT IN (SELECT path FROM projects ORDER BY last_accessed DESC LIMIT 15)")

    def get_recent_projects(self) -> List[str]:
        with self.get_db() as conn:
            cursor = conn.execute("SELECT path FROM projects ORDER BY last_accessed DESC")
            return [row[0] for row in cursor.fetchall()]

    def get_preference(self, key: str) -> Any:
        # Check Cache
        if key in self._pref_cache:
            ts, val = self._pref_cache[key]
            if time.time() - ts < self._cache_ttl: return val

        with self.get_db() as conn:
            row = conn.execute("SELECT value FROM preferences WHERE key = ?", (key,)).fetchone()
        
        val = json.loads(row[0]) if row else True
        self._pref_cache[key] = (time.time(), val)
        return val

    def set_preference(self, key: str, value: Any):
        with self.get_db() as conn:
            conn.execute("INSERT OR REPLACE INTO preferences (key, value) VALUES (?, ?)", (key, json.dumps(value)))
        self._pref_cache.pop(key, None) # Invalidate

    def save_snippet(self, name: str, code: str):
        try:
            name = self._validate_input(name, "snippet name")
            code = self._validate_input(code, "snippet code")
            lang = self._detect_language(name, code)
            
            with self.get_db() as conn:
                conn.execute("INSERT OR REPLACE INTO snippets (name, code, language) VALUES (?, ?, ?)", (name, code, lang))
            return f"✅ Snippet '{name}' saved ({lang})."
        except ValueError as e: return f"❌ {e}"

    def get_snippet(self, name: str) -> str:
        with self.get_db() as conn:
            row = conn.execute("SELECT code FROM snippets WHERE name = ?", (name,)).fetchone()
        return row[0] if row else "❌ Snippet not found."

    def search_snippets(self, query: str) -> List[str]:
        """Hybrid Search: FTS5 > LIKE"""
        with self.get_db() as conn:
            try:
                cursor = conn.execute("SELECT name FROM snippets_fts WHERE snippets_fts MATCH ? ORDER BY rank", (query,))
                return [r['name'] for r in cursor.fetchall()]
            except:
                term = f"%{query}%"
                cursor = conn.execute("SELECT name FROM snippets WHERE name LIKE ? OR code LIKE ?", (term, term))
                return [r['name'] for r in cursor.fetchall()]

    # --- ADVANCED MAINTENANCE ---
    def optimize_database(self) -> str:
        """Runs Vacuum and Analyze to reclaim space and update optimizer stats."""
        try:
            with self.get_db() as conn:
                conn.execute("VACUUM")
                conn.execute("ANALYZE")
            return "✅ Database optimized."
        except Exception as e: return f"❌ Optimization failed: {e}"

    def validate_schema(self) -> Dict[str, Any]:
        """Checks structural integrity."""
        with self.get_db() as conn:
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            required = {"user_profile", "preferences", "projects", "snippets", "schema_version"}
            missing = required - set(tables)
            return {"valid": not missing, "missing": list(missing), "tables": tables}

    def analyze_query(self, query: str) -> List[str]:
        """Returns EXPLAIN QUERY PLAN for performance tuning."""
        with self.get_db() as conn:
            try:
                return [str(r) for r in conn.execute(f"EXPLAIN QUERY PLAN {query}").fetchall()]
            except Exception as e: return [f"Error: {e}"]

    # --- EXPORT / BACKUP ---
    def create_backup(self) -> str:
        """Safe Rotated Backup (Sorts by Modification Time)."""
        timestamp = int(time.time())
        path = os.path.join(BACKUP_DIR, f"memory_{timestamp}.bak")
        try:
            with self.get_db() as src:
                with sqlite3.connect(path) as dst: src.backup(dst)
            
            # Robust Rotation: Sort by Modification Time (Oldest first)
            backups = []
            for f in os.listdir(BACKUP_DIR):
                full_path = os.path.join(BACKUP_DIR, f)
                if os.path.isfile(full_path):
                    backups.append((os.path.getmtime(full_path), full_path))
            
            backups.sort(key=lambda x: x[0]) # Oldest at index 0
            
            while len(backups) > 5:
                _, oldest_path = backups.pop(0)
                os.remove(oldest_path)
                
            return f"✅ Backup created: {os.path.basename(path)}"
        except Exception as e: return f"❌ Backup failed: {e}"

    def export_to_sql(self, path: str):
        """Dumps full DB structure and data to SQL file."""
        with self.get_db() as conn:
            with open(path, 'w', encoding='utf-8') as f:
                for line in conn.iterdump(): f.write(f"{line}\n")