import sqlite3
import os
import time
import csv
import json
import re
import datetime
import gzip
import threading
import shutil
import hashlib
import multiprocessing
from contextlib import contextmanager
from typing import Dict, Any

# =========================================================================
# ⚙️ INFRASTRUCTURE LAYER
# =========================================================================

class DbConfig:
    DEFAULTS = {
        'chunk_size': 10000,
        'default_timeout': 20.0,
        'max_pool_conn': 10,
        'backup_retention_days': 30,
        'backup_keep_count': 10,
        'slow_query_threshold': 2.0,
        'backup_min_free_space_mb': 500,
        'backup_timeout_min': 60
    }
    
    @classmethod
    def get(cls, key):
        env_key = f"MIO_DB_{key.upper()}"
        val = os.environ.get(env_key)
        if val is not None:
            try:
                if 'threshold' in key: return float(val)
                return int(val)
            except ValueError:
                pass
        return cls.DEFAULTS.get(key)

class GlobalConnectionPool:
    _pool = {}      
    _active = {}    
    _lock = threading.Lock()
    
    @classmethod
    def get_stats(cls) -> Dict[str, Any]:
        with cls._lock:
            stats = {}
            for path in set(list(cls._pool.keys()) + list(cls._active.keys())):
                name = os.path.basename(path)
                stats[name] = {
                    'idle': len(cls._pool.get(path, [])),
                    'active': cls._active.get(path, 0),
                    'max': DbConfig.get('max_pool_conn')
                }
            return stats

    @classmethod
    def health_check_pool(cls) -> int:
        cleaned = 0
        with cls._lock:
            for path, conns in cls._pool.items():
                alive = []
                for conn in conns:
                    try:
                        conn.execute("SELECT 1")
                        alive.append(conn)
                    except:
                        try: conn.close()
                        except: pass
                        cleaned += 1
                cls._pool[path] = alive
        return cleaned

    @classmethod
    @contextmanager
    def get_connection(cls, db_path):
        timeout = DbConfig.get('default_timeout')
        max_conn = DbConfig.get('max_pool_conn')
        key = os.path.abspath(db_path)
        
        if not cls._lock.acquire(timeout=5.0):
            raise TimeoutError("Connection Pool Lock Timeout")

        conn = None
        try:
            if key not in cls._pool: cls._pool[key] = []
            if key not in cls._active: cls._active[key] = 0
            
            if cls._pool[key]:
                conn = cls._pool[key].pop()
            
            cls._active[key] += 1
        finally:
            cls._lock.release()
        
        if not conn:
            try:
                conn = cls._create_connection(db_path, timeout)
            except Exception as e:
                with cls._lock: cls._active[key] -= 1
                raise e

        try:
            yield conn
        finally:
            with cls._lock:
                cls._active[key] -= 1
                if len(cls._pool[key]) < max_conn:
                    try:
                        conn.execute("SELECT 1")
                        cls._pool[key].append(conn)
                    except: conn.close()
                else:
                    conn.close()

    @staticmethod
    def _create_connection(db_path, timeout):
        for attempt in range(2):
            try:
                conn = sqlite3.connect(db_path, timeout=timeout)
                conn.execute("PRAGMA foreign_keys = ON")
                return conn
            except sqlite3.OperationalError as e:
                if "locked" in str(e) and attempt == 0:
                    time.sleep(0.5)
                    continue
                raise e

# =========================================================================
# 🛠️ CORE SKILLS
# =========================================================================

def _backup_worker_process(db_path, temp_path, queue):
    """Top-level function for picklability (Windows Support)."""
    try:
        src = sqlite3.connect(db_path)
        dst = sqlite3.connect(temp_path)
        
        # Page count for progress
        cursor = src.cursor()
        cursor.execute("PRAGMA page_count")
        res = cursor.fetchone()
        total_pages = res[0] if res else 0
        
        def progress(remaining, total):
            if total > 0:
                pct = int(((total - remaining) / total) * 100)
                queue.put(('progress', pct))

        with dst:
            src.backup(dst, pages=100, progress=progress)
        
        dst.close()
        src.close()
        queue.put(('done', None))
    except Exception as e:
        queue.put(('error', str(e)))

