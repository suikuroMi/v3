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

def force_save():
    print("🐺 Mio FORCE-Saver Tool")
    print("=======================")
    print("⚠️ WARNING: This will overwrite the remote repository.")
    
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
    msg = f"Force-save: {timestamp} (Overwriting Remote)"
    print(f"💾 Committing: '{msg}'...")
    
    # We attempt commit, but even if it says 'nothing to commit', we might still need to push 
    # if the local history is different from remote.
    if not run_cmd(["git", "commit", "-m", msg]):
        print("⚠️ No changes to commit, proceeding to force push checks...")
    
    # 4. Force Push
    print("🔥 FORCE Pushing to origin...")
    try:
        # Check remote first
        res = subprocess.run(["git", "remote", "-v"], capture_output=True, text=True)
        if "origin" not in res.stdout:
            print("⚠️ No remote 'origin' found. Skipping push.")
            print("💡 To fix: git remote add origin <URL>")
        else:
            # THE KEY CHANGE: Added "--force"
            run_cmd(["git", "push", "-u", "origin", "main", "--force"])
            print("✅ Successfully FORCE pushed!")
    except Exception as e:
        print(f"❌ Push failed: {e}")

if __name__ == "__main__":
    force_save()
    input("\nPress Enter to exit...")