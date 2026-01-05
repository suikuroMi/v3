import os
import sys
import subprocess
import platform
import shutil

# CONFIGURATION
REQUIRED_PYTHON = "3.10"
REQUIRED_MODELS = ["qwen2.5:7b", "llava:latest"]

# --- ADDED yt-dlp HERE ---
PIP_REQUIREMENTS = [
    "pyside6",
    "ollama",
    "Pillow",
    "pyautogui",
    "psutil",
    "pyperclip",
    "requests",
    "yt-dlp" 
]

def run_command(command, shell=False):
    """Runs a shell command and prints output."""
    print(f"⚙️ Running: {' '.join(command) if isinstance(command, list) else command}")
    try:
        subprocess.check_call(command, shell=shell)
        return True
    except subprocess.CalledProcessError:
        print("❌ Command failed.")
        return False

def check_ollama():
    """Checks if Ollama is installed and running."""
    print("\n🔍 Checking AI Core (Ollama)...")
    if shutil.which("ollama") is None:
        print("❌ Ollama is not found in PATH.")
        print("👉 Please install it from https://ollama.com/")
        return False
    
    # Try to connect
    try:
        import requests
        response = requests.get("http://localhost:11434/")
        if response.status_code == 200:
            print("✅ Ollama is running.")
            return True
    except:
        print("⚠️ Ollama is installed but not running.")
        print("👉 Please start Ollama first!")
        return False
    return False

def install_python_deps():
    """Installs pip packages."""
    print("\n📦 Installing Python Dependencies...")
    cmd = [sys.executable, "-m", "pip", "install"] + PIP_REQUIREMENTS
    run_command(cmd)

def pull_models():
    """Tells Ollama to download the brains."""
    print("\n🧠 Downloading AI Models (this may take a while)...")
    for model in REQUIRED_MODELS:
        print(f"⬇️ Pulling {model}...")
        run_command(["ollama", "pull", model])

def main():
    print("=== 🐺 OOKAMI MIO V3 SETUP WIZARD ===")
    
    # 1. Check OS
    os_name = platform.system()
    print(f"🖥️ Detected OS: {os_name}")
    
    # 2. Install Dependencies (Includes yt-dlp now)
    install_python_deps()
    
    # 3. Check Ollama
    if check_ollama():
        pull_models()
    else:
        print("⚠️ Skipping model download (Ollama issue). Run 'ollama pull qwen2.5:7b' manually later.")

    # 4. Finalize
    print("\n✅ Setup Complete!")
    print("To start Mio, run: python src/main.py")

if __name__ == "__main__":
    main()