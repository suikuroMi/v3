#!/usr/bin/env python3
"""
🐺 Ookami Mio Setup Wizard V2
One-click setup: Installs dependencies, checks system tools, and creates shortcuts.
"""

import sys
import os
import subprocess
import shutil
import platform
import time

REQUIRED_PYTHON = (3, 8)
DEPENDENCIES = ["PySide6", "ollama", "requests", "psutil"]

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_banner():
    clear_screen()
    print("=" * 60)
    print("       🐺 OOKAMI MIO - INSTALLATION WIZARD 🐺")
    print("=" * 60)

def check_python():
    print(f"🔍 Checking Python version... {sys.version.split()[0]}")
    if sys.version_info < REQUIRED_PYTHON:
        print(f"❌ Python {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}+ required.")
        return False
    print("✅ Python version OK.")
    return True

def install_dependencies():
    print("\n📦 Checking Python Dependencies...")
    missing = []
    
    # Check what's missing first
    import importlib.util
    for dep in DEPENDENCIES:
        if importlib.util.find_spec(dep) is None:
            missing.append(dep)
            
    if not missing:
        print("✅ All dependencies already installed.")
        return True

    print(f"⚠️  Missing: {', '.join(missing)}")
    print("🚀 Installing now...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing)
        print("✅ Dependencies installed successfully.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        return False

def check_system_tools():
    print("\n🛠️  Checking System Tools...")
    
    tools = {
        "ffmpeg": "Required for Audio/Hearing.",
        "git": "Required for Version Control skills.",
        "code": "Visual Studio Code (Recommended IDE)."
    }
    
    all_good = True
    for tool, desc in tools.items():
        if shutil.which(tool):
            print(f"✅ Found {tool}")
        else:
            print(f"⚠️  Missing {tool}: {desc}")
            all_good = False
            
    if not all_good:
        print("\n💡 Tip: Install missing tools to unlock full functionality.")

def create_shortcut():
    print("\n🔗 Creating Desktop Shortcut...")
    
    system = platform.system()
    script_path = os.path.abspath("src/main.py")
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    icon_path = os.path.abspath("assets/avatars/mio_idle.png")
    
    if system == "Windows":
        try:
            import winshell
            from win32com.client import Dispatch
            
            path = os.path.join(desktop, "Ookami Mio.lnk")
            shell = Dispatch('WScript.Shell')
            shortcut = shell.CreateShortCut(path)
            shortcut.TargetPath = sys.executable
            shortcut.Arguments = f'"{script_path}"'
            shortcut.WorkingDirectory = os.path.dirname(script_path)
            shortcut.IconLocation = icon_path
            shortcut.save()
            print(f"✅ Shortcut created at: {path}")
        except ImportError:
            print("⚠️  To create Windows shortcuts, install pywin32: pip install pywin32")
            
    elif system == "Linux":
        content = f"""[Desktop Entry]
Type=Application
Name=Ookami Mio
Exec={sys.executable} "{script_path}"
Icon={icon_path}
Terminal=false
Categories=Utility;
"""
        path = os.path.join(desktop, "mio.desktop")
        try:
            with open(path, "w") as f:
                f.write(content)
            os.chmod(path, 0o755)
            print(f"✅ Shortcut created at: {path}")
        except Exception as e:
            print(f"❌ Failed to create shortcut: {e}")
            
    else:
        print(f"ℹ️  OS '{system}' shortcut creation not yet supported.")

def main():
    print_banner()
    
    if not check_python():
        return
        
    if not install_dependencies():
        print("❌ Setup Failed.")
        return
        
    check_system_tools()
    
    if input("\nCreate Desktop Shortcut? (Y/n): ").lower() in ['y', 'yes', '']:
        create_shortcut()
        
    print("\n" + "="*60)
    print("🎉 SETUP COMPLETE! 🎉")
    print(f"Run Mio by typing: python src/main.py")
    print("="*60)
    time.sleep(1)

if __name__ == "__main__":
    main()