import os
import platform
import shutil
import subprocess
import json
import re
import time
import datetime
from src.skills.settings_ops import SettingsSkills 

try: import psutil; HAS_PSUTIL = True
except ImportError: HAS_PSUTIL = False

class SystemSkills:
    DANGEROUS_APPS = {"sudo", "rm", "format", "regedit", "diskpart", "bash", "sh", "mkfs", "fdisk", "dd", "shutdown", "reboot", "taskkill"}
    POWER_APPS = {"terminal", "cmd", "powershell", "iterm", "bash", "zsh"}
    DEFAULT_APPS = {
        "chrome", "firefox", "edge", "brave", "vscode", "code", "notepad", "notepad++", "sublime_text",
        "terminal", "cmd", "powershell", "iterm", "spotify", "discord", "slack", "calculator", 
        "calendar", "explorer", "finder", "vlc", "obsidian", "zoom", "teams"
    }
    
    SAFE_APPS = set()
    _CONFIG_PATH = os.path.expanduser("~/.mio_safe_apps.json")
    _CONFIG_MTIME = 0
    _APP_OPEN_TIMES = {}
    _MAX_OPENS_PER_MIN = 10
    _FIRST_LAUNCHES = set()
    _APP_USAGE_STATS = {} 

    @classmethod
    def _load_user_apps_smart(cls):
        if not cls.SAFE_APPS: cls.SAFE_APPS = cls.DEFAULT_APPS.copy()
        if not os.path.exists(cls._CONFIG_PATH): return

        try:
            mtime = os.path.getmtime(cls._CONFIG_PATH)
            if mtime > cls._CONFIG_MTIME:
                with open(cls._CONFIG_PATH, 'r') as f:
                    data = json.load(f)
                    raw_apps = set(data.get("user_apps", []))
                    safe_user_apps = {app for app in raw_apps if app.lower() not in cls.DANGEROUS_APPS}
                    cls.SAFE_APPS = cls.DEFAULT_APPS.union(safe_user_apps)
                    cls._CONFIG_MTIME = mtime
        except: pass

    @staticmethod
    def _log_activity(app_name, success, reason=""):
        log_dir = os.path.join(os.getcwd(), "data")
        os.makedirs(log_dir, exist_ok=True)
        try:
            with open(os.path.join(log_dir, "system_audit.log"), "a", encoding="utf-8") as f:
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                status = "ALLOWED" if success else "BLOCKED"
                f.write(f"[{timestamp}] {status}: {app_name} | {reason}\n")
        except: pass

    @staticmethod
    def _validate_app_name(name):
        return bool(re.match(r'^[a-zA-Z0-9][a-zA-Z0-9_\+\-\.\s&\(\)]*$', name))

    @staticmethod
    def _check_rate_limit(app_name):
        now = time.time()
        history = [t for t in SystemSkills._APP_OPEN_TIMES.get(app_name, []) if now - t < 60]
        if len(history) >= SystemSkills._MAX_OPENS_PER_MIN: return False
        history.append(now)
        SystemSkills._APP_OPEN_TIMES[app_name] = history
        return True

    @staticmethod
    def _app_exists(app_name):
        """Check if app exists on system before launching."""
        if platform.system() == "Darwin":
            return os.path.exists(f"/Applications/{app_name}.app")
        elif platform.system() == "Windows":
            dirs = [os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", ""), os.environ.get("LocalAppData", "")]
            for d in dirs:
                if os.path.exists(os.path.join(d, f"{app_name}.exe")): return True
            if shutil.which(app_name): return True
            return False 
        return True 

    @staticmethod
    def open_app(app_name):
        SystemSkills._load_user_apps_smart()
        clean_name = app_name.strip()
        lower_name = clean_name.lower().replace(".exe", "")
        
        if not SystemSkills._validate_app_name(clean_name):
            SystemSkills._log_activity(clean_name, False, "Illegal characters")
            return "❌ Security Alert: Illegal characters in app name."
            
        allow_sys = SettingsSkills.get("allow_system_apps") or SettingsSkills.get("god_mode")
        
        if not allow_sys and lower_name in SystemSkills.DANGEROUS_APPS:
            SystemSkills._log_activity(clean_name, False, "Blacklisted app")
            return "❌ Security Alert: This app is strictly blocked. (Enable 'allow_system_apps' or use God Mode to bypass)."

        if lower_name not in SystemSkills.SAFE_APPS and not allow_sys:
            SystemSkills._log_activity(clean_name, False, "Not in whitelist")
            return f"❌ Security Alert: '{clean_name}' not in Safe Apps. (Edit ~/.mio_safe_apps.json)"

        if not SystemSkills._check_rate_limit(lower_name):
            SystemSkills._log_activity(clean_name, False, "Rate limit exceeded")
            return "⚠️ Rate limit exceeded. Please wait a moment."

        if not SystemSkills._app_exists(clean_name) and platform.system() == "Windows":
             pass 

        if lower_name in SystemSkills.POWER_APPS and lower_name not in SystemSkills._FIRST_LAUNCHES:
            SystemSkills._FIRST_LAUNCHES.add(lower_name)
            return (f"⚠️ Opening **{clean_name}**. This is a powerful system tool.\nUse the command again to confirm execution.")

        try:
            if platform.system() == "Windows":
                try: os.startfile(clean_name)
                except: subprocess.Popen([clean_name], shell=False)
            elif platform.system() == "Darwin": subprocess.call(["open", "-a", clean_name])
            else: subprocess.call(["xdg-open", clean_name])
            
            SystemSkills._APP_USAGE_STATS[lower_name] = SystemSkills._APP_USAGE_STATS.get(lower_name, 0) + 1
            SystemSkills._log_activity(clean_name, True, "Opened successfully")
            return f"✅ Opening {clean_name}..."
        except Exception as e:
            SystemSkills._log_activity(clean_name, False, f"Error: {e}")
            return f"❌ Failed to open: {e}"

    @staticmethod
    def get_app_stats(args=""):
        stats = sorted(SystemSkills._APP_USAGE_STATS.items(), key=lambda x: x[1], reverse=True)[:5]
        if stats:
            return "📊 **Most Used Apps:**\n" + "\n".join([f"  • {app.title()}: {count}x" for app, count in stats])
        return "📉 No app usage data yet."

    @staticmethod
    def take_screenshot(args=""):
        """V5.1: Captures the screen (Restored Missing Method)."""
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        filename = f"screenshot_{int(time.time())}.png"
        filepath = os.path.join(desktop, filename)
        
        try:
            import pyautogui
            screenshot = pyautogui.screenshot()
            screenshot.save(filepath)
            return f"📸 Screenshot saved to Desktop: {filename}"
        except ImportError:
            return "❌ Python library 'pyautogui' not found. Run: pip install pyautogui"
        except Exception as e:
            return f"❌ Screenshot failed: {e}"

    @staticmethod
    def system_info(args=""):
        info = [f"💻 System: {platform.system()} {platform.release()}"]
        try:
            total, used, free = shutil.disk_usage("/")
            info.append(f"💾 Disk: {free // (2**30)}GB free / {total // (2**30)}GB total")
        except: pass
        
        if HAS_PSUTIL:
            try:
                mem = psutil.virtual_memory()
                info.extend([f"🧠 RAM: {mem.percent}% used", f"⚙️ CPU: {psutil.cpu_percent(interval=0.1)}%"])
                battery = psutil.sensors_battery()
                if battery: info.append(f"{'🔌' if battery.power_plugged else '🔋'} Battery: {battery.percent}%")
            except: pass
        else: info.append("⚠️ Install 'psutil' for detailed stats.")
        return "\n".join(info)