class DbSkills:
    """
    Omega Database Engine (V18).
    The Final Form.
    """

    @staticmethod
    def _log_activity(operation, db_name, details, success):
        log_dir = os.path.join(os.getcwd(), "data")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "db_audit.log")
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status = "SUCCESS" if success else "FAILED"
        entry = f"[{timestamp}] {status} | {operation} | {db_name} | {str(details)[:250]}\n"
        try:
            with open(log_file, "a", encoding="utf-8") as f: f.write(entry)
        except: pass

    # --- VALIDATORS ---
    @staticmethod
    def _validate_table_name(name):
        return bool(re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name))

    @staticmethod
    def _validate_sql_injection(query):
        patterns = [r";\s*--", r"UNION\s+SELECT", r"LOAD_FILE", r"ATTACH\s+DATABASE", r"PRAGMA\s+journal_mode"]
        for p in patterns:
            if re.search(p, query, re.IGNORECASE):
                return False, f"❌ Security Block: Suspicious pattern '{p}'."
        return True, ""

    @staticmethod
    def _add_safety_limit(query):
        q = query.upper().strip()
        if not q.startswith("SELECT") or "LIMIT" in q: return query
        if query.rstrip().endswith(";"): return query.rstrip()[:-1] + " LIMIT 1000;"
        return query + " LIMIT 1000"

    @staticmethod
    def _is_safe_query(query, allow_mod=False):
        safe, msg = DbSkills._validate_sql_injection(query)
        if not safe: return False, msg
        q = query.strip().upper()
        if q.startswith(("SELECT", "PRAGMA", "EXPLAIN")): return True, ""
        if any(c in q for c in ["DROP DATABASE", "TRUNCATE", "VACUUM"]):
            return False, "❌ Destructive operations blocked."
        if any(q.startswith(c) for c in ("CREATE", "ALTER", "INSERT", "UPDATE", "DELETE", "DROP TABLE")):
            if allow_mod: return True, ""
            return False, "⚠️ Writes blocked. Use [DB_MOD]."
        return False, "❌ Unknown SQL command."

    @staticmethod
    def _check_disk_space(db_path):
        try:
            db_size = os.path.getsize(db_path)
            temp_usage = sum(os.path.getsize(f) for f in os.listdir('.') 
                           if f.startswith(os.path.basename(db_path)) and f.endswith('.temp'))
            required_bytes = int(db_size * 2.3) + (DbConfig.get('backup_min_free_space_mb') * 1024 * 1024) + temp_usage
            usage = shutil.disk_usage(os.path.dirname(os.path.abspath(db_path)))
            return usage.free > required_bytes, required_bytes / (1024*1024)
        except: return True, 0

    # --- OPERATIONS ---

    @staticmethod
    def db_info(args="data/search_index.db") -> str:
        """[DB_INFO] path (Returns formatted string info)"""
        try:
            db_path = args.strip() if args else "data/search_index.db"
            if not os.path.exists(db_path): return f"❌ Database not found: {db_path}"
            
            size_mb = os.path.getsize(db_path) / (1024*1024)
            
            with GlobalConnectionPool.get_connection(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT count(*) FROM sqlite_master WHERE type='table'")
                table_count = cursor.fetchone()[0]
                
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [r[0] for r in cursor.fetchall()]
                
            return (f"📊 **Database Report**: {os.path.basename(db_path)}\n"
                    f"   📂 Path: {db_path}\n"
                    f"   💾 Size: {size_mb:.2f} MB\n"
                    f"   🔢 Tables: {table_count}\n"
                    f"   📝 Names: {', '.join(tables)}")
        except Exception as e: return f"❌ Error retrieving info: {e}"

    @staticmethod
    def schema_view(args="data/search_index.db") -> str:
        """[DB_SCHEMA] path (Returns schema dump)"""
        try:
            db_path = args.strip() if args else "data/search_index.db"
            if not os.path.exists(db_path): return "❌ DB Not Found"
            
            output = [f"🏗️ **Schema for {os.path.basename(db_path)}**"]
            with GlobalConnectionPool.get_connection(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name")
                for type_, name, sql in cursor.fetchall():
                    output.append(f"\n🔹 {type_.upper()}: {name}")
                    output.append(f"   ```sql\n   {sql}\n   ```")
            return "\n".join(output)
        except Exception as e: return f"❌ Error: {e}"

    @staticmethod
    def query_sqlite(args) -> Dict[str, Any]:
        """[DB_QUERY] path.db | SELECT... | [params]"""
        try:
            parts = [x.strip() for x in args.split("|")]
            if len(parts) < 2: return {'success': False, 'error': "Usage: path.db | QUERY"}
            db_path, query = parts[0], parts[1]
            params = []
            if len(parts) >= 3 and parts[2]:
                try: params = json.loads(parts[2])
                except: return {'success': False, 'error': "Invalid JSON Params"}

            if not os.path.exists(db_path): return {'success': False, 'error': "DB Not Found"}
            
            is_safe, msg = DbSkills._is_safe_query(query)
            if not is_safe: return {'success': False, 'error': msg}

            start = time.time()
            try:
                with GlobalConnectionPool.get_connection(db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(DbSkills._add_safety_limit(query), params)
                    rows = cursor.fetchall()
            
                duration = time.time() - start
                if duration > DbConfig.get('slow_query_threshold'):
                    DbSkills._log_activity("SLOW_QUERY", os.path.basename(db_path), f"{duration:.2f}s", True)

                return {'success': True, 'rows': rows, 'count': len(rows), 'duration': round(duration, 3)}

            except Exception as e: return {'success': False, 'error': str(e)}
        except Exception as e: return {'success': False, 'error': str(e)}

    @staticmethod
    def modify_schema(args) -> Dict[str, Any]:
        """[DB_MOD] path.db | SQL"""
        try:
            if "|" not in args: return {'success': False, 'error': "Usage: path.db | SQL"}
            db_path, query = [x.strip() for x in args.split("|", 1)]
            
            is_safe, msg = DbSkills._is_safe_query(query, allow_mod=True)
            if not is_safe: return {'success': False, 'error': msg}
            
            with GlobalConnectionPool.get_connection(db_path) as conn:
                try:
                    cursor = conn.cursor()
                    cursor.execute(query)
                    conn.commit()
                    rows = cursor.rowcount
                    DbSkills._log_activity("MODIFY", os.path.basename(db_path), query[:50], True)
                    return {'success': True, 'affected': rows}
                except Exception as e:
                    conn.rollback()
                    return {'success': False, 'error': str(e)}
        except Exception as e: return {'success': False, 'error': str(e)}

    @staticmethod
    def migrate_schema(args, dry_run=False) -> Dict[str, Any]:
        """[DB_MIGRATE] path.db | folder/"""
        try:
            db_path, mig_dir = [x.strip() for x in args.split("|")]
            if not os.path.exists(mig_dir): return {'success': False, 'error': "Migration dir missing"}
            
            def sort_key(f):
                match = re.match(r'^(\d+)', f)
                return int(match.group(1)) if match else float('inf')

            files = sorted([f for f in os.listdir(mig_dir) if f.endswith(".sql")], key=sort_key)
            if not files: return {'success': False, 'error': "No .sql files"}
            
            if dry_run:
                for f_name in files:
                    with open(os.path.join(mig_dir, f_name), 'r', encoding='utf-8') as f:
                        if not DbSkills._is_safe_query(f.read(), allow_mod=True)[0]:
                            return {'success': False, 'error': f"Security Check Failed: {f_name}"}
                return {'success': True, 'msg': "Dry Run Passed", 'files': len(files)}

            applied_count = 0
            with GlobalConnectionPool.get_connection(db_path) as conn:
                conn.execute("CREATE TABLE IF NOT EXISTS _migrations (id INTEGER PRIMARY KEY, name TEXT UNIQUE, hash TEXT, applied_at TIMESTAMP)")
                history = {row[0]: row[1] for row in conn.execute("SELECT name, hash FROM _migrations").fetchall()}
                
                conn.execute("BEGIN TRANSACTION")
                try:
                    for f_name in files:
                        path = os.path.join(mig_dir, f_name)
                        with open(path, 'r', encoding='utf-8') as f: sql = f.read()
                        
                        file_hash = hashlib.sha256(sql.encode()).hexdigest()
                        if f_name in history:
                            if history[f_name] != file_hash:
                                raise ValueError(f"Hash Mismatch: '{f_name}'")
                            continue
                        
                        if not DbSkills._is_safe_query(sql, allow_mod=True)[0]:
                            raise ValueError(f"Unsafe SQL: '{f_name}'")

                        conn.executescript(sql)
                        conn.execute("INSERT INTO _migrations (name, hash) VALUES (?, ?)", (f_name, file_hash))
                        applied_count += 1
                        
                    conn.commit()
                    return {'success': True, 'applied': applied_count}
                except Exception as e:
                    conn.rollback()
                    return {'success': False, 'error': str(e)}
        except Exception as e: return {'success': False, 'error': str(e)}

    @staticmethod
    def backup_db(args, progress_callback=None) -> Dict[str, Any]:
        """[DB_BACKUP] Cross-Platform Safe Backup."""
        temp_path = None
        final_path = None
        
        try:
            # Handle args being empty or a path
            db_path = args.strip() if args else "data/search_index.db"
            if not os.path.exists(db_path): return {'success': False, 'error': "DB Not Found"}
            
            has_space, required = DbSkills._check_disk_space(db_path)
            if not has_space: return {'success': False, 'error': f"Low Disk Space (Need {required:.1f}MB)"}

            timestamp = int(time.time() * 1000000)
            temp_path = f"{db_path}.{timestamp}.temp"
            final_path = f"{db_path}.{timestamp}.db.gz"
            
            # Cross-Platform Spawn
            ctx = multiprocessing.get_context('spawn')
            queue = ctx.Queue()
            p = ctx.Process(target=_backup_worker_process, args=(db_path, temp_path, queue))
            p.start()
            
            timeout = DbConfig.get('backup_timeout_min') * 60
            start = time.time()
            worker_success = False
            
            while time.time() - start < timeout:
                if not p.is_alive(): break
                try:
                    msg_type, payload = queue.get(timeout=0.5)
                    if msg_type == 'progress' and progress_callback:
                        progress_callback(payload)
                    elif msg_type == 'done':
                        worker_success = True
                        break
                    elif msg_type == 'error':
                        raise Exception(payload)
                except: pass # Queue empty or timeout, loop again
            
            if p.is_alive():
                p.terminate()
                p.join()
                raise TimeoutError("Backup Timed Out")
            
            p.join()
            if not worker_success: raise Exception("Worker failed silently")

            # Integrity & Compress
            v_conn = sqlite3.connect(temp_path)
            res = v_conn.execute("PRAGMA integrity_check").fetchone()[0]
            v_conn.close()
            if res != "ok": raise Exception("Integrity Check Failed")
                
            with open(temp_path, 'rb') as f_in:
                with gzip.open(final_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            # Verify Gzip
            with gzip.open(final_path, 'rb') as f:
                while f.read(1024*1024): pass 

            size_kb = os.path.getsize(final_path) // 1024
            return {'success': True, 'path': final_path, 'size_kb': size_kb}
            
        except Exception as e: 
            if final_path and os.path.exists(final_path): os.remove(final_path)
            return {'success': False, 'error': str(e)}
        finally:
            if temp_path and os.path.exists(temp_path):
                try: os.remove(temp_path)
                except: pass

    @staticmethod
    def backup_encrypted(args, password) -> Dict[str, Any]:
        """[DB_BACKUP_ENC] Encryption Wrapper."""
        try:
            from cryptography.fernet import Fernet
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
            import base64
            
            salt = os.urandom(16)
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100_000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
            fernet = Fernet(key)
            
            res = DbSkills.backup_db(args)
            if not res['success']: return res
            
            full_path = res['path']
            with open(full_path, 'rb') as f: data = f.read()
            
            enc_data = salt + fernet.encrypt(data)
            enc_path = full_path + ".enc"
            
            with open(enc_path, 'wb') as f: f.write(enc_data)
            os.remove(full_path)
            
            return {'success': True, 'path': enc_path, 'msg': "Encrypted"}
        except ImportError: return {'success': False, 'error': "No cryptography lib"}
        except Exception as e: return {'success': False, 'error': str(e)}

    @staticmethod
    def import_data(args) -> Dict[str, Any]:
        """[DB_IMPORT] Chunked Import."""
        try:
            db_path, table, src_file = [x.strip() for x in args.split("|")]
            if not DbSkills._validate_table_name(table): return {'success': False, 'error': "Bad Table Name"}
            if not os.path.exists(src_file): return {'success': False, 'error': "File Not Found"}
            
            chunk_size = DbConfig.get('chunk_size')
            inserted = 0
            
            with GlobalConnectionPool.get_connection(db_path) as conn:
                conn.execute("PRAGMA journal_mode = WAL")
                conn.execute("PRAGMA synchronous = NORMAL")
                try:
                    conn.execute("BEGIN TRANSACTION")
                    cursor = conn.cursor()
                    if src_file.endswith(".csv"):
                        with open(src_file, 'r', encoding='utf-8') as f:
                            reader = csv.reader(f)
                            headers = next(reader)
                            placeholders = ",".join(["?"] * len(headers))
                            sql = f"INSERT INTO {table} VALUES ({placeholders})"
                            chunk = []
                            for row in reader:
                                chunk.append(row)
                                if len(chunk) >= chunk_size:
                                    cursor.executemany(sql, chunk)
                                    inserted += len(chunk)
                                    chunk = []
                            if chunk:
                                cursor.executemany(sql, chunk)
                                inserted += len(chunk)
                    conn.commit()
                    return {'success': True, 'inserted': inserted}
                except Exception as e:
                    conn.rollback()
                    raise e
        except Exception as e: return {'success': False, 'error': str(e)}

    @staticmethod
    def export_data(args) -> Dict[str, Any]:
        """[DB_EXPORT] Streaming Export."""
        try:
            db_path, query, out_path = [x.strip() for x in args.split("|")]
            is_safe, msg = DbSkills._is_safe_query(query)
            if not is_safe: return {'success': False, 'error': msg}
            
            count = 0
            is_gz = out_path.endswith(".gz")
            opener = gzip.open if is_gz else open
            mode = 'wt' if is_gz else 'w'
            
            with GlobalConnectionPool.get_connection(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(query)
                headers = [d[0] for d in cursor.description]
                with opener(out_path, mode, encoding='utf-8', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(headers)
                    while True:
                        row = cursor.fetchone()
                        if not row: break
                        writer.writerow(row)
                        count += 1
            return {'success': True, 'rows': count, 'file': out_path}
        except Exception as e: return {'success': False, 'error': str(e)}

    @staticmethod
    def pool_stats(args) -> Dict[str, Any]:
        """[DB_POOL_STATS]"""
        try:
            return {'success': True, 'data': GlobalConnectionPool.get_stats()}
        except Exception as e: return {'success': False, 'error': str(e)}

    @staticmethod
    def pool_health(args) -> Dict[str, Any]:
        """[DB_POOL_CLEAN]"""
        try:
            cleaned = GlobalConnectionPool.health_check_pool()
            return {'success': True, 'cleaned': cleaned}
        except Exception as e: return {'success': False, 'error': str(e)}

    @staticmethod
    def manage_backups(args) -> Dict[str, Any]:
        """[DB_CLEANUP] Rotation."""
        try:
            db_path = args.strip()
            folder = os.path.dirname(db_path)
            base = os.path.basename(db_path)
            backups = []
            for f in os.listdir(folder):
                if f.startswith(base) and (f.endswith(".bak") or f.endswith(".gz") or f.endswith(".enc")):
                    full = os.path.join(folder, f)
                    backups.append((os.path.getmtime(full), full))
            backups.sort(reverse=True)
            deleted = 0
            keep_count = DbConfig.get('backup_keep_count')
            for _, path in backups[keep_count:]:
                os.remove(path)
                deleted += 1
            return {'success': True, 'deleted': deleted}
        except Exception as e: return {'success': False, 'error': str(e)}

    @staticmethod
    def health_check(args) -> Dict[str, Any]:
        """[DB_HEALTH]"""
        try:
            db_path = args.strip()
            with GlobalConnectionPool.get_connection(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA integrity_check")
                integrity = cursor.fetchone()[0]
                cursor.execute("SELECT count(*) FROM sqlite_master WHERE type='table'")
                tables = cursor.fetchone()[0]
            return {'success': True, 'integrity': integrity, 'tables': tables}
        except Exception as e: return {'success': False, 'error': str(e)}