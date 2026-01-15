import subprocess
import os

def run_cmd(args):
    try:
        print(f"👉 Running: {' '.join(args)}")
        subprocess.run(args, check=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error: {e}")
        return False

def reset_git_cache():
    print("🧹 Mio Git Cache Cleaner")
    print("========================")
    print("This will untrack ALL files and re-add them based on .gitignore.")
    
    confirm = input("Type 'yes' to proceed: ")
    if confirm.lower() != "yes":
        print("Cancelled.")
        return

    # 1. Remove everything from the Git index (staging area)
    # This DOES NOT delete your actual files, just Git's memory of them.
    print("\n1️⃣  Clearing Git index...")
    run_cmd(["git", "rm", "-r", "--cached", "."])

    # 2. Re-add everything
    # Now Git will look at .gitignore and only add what is allowed.
    print("\n2️⃣  Re-adding files (respecting .gitignore)...")
    run_cmd(["git", "add", "."])

    # 3. Commit the cleanup
    print("\n3️⃣  Committing changes...")
    run_cmd(["git", "commit", "-m", "Fix: Apply .gitignore rules and remove ignored files"])

    print("\n✅ Done! Now run your 'force_save.py' to push these changes.")

if __name__ == "__main__":
    reset_git_cache()
    input("\nPress Enter to exit...")