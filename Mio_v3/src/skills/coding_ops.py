import os
import subprocess
import sys
import shutil
import json
import re
import ast
import time
import threading
import datetime
from src.core.finder import find_path
from src.skills.file_ops import FileSkills 
from src.skills.settings_ops import SettingsSkills # <--- NEW IMPORT

class CodingSkills:
    # --- V5 CONFIGURATION ---
    DEFAULT_EXTS = {
        '.py', '.js', '.html', '.css', '.md', '.txt', '.json', 
        '.yml', '.yaml', '.sql', '.java', '.cpp', '.c', '.h', 
        '.cs', '.go', '.rs', '.ts', '.jsx', '.tsx', '.php', 
        '.rb', '.xml', '.csv', '.sh', '.bat', '.env', '.vue'
    }
    
    SAFE_EXTENSIONS = set(DEFAULT_EXTS)
    
    DANGEROUS_PATTERNS = {
        '.py': [r"os\.system\(", r"subprocess\.run\([^)]*shell=True", r"__import__\(", r"exec\(", r"eval\(", r"shutil\.rmtree"],
        '.js': [r"eval\(", r"new\s+Function\(", r"document\.write\("],
        '.sh': [r"rm\s+-rf", r"mkfs", r"dd\s+if="]
    }

    @classmethod
    def load_safe_extensions(cls):
        config_path = os.path.expanduser("~/.mio_safe_extensions.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    data = json.load(f)
                    cls.SAFE_EXTENSIONS.update(set(data.get("extensions", [])))
            except: pass

    @staticmethod
    def _log_activity(filename, extension, size, warnings):
        log_dir = os.path.join(os.getcwd(), "data")
        os.makedirs(log_dir, exist_ok=True)
        try:
            with open(os.path.join(log_dir, "coding_audit.log"), "a", encoding="utf-8") as f:
                entry = {"timestamp": time.time(), "file": filename, "ext": extension, "size": size, "warnings": warnings}
                f.write(json.dumps(entry) + "\n")
        except: pass

    @staticmethod
    def _validate_syntax(content, extension):
        if extension == '.py':
            try:
                ast.parse(content)
                return True, ""
            except SyntaxError as e: return False, f"Python Syntax Error: {e}"
        elif extension == '.json':
            try:
                json.loads(content)
                return True, ""
            except json.JSONDecodeError as e: return False, f"JSON Syntax Error: {e}"
        return True, ""

    @staticmethod
    def _is_suspicious_content(content, extension):
        if not content: return False, ""
        patterns = CodingSkills.DANGEROUS_PATTERNS.get(extension, [])
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            for pattern in patterns:
                if re.search(pattern, line):
                    return True, f"Line {i}: Matches suspicious pattern '{pattern}'"
        return False, ""

    @staticmethod
    def _format_code(filepath, extension):
        try:
            if extension == '.py' and shutil.which("black"):
                subprocess.run(["black", filepath], capture_output=True)
                return True
            elif extension in ['.js', '.ts', '.css', '.html'] and shutil.which("prettier"):
                subprocess.run(["prettier", "--write", filepath], capture_output=True)
                return True
        except: pass
        return False

    @staticmethod
    def _find_vscode():
        locations = []
        if sys.platform == "win32":
            locations.extend([
                shutil.which("code.cmd"), shutil.which("code"),
                os.path.join(os.environ.get("ProgramFiles", ""), "Microsoft VS Code", "Code.exe"),
                os.path.join(os.environ.get("LocalAppData", ""), "Programs", "Microsoft VS Code", "Code.exe"),
            ])
        elif sys.platform == "darwin": 
            locations.extend([shutil.which("code"), "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code"])
        else: 
            locations.extend([shutil.which("code"), "/usr/bin/code", "/snap/bin/code"])
        
        for loc in locations:
            if loc and os.path.exists(loc): return loc
        return None

    @staticmethod
    def open_vscode(args=""):
        path = args.strip() or "."
        if path != ".":
            found = find_path(path, "folder") or find_path(path, "file")
            if found: path = found
            else: return f"❌ Path not found: {path}"
            
        if not FileSkills._is_safe_path(os.path.abspath(path)):
             return "❌ Security Alert: Cannot open system paths."

        try:
            vscode_path = CodingSkills._find_vscode()
            if vscode_path:
                subprocess.Popen([vscode_path, path])
                return f"✅ Opened VS Code at: {path}"
            return "❌ VS Code not found."
        except Exception as e: return f"❌ Failed to launch: {e}"

    @staticmethod
    def write_file(args):
        try:
            if "|" not in args: return "❌ Usage: filename | content"
            name, content = [x.strip() for x in args.split("|", 1)]
            CodingSkills.load_safe_extensions()
            
            # --- PATCHED LOGIC START ---
            ext = os.path.splitext(name)[1].lower()
            
            # Check Settings: Do we allow dangerous extensions?
            allow_danger = SettingsSkills.get("allow_dangerous_ext") or SettingsSkills.get("god_mode")
            
            if not allow_danger and ext not in CodingSkills.SAFE_EXTENSIONS:
                return f"❌ Security Alert: Extension '{ext}' blocked. (Enable 'allow_dangerous_ext' in Settings to bypass)."
            # --- PATCHED LOGIC END ---

            if "FORCE" not in args:
                is_valid, err_msg = CodingSkills._validate_syntax(content, ext)
                if not is_valid: return f"❌ {err_msg} (Use [WRITE_FORCE] to ignore)"

            is_bad, reason = CodingSkills._is_suspicious_content(content, ext)
            if is_bad and "FORCE" not in args:
                return f"⚠️ Safety Warning: {reason}. Use [WRITE_FORCE] to override."

            if not content.strip():
                date_str = datetime.datetime.now().strftime("%Y-%m-%d")
                headers = {'.py': f'# {name}\n# Created by Mio on {date_str}\n\n', '.js': f'// {name}\n// Created by Mio\n\n'}
                content = headers.get(ext, '')

            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            folder = os.path.join(desktop, "Mio_Files")
            os.makedirs(folder, exist_ok=True)
            filepath = os.path.join(folder, name)
            
            if os.path.exists(filepath) and "OVERWRITE" not in args and "FORCE" not in args:
                 return f"⚠️ File exists. Add '| OVERWRITE' to replace."

            with open(filepath, "w", encoding="utf-8") as f: f.write(content)
            
            formatted = CodingSkills._format_code(filepath, ext)
            fmt_msg = " (+Formatted)" if formatted else ""
            CodingSkills._log_activity(name, ext, len(content), reason if is_bad else "None")
            return f"✅ Saved file: {filepath}{fmt_msg}"
        except Exception as e: return f"❌ Write failed: {e}"

    @staticmethod
    def create_template(args):
        if "|" not in args: return "❌ Usage: [TEMPLATE] Name | Type"
        name, t_type = [x.strip() for x in args.split("|", 1)]
        t_type = t_type.lower()
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        folder = os.path.join(desktop, "Mio_Projects", name)
        
        if os.path.exists(folder): return f"❌ Project folder '{name}' already exists."
        
        try:
            os.makedirs(folder, exist_ok=True)
            templates = {
                "python": {"main.py": "print('Hello World')"},
                "web": {"index.html": "<h1>Hello</h1>", "style.css": "", "script.js": ""},
                "flask": {"app.py": "from flask import Flask\napp=Flask(__name__)\n@app.route('/')\ndef home():return 'Hi'", "requirements.txt": "flask"},
                "react": {"package.json": "{}", "src/App.js": "export default ()=><h1>Hi</h1>"}
            }
            if t_type not in templates: return f"❌ Unknown template. Available: {', '.join(templates.keys())}"
            
            for fname, content in templates[t_type].items():
                full_path = os.path.join(folder, fname)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, "w", encoding="utf-8") as f: f.write(content)
            
            if CodingSkills._find_vscode():
                threading.Thread(target=CodingSkills.open_vscode, args=(folder,)).start()
                return f"✅ Created {t_type} at {folder}\n🚀 Opening VS Code..."
            return f"✅ Created {t_type} at {folder}"
        except Exception as e: return f"❌ Template creation failed: {e}"