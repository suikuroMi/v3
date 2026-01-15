import os
import subprocess
import datetime
import sys

def run_cmd(args, ignore_error=False):
    """Runs a command. Returns True if successful, False otherwise."""
    try:
        # We capture output to prevent spam, but print it if there's an error
        result = subprocess.run(args, check=True, text=True, capture_output=False)
        return True
    except subprocess.CalledProcessError as e:
        if not ignore_error:
            print(f"❌ Error running {' '.join(args)}: {e}")
        return False

def check_remote():
    """Checks if a remote named 'origin' exists."""
    try:
        res = subprocess.run(["git", "remote", "-v"], capture_output=True, text=True)
        return "origin" in res.stdout
    except:
        return False

def auto_save():
    print("🐺 Mio Auto-Saver v2 (Smart Sync)")
    print("==================================")
    
    # 1. Initialize if needed
    if not os.path.exists(".git"):
        print("⚠️ Not a git repository. Initializing...")
        run_cmd(["git", "init"])
        run_cmd(["git", "branch", "-M", "main"])

    # 2. Stage Changes
    print("📂 Staging files...")
    if not run_cmd(["git", "add", "."]):
        return

    # 3. Commit
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = f"Auto-save: {timestamp}"
    
    # We allow commit to fail if there's nothing to commit, it's fine.
    print(f"💾 Committing...")
    committed = run_cmd(["git", "commit", "-m", msg], ignore_error=True)
    if not committed:
        print("   (Nothing to commit, proceeding to sync...)")

    # 4. Smart Sync (Pull then Push)
    if check_remote():
        print("🔄 Syncing with Origin...")
        
        # A. PULL first (Rebase keeps history clean)
        # This fixes the "fetch first" error you saw
        print("   ⬇️  Pulling changes from GitHub...")
        if not run_cmd(["git", "pull", "origin", "main", "--rebase"], ignore_error=True):
            print("⚠️ Pull failed. You might have merge conflicts.")
            print("   Please fix them manually, then run the script again.")
            return

        # B. PUSH
        print("   ☁️  Pushing to GitHub...")
        if run_cmd(["git", "push", "-u", "origin", "main"]):
            print("✅ Successfully saved and synced!")
        else:
            print("❌ Push failed.")
    else:
        print("⚠️ No remote 'origin' found. Changes saved locally only.")
        print("💡 To link GitHub: git remote add origin <URL>")

if __name__ == "__main__":
    auto_save()
    input("\nPress Enter to exit...")