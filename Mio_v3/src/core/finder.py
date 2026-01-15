import os
import re
import time
import json
import platform
import unicodedata
import difflib
import atexit
import sqlite3
import shlex
import threading
import queue
import random
from datetime import datetime, timedelta
from functools import lru_cache, wraps
from typing import List, Dict, Optional, Callable, Iterator, Any, Union

# ============================================================================
# ⚙️ CONFIGURATION
# ============================================================================

SEARCH_CACHE_SIZE = 512
DEEP_SEARCH_TIMEOUT = 20.0 
FUZZY_THRESHOLD = 0.6
MAX_CONTENT_READ = 2 * 1024 * 1024 # 2MB
HISTORY_FILE = os.path.join("data", "search_history.json")
INDEX_DB_FILE = os.path.join("data", "search_index.db")
MAX_INDEX_ITEMS = 100000 # Increased for persistent storage

FILE_TYPES = {
    "image": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".ico", ".tiff"},
    "video": {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".m4v"},
    "audio": {".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a", ".wma"},
    "code": {".py", ".js", ".html", ".css", ".java", ".cpp", ".rs", ".go", ".ts", ".json", ".sql", ".sh", ".md", ".yml", ".toml", ".bat", ".ps1"},
    "doc": {".pdf", ".docx", ".doc", ".txt", ".rtf", ".xlsx", ".pptx", ".csv", ".log", ".msg", ".odt"}
}

# Reverse mapping for O(1) lookup during indexing
EXT_TO_CATEGORY = {ext: cat for cat, exts in FILE_TYPES.items() for ext in exts}

GLOBAL_EXCLUDES = {
    'appdata', 'application data', 'windows', 'program files', 'library',
    'system', 'node_modules', 'venv', '.git', '__pycache__', 'temp', 'tmp',
    'cache', '$recycle.bin', 'onedrivetemp', '.vscode', '.idea', 'android', 
    'build', 'dist', 'target', 'vendor', 'obj', 'bin', 'debug', 'release'
}

# ============================================================================
# 📚 THE LIBRARIAN (PERSISTENT INDEXER)
# ============================================================================

