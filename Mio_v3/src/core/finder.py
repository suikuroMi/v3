import os
import re

def normalize_name(name, is_file=False):
    """
    Aggressively simplifies a name for comparison.
    - Case insensitive
    - Removes all non-alphanumeric characters (spaces, dashes, quotes)
    
    Examples:
    'M.I.O v2' -> 'miov2'
    'My_Document.txt' -> 'mydocument' (if is_file=True)
    """
    if not name: return ""
    clean = name.lower()
    
    # 1. Strip Extension (Only if looking for a file)
    # This allows "My Document" to find "My Document.pdf"
    if is_file:
        clean = os.path.splitext(clean)[0] 
        
    # 2. Regex Magic: Keep ONLY letters and numbers
    # Replaces anything that isn't a-z or 0-9 with empty string
    clean = re.sub(r'[^a-z0-9]', '', clean)
    
    return clean

def find_path(target, item_type="folder"):
    """
    Finds a file or folder (case-insensitive) using:
    1. Direct Path check
    2. Priority Search (Desktop, Docs, Downloads, Music, Videos)
    3. Deep Search (Scanning user directory with strict exclusions)
    """
    # Clean input target once
    target = target.strip().strip('"').strip("'")
    
    # 1. DIRECT PATH CHECK
    if os.path.exists(target):
        return target
        
    target_is_file = (item_type == "file")
    target_clean = normalize_name(target, is_file=target_is_file)
    
    user_home = os.path.expanduser("~")

    # 2. PRIORITY SEARCH (Fast & Cached)
    priority_dirs = [
        os.path.join(user_home, "Desktop"),
        os.path.join(user_home, "Documents"),
        os.path.join(user_home, "Downloads"),
        os.path.join(user_home, "Pictures"),
        os.path.join(user_home, "Music"),
        os.path.join(user_home, "Videos"),
        user_home
    ]

    for p_dir in priority_dirs:
        if not os.path.exists(p_dir): continue
        try:
            for item in os.listdir(p_dir):
                full_path = os.path.join(p_dir, item)
                
                # Type Check
                if item_type == "folder" and not os.path.isdir(full_path): continue
                if item_type == "file" and not os.path.isfile(full_path): continue
                
                # OPTIMIZATION: Calc once, compare
                if normalize_name(item, is_file=target_is_file) == target_clean:
                    return full_path
        except: continue

    # 3. DEEP SEARCH (Robust)
    print(f"🕵️‍♀️ Deep searching for '{target}' in {user_home}...")
    
    EXCLUDE_DIRS = {
        'AppData', 'Application Data', 'Cookies', 'Local Settings', 
        'NetHood', 'PrintHood', 'Recent', 'SendTo', 'Start Menu', 
        'Templates', 'Temporary Internet Files', 'Windows', 'Program Files',
        'Program Files (x86)', 'venv', '.git', '__pycache__', 'node_modules', 
        '$RECYCLE.BIN', 'ai-assistant', 'Library', 'System', 'OneDriveTemp'
    }

    for root, dirs, files in os.walk(user_home):
        # Prune excluded dirs
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith('.')]
        
        if item_type == "folder":
            for d in dirs:
                # OPTIMIZATION: Calc once
                if normalize_name(d, is_file=False) == target_clean:
                    return os.path.join(root, d)
        
        elif item_type == "file":
            for f in files:
                # OPTIMIZATION: Calc once
                if normalize_name(f, is_file=True) == target_clean:
                    return os.path.join(root, f)

    return None