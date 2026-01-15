import os
import subprocess
import datetime
import sys

def run_cmd(args):
    """Runs a command and returns True if successful."""
    try:
        subprocess.run(args, check=True, text=True, capture_output=False)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error: {e}")
        return False

def auto_save():
    print("🐺 Mio Auto-Saver Tool")
    print("======================")
    
    # 1. Check if git exists
    if not os.path.exists(".git"):
        print("⚠️ Not a git repository. Initializing...")
        run_cmd(["git", "init"])
        run_cmd(["git", "branch", "-M", "main"])

    # 2. Add all files
    print("📂 Staging files...")
    if not run_cmd(["git", "add", "."]):
        return

    # 3. Commit
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = f"Auto-save: {timestamp} (Recovery Commit)"
    print(f"💾 Committing: '{msg}'...")
    if not run_cmd(["git", "commit", "-m", msg]):
        print("⚠️ Nothing to commit (Working tree clean).")
    
    # 4. Push (Safe attempt)
    print("☁️ Pushing to origin...")
    try:
        # Check remote first
        res = subprocess.run(["git", "remote", "-v"], capture_output=True, text=True)
        if "origin" not in res.stdout:
            print("⚠️ No remote 'origin' found. Skipping push.")
            print("💡 To fix: git remote add origin <URL>")
        else:
            run_cmd(["git", "push", "-u", "origin", "main"])
            print("✅ Successfully saved and pushed!")
    except Exception as e:
        print(f"❌ Push failed: {e}")

if __name__ == "__main__":
    auto_save()
    input("\nPress Enter to exit...")