class Librarian(threading.Thread):
    """
    Background worker that maintains a PERSISTENT SQL index of user files.
    Features: WAL Mode, Category Indexing, Staleness Pruning.
    """
    def __init__(self):
        super().__init__(daemon=True, name="Mio-Librarian")
        os.makedirs("data", exist_ok=True)
        
        # Connect to disk DB
        self.conn = sqlite3.connect(INDEX_DB_FILE, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL;") # Enable Write-Ahead Logging for concurrency
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        
        self.lock = threading.Lock()
        self.indexing_queue = queue.Queue()
        self._init_db()
        self.is_ready = False

    def _init_db(self):
        with self.lock:
            # V7 Schema: Added 'category' column
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    path TEXT PRIMARY KEY,
                    name TEXT,
                    ext TEXT,
                    category TEXT,
                    size INTEGER,
                    mtime REAL,
                    lower_name TEXT
                )
            """)
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_lower ON files(lower_name)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_cat ON files(category)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_mtime ON files(mtime)")

    def index_path(self, root_path: str):
        self.indexing_queue.put(root_path)

    def run(self):
        """Main loop: Process queue -> Idle -> Prune."""
        # Startup Prune Check (1 in 5 chance to clean up dead files on boot)
        if random.random() < 0.2:
            self._prune_dead_files()

        while True:
            try:
                root = self.indexing_queue.get(timeout=2.0)
                self._scan_and_index(root)
                self.is_ready = True
            except queue.Empty:
                if not self.is_ready: self.is_ready = True
                time.sleep(1) # Idle

    def _scan_and_index(self, root_path):
        batch = []
        count = 0
        try:
            for root, dirs, files in os.walk(root_path):
                dirs[:] = [d for d in dirs if d.lower() not in GLOBAL_EXCLUDES and not d.startswith('.')]
                
                for f in files:
                    if count >= MAX_INDEX_ITEMS: return
                    
                    full_path = os.path.join(root, f)
                    try:
                        stat = os.stat(full_path)
                        ext = os.path.splitext(f)[1].lower()
                        cat = EXT_TO_CATEGORY.get(ext, "other")
                        
                        batch.append((
                            full_path, f, ext, cat, 
                            stat.st_size, stat.st_mtime, f.lower()
                        ))
                        count += 1
                    except: pass
                    
                    if len(batch) > 2000:
                        self._write_batch(batch)
                        batch = []
            
            if batch: self._write_batch(batch)
        except: pass

    def _write_batch(self, batch):
        with self.lock:
            self.conn.executemany(
                "INSERT OR REPLACE INTO files VALUES (?, ?, ?, ?, ?, ?, ?)", 
                batch
            )
            self.conn.commit()

    def _prune_dead_files(self):
        """Removes non-existent files from the index."""
        try:
            with self.lock:
                cursor = self.conn.execute("SELECT path FROM files")
                paths = [row[0] for row in cursor.fetchall()]
            
            dead_paths = [p for p in paths if not os.path.exists(p)]
            
            if dead_paths:
                with self.lock:
                    # Split into chunks for SQLite limits
                    chunk_size = 500
                    for i in range(0, len(dead_paths), chunk_size):
                        chunk = dead_paths[i:i + chunk_size]
                        placeholders = ','.join(['?'] * len(chunk))
                        self.conn.execute(f"DELETE FROM files WHERE path IN ({placeholders})", chunk)
                    self.conn.commit()
        except: pass

    def query(self, sql: str, params: tuple) -> List[Dict]:
        """Thread-safe query execution."""
        if not self.is_ready: return []
        with self.lock:
            try:
                cursor = self.conn.execute(sql, params)
                # Map tuple to dict for consistency
                return [
                    {'path': r[0], 'name': r[1], 'size': r[4], 'mtime': r[5]} 
                    for r in cursor.fetchall()
                ]
            except Exception as e:
                print(f"Librarian Query Error: {e}")
                return []

    def get_status(self):
        """Returns index stats."""
        with self.lock:
            count = self.conn.execute("SELECT count(*) FROM files").fetchone()[0]
        return f"Indexed: {count} files"

# Global Instance
librarian = Librarian()
librarian.start()

# ============================================================================
# 🧠 SEARCH MEMORY
# ============================================================================

class SearchMemory:
    def __init__(self):
        self.history: Dict[str, str] = {}
        self.load()
        atexit.register(self.save)

    def load(self):
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, 'r') as f: self.history = json.load(f)
            except: self.history = {}

    def save(self):
        try:
            os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
            with open(HISTORY_FILE, 'w') as f: json.dump(self.history, f)
        except: pass

    def learn(self, query: str, path: str):
        self.history[normalize_name(query)] = path

    def get_boost(self, query: str, path: str) -> float:
        norm_q = normalize_name(query)
        if norm_q in self.history and self.history[norm_q] == path:
            return 0.4 
        return 0.0

memory = SearchMemory()

# ============================================================================
# 🛠️ UTILITIES & PARSING
# ============================================================================

def normalize_name(name: str) -> str:
    if not name: return ""
    clean = name.lower()
    clean = unicodedata.normalize('NFKD', clean).encode('ASCII', 'ignore').decode('ASCII')
    return re.sub(r'[\s_\-\.]', '', clean)

def parse_time_filter(val: str) -> Optional[float]:
    now = time.time()
    val = val.lower()
    if val == 'today': return now - 86400
    if val == 'yesterday': return now - (86400 * 2)
    match = re.match(r'([<>])?(\d+)([d|w|m|y])', val)
    if match:
        _, num, unit = match.groups()
        seconds = int(num) * {'d': 86400, 'w': 604800, 'm': 2592000, 'y': 31536000}[unit]
        return now - seconds
    return None

def parse_query(raw_query: str) -> Dict[str, Any]:
    filters = {
        'text': [], 'ext': None, 'regex': None, 'category': None,
        'min_size': 0, 'max_size': float('inf'),
        'min_date': 0, 'max_date': float('inf'),
        'content_search': False
    }
    
    try: parts = shlex.split(raw_query)
    except: parts = raw_query.split()

    for part in parts:
        if ':' in part and not part.startswith('\\'):
            key, val = part.split(':', 1)
            key = key.lower()
            
            if key == 'ext': filters['ext'] = f".{val.lower().strip('.')}"
            elif key == 'regex': filters['regex'] = re.compile(val, re.IGNORECASE)
            elif key == 'content': filters['content_search'] = (val.lower() == 'true')
            elif key == 'type' or key == 'cat': filters['category'] = val.lower()
            elif key == 'size':
                unit = 1
                if val.lower().endswith('m'): unit = 1024**2
                elif val.lower().endswith('k'): unit = 1024
                elif val.lower().endswith('g'): unit = 1024**3
                num = float(re.sub(r'[a-zA-Z]', '', val.replace('>','').replace('<','')))
                bytes_val = num * unit
                if '>' in val: filters['min_size'] = bytes_val
                elif '<' in val: filters['max_size'] = bytes_val
            elif key in ['modified', 'created', 'accessed']:
                ts = parse_time_filter(val.replace('>','').replace('<',''))
                if ts:
                    if '>' in val or 'today' in val: filters['min_date'] = ts
                    elif '<' in val: filters['max_date'] = ts
        else:
            filters['text'].append(part)
            
    filters['target'] = " ".join(filters['text'])
    filters['target_clean'] = normalize_name(filters['target'])
    return filters

def get_priority_paths() -> List[str]:
    home = os.path.expanduser("~")
    paths = [
        os.path.join(home, "Desktop"),
        os.path.join(home, "Downloads"),
        os.path.join(home, "Documents"),
        os.path.join(home, "Pictures"),
        os.path.join(home, "Videos"),
    ]
    if platform.system() == "Windows":
        od = os.environ.get("OneDrive")
        if od and os.path.exists(od): paths.append(os.path.join(od, "Documents"))
    return [p for p in paths if os.path.exists(p)]

# Auto-Index on Load
for p in get_priority_paths():
    librarian.index_path(p)

# ============================================================================
# 🔮 SEARCH CORE
# ============================================================================

def search_generator(
    raw_query: str,
    item_type: str = "folder",
    fuzzy: bool = True,
    timeout: float = DEEP_SEARCH_TIMEOUT
) -> Iterator[Dict]:
    """
    Omnipresent Streaming Search.
    Uses Persistent Index -> Priority Disk -> Deep Disk.
    """
    start_time = time.time()
    q = parse_query(raw_query)
    target_clean = q['target_clean']
    
    # Allow pure regex/category searches even if target is empty
    if not target_clean and not q['regex'] and not q['category'] and item_type == "folder": 
        return

    seen_paths = set()
    
    def calculate_score(name, path, is_dir, mtime=0):
        score = 0.0
        name_clean = normalize_name(name)
        
        if q['regex']:
            if q['regex'].search(name): score = 1.0
        elif target_clean:
            if target_clean == name_clean: score = 1.0
            elif target_clean in name_clean: score = 0.8
            elif fuzzy:
                ratio = difflib.SequenceMatcher(None, target_clean, name_clean).ratio()
                if ratio >= FUZZY_THRESHOLD: score = ratio * 0.7
        else:
            # Pure category search (e.g., list all images)
            score = 0.8

        if score < 0.3: return 0.0

        # Bonuses
        if mtime > time.time() - 86400: score += 0.1
        score += memory.get_boost(q['target'], path)
        
        # Content Check (Last resort, expensive)
        if score < 0.6 and q['content_search'] and not is_dir:
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    if q['target'].lower() in f.read(MAX_CONTENT_READ).lower():
                        score = 0.95
            except: pass

        return min(score, 1.0)

    # --- PHASE 1: LIBRARIAN INDEX (Persistent) ---
    sql = "SELECT path, name, size, mtime FROM files WHERE 1=1"
    params = []
    
    if q['ext']: 
        sql += " AND ext = ?"
        params.append(q['ext'])
    if q['category']: # Explicit category from query
        sql += " AND category = ?"
        params.append(q['category'])
    elif item_type not in ["file", "folder"]: # Implicit category from arg
        sql += " AND category = ?"
        params.append(item_type)
        
    if q['min_size'] > 0: 
        sql += " AND size >= ?"
        params.append(q['min_size'])
    if q['min_date'] > 0:
        sql += " AND mtime >= ?"
        params.append(q['min_date'])
        
    # Execute SQL
    candidates = librarian.query(sql, tuple(params))
    
    for cand in candidates:
        is_dir = os.path.isdir(cand['path']) 
        if item_type == "folder" and not is_dir: continue
        if item_type == "file" and is_dir: continue
        
        score = calculate_score(cand['name'], cand['path'], is_dir, cand['mtime'])
        
        if score > 0.4:
            seen_paths.add(cand['path'])
            yield {'path': cand['path'], 'name': cand['name'], 'score': score}

    # --- PHASE 2: DISK FALLBACK ---
    # Only scan disk if we need more results or specific non-indexed content
    if len(seen_paths) < 10:
        priority_dirs = get_priority_paths()
        for p_dir in priority_dirs:
            try:
                with os.scandir(p_dir) as entries:
                    for entry in entries:
                        if entry.path in seen_paths: continue
                        if time.time() - start_time > timeout: return
                        
                        is_dir = entry.is_dir()
                        # Manual Filters
                        if q['min_date'] > 0 and entry.stat().st_mtime < q['min_date']: continue
                        if q['ext'] and not entry.name.endswith(q['ext']): continue
                        
                        # Category Check
                        if item_type not in ["file", "folder"] and not is_dir:
                            ext = os.path.splitext(entry.name)[1].lower()
                            if ext not in FILE_TYPES.get(item_type, set()): continue

                        score = calculate_score(entry.name, entry.path, is_dir, entry.stat().st_mtime)
                        if score > 0.4:
                            seen_paths.add(entry.path)
                            yield {'path': entry.path, 'name': entry.name, 'score': score}
            except: continue

# ============================================================================
# 🚀 PUBLIC API
# ============================================================================

def find_path_ranked(
    target: str,
    item_type: str = "folder",
    limit: int = 5,
    fuzzy: bool = True,
    timeout: float = DEEP_SEARCH_TIMEOUT,
    callback: Optional[Callable] = None
) -> List[Dict]:
    
    clean_target = target.strip().strip('"')
    if os.path.exists(clean_target):
        return [{'path': clean_target, 'score': 1.0, 'name': os.path.basename(clean_target)}]

    matches = []
    for match in search_generator(target, item_type, fuzzy, timeout):
        matches.append(match)
        if callback: callback(match)
        if len(matches) > 100: break

    matches.sort(key=lambda x: x['score'], reverse=True)
    return matches[:limit]

def find_path(target: str, item_type: str = "folder") -> Optional[str]:
    """
    Compatibility wrapper for file_ops.py.
    Calls the advanced ranker but returns just the best path string (or None).
    """
    # We ask for the top 1 result
    results = find_path_ranked(target, item_type, limit=1, timeout=2.0)
    
    # If we found something, return the 'path' string
    if results:
        return results[0]['path']
    
    return None

def batch_search(targets: List[str]) -> Dict[str, List[Dict]]:
    results = {}
    for t in targets:
        results[t] = find_path_ranked(t, limit=3, timeout=1.0) # Fast timeout for batch
    return results

def learn_selection(query: str, path: str):
    memory.learn(query, path)

def get_index_status() -> str:
    """Returns status of the background librarian."""
    return librarian.get_status()