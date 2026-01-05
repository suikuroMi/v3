import subprocess
import os
import re
import json
from pathlib import Path

class GitSkills:
    # --- V4.1 CONFIGURATION ---
    # Default settings
    GIT_CONFIG = {
        "default_branch": "main",
        "default_visibility": "public",
        "desktop_path": os.path.join(os.path.expanduser("~"), "Desktop")
    }
    
    # Cache for branch names: { "path/to/repo": "main" }
    _branch_cache = {}

    # --- V4.1 ORDERED ERROR PATTERNS ---
    # List of tuples (regex, advice) ensures priority matching.
    # We check top-to-bottom.
    ERROR_PATTERNS = [
        (r"permission denied", "🔒 Permission Denied: Check your SSH keys or run 'gh auth login'."),
        (r"could not resolve host", "🌐 Network Error: Check your internet connection."),
        (r"not a git repository", "📂 Not a Repo: You need to run '[GITHUB] init | ProjectName' first."),
        (r"already exists", "⚠️ Exists: A repository with this name already exists locally."),
        (r"no upstream", "☁️ No Upstream: The branch isn't linked to GitHub yet."),
        (r"conflict", "⚔️ Merge Conflict: Automatic push failed. Resolve conflicts manually."),
        (r"authenticat", "🔑 Auth Failed: Please run 'gh auth login' in your terminal."),
        (r"nothing to commit", "✨ Working tree clean (Nothing to commit).")
    ]

    @classmethod
    def load_user_config(cls):
        """Loads custom config from ~/.mio_git_config.json if it exists."""
        config_path = os.path.expanduser("~/.mio_git_config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    user_config = json.load(f)
                    cls.GIT_CONFIG.update(user_config)
            except Exception:
                pass # Fail silently and use defaults

    @staticmethod
    def clear_cache():
        """Invalidates the branch cache."""
        GitSkills._branch_cache.clear()

    @staticmethod
    def _analyze_error(error_msg):
        """Scans raw git output using ordered priority."""
        for pattern, advice in GitSkills.ERROR_PATTERNS:
            if re.search(pattern, error_msg, re.IGNORECASE):
                # Return sanitized advice (hiding raw system paths/tokens if possible)
                return f"{advice}"
        
        # Fallback for unknown errors
        return f"❌ Git Error: {error_msg.strip()}"

    @staticmethod
    def git_manager(args):
        """
        Unified Git Command Processor (V4.1 Production)
        """
        # Ensure config is loaded
        GitSkills.load_user_config()
        
        parts = [x.strip() for x in args.split("|")]
        if not parts: return "❌ No command specified"
            
        action = parts[0].lower()
        
        if action == "push":
            return GitSkills._handle_push(parts)
        elif action == "init":
            return GitSkills._handle_init(parts)
        elif action == "status":
            return GitSkills._handle_status()
        elif action == "clone":
            return GitSkills._handle_clone(parts)
        else:
            return f"❌ Unknown Git command: {action}"

    @staticmethod
    def _run_safe(cmd_list, cwd=None):
        """Executes commands securely (No shell=True)."""
        try:
            result = subprocess.run(
                cmd_list, 
                cwd=cwd, 
                capture_output=True, 
                text=True, 
                check=True
            )
            return True, result.stdout.strip()
        except subprocess.CalledProcessError as e:
            return False, e.stderr.strip()
        except Exception as e:
            return False, str(e)

    @staticmethod
    def _detect_branch(cwd=None, force_refresh=False):
        """Finds current branch name with caching."""
        cwd_str = str(cwd) if cwd else os.getcwd()
        
        if not force_refresh and cwd_str in GitSkills._branch_cache:
            return GitSkills._branch_cache[cwd_str]

        success, output = GitSkills._run_safe(["git", "branch", "--show-current"], cwd)
        branch = output if success and output else GitSkills.GIT_CONFIG["default_branch"]
        
        GitSkills._branch_cache[cwd_str] = branch
        return branch

    @staticmethod
    def _handle_status():
        success, output = GitSkills._run_safe(["git", "status", "-s"])
        if not success: 
            return GitSkills._analyze_error(output)
        
        if not output: return "✨ Working tree clean (Nothing to commit)."
        return f"📝 Git Status:\n{output}"

    @staticmethod
    def _handle_push(parts):
        msg = parts[1] if len(parts) > 1 else "Auto-update by Mio"
        cwd = os.getcwd()
        
        if not os.path.exists(".git"):
            return "❌ Current folder is not a git repository."

        # 1. Force Refresh Branch (in case user switched branches externally)
        branch = GitSkills._detect_branch(cwd, force_refresh=True)

        # 2. Check for changes
        success, status = GitSkills._run_safe(["git", "status", "--porcelain"])
        if success and not status:
            return "⚠️ No changes to push."

        # 3. Add, Commit, Push Sequence
        steps = [
            (["git", "add", "."], "Stage"),
            (["git", "commit", "-m", msg], "Commit"),
            (["git", "push", "origin", branch], "Push")
        ]

        for cmd, name in steps:
            ok, out = GitSkills._run_safe(cmd)
            if not ok:
                # Auto-Fix: No Upstream
                if "no upstream" in out.lower() or "current branch" in out.lower():
                    ok2, out2 = GitSkills._run_safe(["git", "push", "-u", "origin", branch])
                    if ok2: continue
                
                return GitSkills._analyze_error(out)

        return f"✅ Pushed to branch '{branch}' with message: '{msg}'"

    @staticmethod
    def _handle_init(parts):
        if len(parts) < 2: return "❌ Usage: [GITHUB] init | Name | [public/private]"
        
        name = parts[1]
        visibility = parts[2].lower() if len(parts) > 2 else GitSkills.GIT_CONFIG["default_visibility"]
        
        base_path = GitSkills.GIT_CONFIG["desktop_path"]
        repo_path = os.path.join(base_path, name)
        
        try:
            os.makedirs(repo_path, exist_ok=True)
            
            def run_repo(cmd): return GitSkills._run_safe(cmd, cwd=repo_path)

            # Local Init
            run_repo(["git", "init"])
            
            # Create README
            with open(os.path.join(repo_path, "README.md"), "w") as f:
                f.write(f"# {name}\n\nCreated by Mio AI 🐺")
                
            run_repo(["git", "add", "."])
            run_repo(["git", "commit", "-m", "Initial commit"])
            
            # Remote Creation
            gh_flag = "--public" if visibility == "public" else "--private"
            
            ok, out = run_repo(["gh", "repo", "create", name, gh_flag, "--source=.", "--remote=origin"])
            
            if ok:
                ok_push, out_push = run_repo(["git", "push", "-u", "origin", "main"])
                if ok_push:
                    return f"🚀 Repo '{name}' created on GitHub and pushed!"
                else:
                    return f"✅ Repo created but push failed: {GitSkills._analyze_error(out_push)}"
            else:
                return (f"✅ Local Repo created at: {repo_path}\n"
                        f"{GitSkills._analyze_error(out)}\n"
                        f"To finish manually:\n"
                        f"1. Create repo on GitHub.com\n"
                        f"2. Run: git remote add origin <URL>\n"
                        f"3. Run: git push -u origin main")

        except Exception as e: return f"❌ Init failed: {e}"

    @staticmethod
    def _handle_clone(parts):
        if len(parts) < 2: return "❌ Usage: [GITHUB] clone | url"
        url = parts[1]
        cwd = GitSkills.GIT_CONFIG["desktop_path"]
        
        ok, out = GitSkills._run_safe(["git", "clone", url], cwd=cwd)
        if ok:
            return f"✅ Cloned repository to Desktop."
        return GitSkills._analyze_error(out)