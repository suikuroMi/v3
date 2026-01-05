import os
import subprocess
import sys
from src.core.memory import MemoryCore
from src.core.finder import find_path

mem = MemoryCore()

class DevSkills:
    @staticmethod
    def manage_snippets(args):
        # Format: "save | name | code" OR "load | name" OR "list"
        parts = [p.strip() for p in args.split("|")]
        action = parts[0].lower()
        
        if action == "save" and len(parts) >= 3:
            return mem.save_snippet(parts[1], parts[2])
        elif action == "load" and len(parts) >= 2:
            return f"📜 Snippet '{parts[1]}':\n{mem.get_snippet(parts[1])}"
        elif action == "list":
            return f"📂 Saved Snippets: {', '.join(mem.list_snippets())}"
        return "❌ Usage: [SNIPPET] save | name | code"

    @staticmethod
    def project_switcher(args):
        # Format: "ProjectName" -> Finds it, opens VS Code, updates memory
        target = find_path(args, "folder")
        if target:
            mem.add_project(target)
            # Open in VS Code
            if sys.platform == "win32":
                subprocess.Popen(f'code "{target}"', shell=True)
            else:
                subprocess.Popen(['code', target])
            return f"🚀 Switched to project: {os.path.basename(target)}"
        return f"❌ Project '{args}' not found."

    @staticmethod
    def quick_lint(args):
        # Runs a basic syntax check on a python file
        target = find_path(args, "file")
        if not target: return "❌ File not found."
        
        try:
            # Using py_compile to check syntax without running
            import py_compile
            py_compile.compile(target, doraise=True)
            return f"✅ '{os.path.basename(target)}' passed syntax check!"
        except py_compile.PyCompileError as e:
            return f"⚠️ Syntax Error:\n{e.msg}"
        except Exception as e:
            return f"❌ Error: {e}"

    @staticmethod
    def git_status(args="."):
        # Simple text-based git visualizer
        try:
            res = subprocess.check_output(["git", "status", "-s"], cwd=os.getcwd(), text=True)
            if not res: return "✨ Working tree clean."
            return f"📝 Git Status:\n{res}"
        except: return "❌ Not a git repository."