import os
import shutil
import json
import time
import glob
from src.core.finder import find_path 

class FileSkills:
    # --- V5 CONFIGURATION ---
    ALLOWED_ROOTS = [os.path.abspath(os.path.expanduser("~"))]
    DANGEROUS_EXTENSIONS = {'.exe', '.bat', '.sh', '.py', '.js', '.vbs', '.dll', '.sys'}
    CRITICAL_PATHS = {"Downloads", "Documents", "Desktop", ".git", "node_modules", "venv", "System32"}
    
    # Caching & History
    _config_mtime = 0
    _MOVE_HISTORY = []
    HISTORY_FILE = os.path.expanduser("~/.mio_move_history.json")

    @classmethod
    def _load_config_smart(cls):
        """V5: Caches config to avoid disk reads on every call."""
        config_path = os.path.expanduser("~/.mio_allowed_paths.json")
        if not os.path.exists(config_path): return

        try:
            mtime = os.path.getmtime(config_path)
            if mtime > cls._config_mtime:
                with open(config_path, 'r') as f:
                    extra_paths = json.load(f)
                    for p in extra_paths:
                        if os.path.exists(p):
                            cls.ALLOWED_ROOTS.append(os.path.abspath(p))
                cls._config_mtime = mtime
        except: pass

    @classmethod
    def _load_history(cls):
        """V5: Loads move history from disk."""
        if os.path.exists(cls.HISTORY_FILE) and not cls._MOVE_HISTORY:
            try:
                with open(cls.HISTORY_FILE, 'r') as f:
                    cls._MOVE_HISTORY = json.load(f)
            except: pass

    @classmethod
    def _save_history(cls):
        """V5: Persists move history to disk."""
        try:
            # Keep last 50 moves
            trimmed = cls._MOVE_HISTORY[-50:]
            with open(cls.HISTORY_FILE, 'w') as f:
                json.dump(trimmed, f, indent=2)
        except: pass

    @staticmethod
    def _is_safe_path(path):
        if not path: return False
        FileSkills._load_config_smart() # Efficient check
        try:
            real_path = os.path.realpath(os.path.abspath(path))
            return any(real_path.startswith(root) for root in FileSkills.ALLOWED_ROOTS)
        except: return False

    @staticmethod
    def _get_dir_size(path):
        """V5: Calculates directory size recursively."""
        total = 0
        try:
            for dirpath, _, filenames in os.walk(path):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    total += os.path.getsize(fp)
        except: pass
        return total

    @staticmethod
    def _resolve_path(path):
        path = path.strip()
        path = os.path.expanduser(path)
        if os.path.isabs(path) or path.startswith("."): return path
        found = find_path(path, "folder")
        if found: return found
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        return os.path.join(desktop, path)

    @staticmethod
    def list_files(path):
        target = FileSkills._resolve_path(path)
        if not FileSkills._is_safe_path(target): return f"❌ Access Denied."
        if not os.path.exists(target): return f"❌ Not found: {target}"
        
        try:
            items = os.listdir(target)
            display = "\n".join(items[:20])
            if len(items) > 20: display += f"\n...and {len(items)-20} more."
            return f"📂 Files in {os.path.basename(target)}:\n{display}"
        except Exception as e: return f"❌ Error: {e}"

    @staticmethod
    def make_directory(path):
        target = FileSkills._resolve_path(path)
        if not FileSkills._is_safe_path(target): return "❌ Security Alert."
        try:
            os.makedirs(target, exist_ok=True)
            return f"✅ Created: {target}"
        except Exception as e: return f"❌ Error: {e}"

    @staticmethod
    def batch_move(args):
        """V5: [BATCH_MOVE] *.jpg | destination"""
        if "|" not in args: return "❌ Usage: pattern | destination"
        pattern_raw, dst_raw = [x.strip() for x in args.split("|", 1)]
        
        # 1. Resolve Destination
        dst = FileSkills._resolve_path(dst_raw)
        if not FileSkills._is_safe_path(dst): return "❌ Unsafe Destination."
        
        # 2. Find Files (Glob)
        # We assume pattern is relative to CWD or absolute. 
        # For safety, we force it to match inside safe roots if absolute.
        matches = glob.glob(pattern_raw)
        if not matches:
            # Try searching in Desktop by default if no path provided
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            matches = glob.glob(os.path.join(desktop, pattern_raw))
            
        safe_matches = [m for m in matches if FileSkills._is_safe_path(m)]
        
        if not safe_matches: return "⚠️ No safe files found matching pattern."
        
        # 3. Execute Batch
        moved_count = 0
        print(f"📦 Batch Moving {len(safe_matches)} files...")
        
        for src in safe_matches:
            # Re-use the single move logic safely
            res = FileSkills.move_file(f"{src} | {dst} | FORCE") 
            if "✅" in res: moved_count += 1
            print(f"   > {os.path.basename(src)}: {'OK' if '✅' in res else 'FAIL'}")
            
        return f"✅ Batch complete. Moved {moved_count}/{len(safe_matches)} files to {dst}"

    @staticmethod
    def preview_move(args):
        """V5: Shows what would happen without moving."""
        if "|" not in args: return "❌ Usage: source | destination"
        src_raw, dst_raw = [x.strip() for x in args.split("|")]
        
        src = find_path(src_raw, "file") or find_path(src_raw, "folder")
        if not src: return f"❌ Source not found."
        
        dst = FileSkills._resolve_path(dst_raw)
        
        size = os.path.getsize(src) if os.path.isfile(src) else FileSkills._get_dir_size(src)
        size_str = f"{size / (1024*1024):.2f} MB"
        
        is_safe_src = FileSkills._is_safe_path(src)
        is_safe_dst = FileSkills._is_safe_path(dst)
        
        status = "✅ SAFE" if (is_safe_src and is_safe_dst) else "❌ UNSAFE"
        
        return (f"🔮 **Preview Move:**\n"
                f"   📄 Source: {src}\n"
                f"   📂 Target: {dst}\n"
                f"   📦 Size: {size_str}\n"
                f"   🛡️ Status: {status}")

    @staticmethod
    def move_file(args):
        try:
            if "|" not in args: return "❌ Usage: source | destination"
            parts = [x.strip() for x in args.split("|")]
            src_raw, dst_raw = parts[0], parts[1]
            force_mode = "FORCE" in parts or "CONFIRM" in parts
            
            src = find_path(src_raw, "file") or find_path(src_raw, "folder")
            if not src: return f"❌ Source not found."
            
            if not FileSkills._is_safe_path(src): return "❌ Security: Source unsafe."

            # V5: Critical Path Warning
            if any(c in src for c in FileSkills.CRITICAL_PATHS) and not force_mode:
                return f"⚠️ Moving from system/critical folder ({os.path.basename(src)}). Use '| CONFIRM' to proceed."

            dst = FileSkills._resolve_path(dst_raw)
            if not FileSkills._is_safe_path(dst): return "❌ Security: Dest unsafe."

            # Smart Rename / Collision
            final_dst = dst
            if os.path.isdir(dst):
                base = os.path.basename(src)
                final_dst = os.path.join(dst, base)
                if os.path.exists(final_dst):
                    name, ext = os.path.splitext(base)
                    c = 1
                    while os.path.exists(os.path.join(dst, f"{name}_{c}{ext}")): c += 1
                    final_dst = os.path.join(dst, f"{name}_{c}{ext}")

            # Execution
            is_large = (os.path.getsize(src) > 100*1024*1024) if os.path.isfile(src) else False
            if is_large: print(f"📦 Moving large file...")
            
            shutil.move(src, final_dst)
            
            # V5: Persistent History
            FileSkills._load_history()
            FileSkills._MOVE_HISTORY.append({
                'src': src, 'dst': final_dst, 'time': time.time()
            })
            FileSkills._save_history()

            return f"✅ Moved to {final_dst}"
            
        except Exception as e: return f"❌ Move failed: {e}"

    @staticmethod
    def undo_last_move(args=""):
        FileSkills._load_history()
        if not FileSkills._MOVE_HISTORY: return "⚠️ No history found."
        
        last = FileSkills._MOVE_HISTORY.pop()
        src, dst = last['src'], last['dst']
        
        if not os.path.exists(dst): return f"❌ Cannot undo: {dst} missing."
        
        try:
            shutil.move(dst, src)
            FileSkills._save_history()
            return f"✅ Undone: Returned to {src}"
        except Exception as e:
            FileSkills._MOVE_HISTORY.append(last) # Restore if failed
            return f"❌ Undo failed: {e}"