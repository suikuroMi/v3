import subprocess
import os

def run_cmd(args):
    try:
        subprocess.run(args, check=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Error: {e}")

print("🚑 Mio Repository Rescue")
print("========================")

# 1. Re-add everything using the fixed .gitignore
print("📂 Re-scanning and adding files...")
run_cmd(["git", "add", "."])

# 2. Check status to show you what was found
print("\n👀 Checking what Git found (Green = Good):")
subprocess.run(["git", "status"], check=False)

print("\n✅ If you see a long list of 'new file' or 'modified', it worked!")
input("Press Enter to exit...")