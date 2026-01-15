import json
import os
import time
import secrets
import shutil
import getpass
from datetime import datetime
from src.core.recovery import EmergencyRecovery

class SettingsSkills:
    SETTINGS_FILE = os.path.expanduser("~/.mio_system_settings.json")
    AUDIT_LOG = os.path.expanduser("~/.mio_settings_audit.log")
    TOKEN_FILE = os.path.expanduser("~/.mio_admin_token.key")
    BACKUP_DIR = os.path.expanduser("~/.mio_settings_backups")
    
    # === SAFE DEFAULTS ===
    DEFAULTS = {
        # Security
        "security_level": "strict", # strict, balanced, permissive, unlocked
        "strict_path_check": True,
        
        # Operations
        "allow_dangerous_ext": False,
        "allow_system_apps": False,
        "allow_file_deletion": False,
        "allow_any_executable": False,
        "god_mode": False,
        
        # Dev / Privacy
        "experimental_mode": False,
        "telemetry_enabled": True,
        "auto_format_code": True,

        # 🧠 NEURAL CONFIG (AI BRAIN)
        "ai_model": "qwen2.5:7b",    # Offline model (Ollama)
        "ai_temperature": 0.7,       # 0.1 (Robot) to 1.0 (Creative)
        "ai_context_window": 4096,   # Memory size
        "ai_persona": "default",     # default, sensei, coder, maid
        "voice_language": "en"       # en, jp, ph
    }

    # === DANGER LEVELS ===
    DANGER_LEVELS = {
        "1": { # Mild
            "allow_dangerous_ext": True,
            "allow_system_apps": False,
            "security_level": "balanced",
            "god_mode": False
        },
        "2": { # Moderate
            "allow_dangerous_ext": True,
            "allow_system_apps": True,
            "allow_file_deletion": True,
            "security_level": "permissive",
            "god_mode": False
        },
        "3": { # EXTREME (God Mode)
            "allow_dangerous_ext": True,
            "allow_system_apps": True,
            "allow_file_deletion": True,
            "allow_any_executable": True,
            "security_level": "unlocked",
            "god_mode": True
        }
    }

    # === VALIDATORS ===
    VALIDATORS = {
        "security_level": lambda v: v in ["strict", "balanced", "permissive", "unlocked"],
        "telemetry_enabled": lambda v: isinstance(v, bool),
        "god_mode": lambda v: isinstance(v, bool)
    }

    # --- TOKEN MANAGEMENT ---
    @classmethod
    def _get_admin_token(cls):
        """Generates token safely with user confirmation if missing."""
        if not os.path.exists(cls.TOKEN_FILE):
            print("\n⚠️  NO ADMIN TOKEN FOUND")
            token = secrets.token_urlsafe(16)
            with open(cls.TOKEN_FILE, 'w') as f:
                f.write(token)
            if os.name == 'posix': os.chmod(cls.TOKEN_FILE, 0o600)
            
            print(f"🔑 NEW ADMIN TOKEN GENERATED: {token}")
            print("⚠️  SAVE THIS! You need it for Danger Levels.\n")
            return token
        else:
            with open(cls.TOKEN_FILE, 'r') as f:
                return f.read().strip()

    @classmethod
    def _verify_token(cls, provided_token):
        real_token = cls._get_admin_token()
        return secrets.compare_digest(real_token, provided_token)

    # --- CORE OPERATIONS ---
    @classmethod
    def load_settings(cls):
        """Loads settings. If Recovery Mode, force defaults."""
        if EmergencyRecovery.is_recovery_mode():
            print("🔄 Loading Default Settings (Recovery Mode)")
            return cls.DEFAULTS.copy()

        settings = cls.DEFAULTS.copy()
        if os.path.exists(cls.SETTINGS_FILE):
            try:
                with open(cls.SETTINGS_FILE, 'r') as f:
                    user_settings = json.load(f)
                    settings.update(user_settings)
            except: pass
        return settings

    @classmethod
    def get(cls, key):
        s = cls.load_settings()
        # God Mode Override
        if s.get("god_mode", False):
            if "allow" in key: return True
            if "strict" in key: return False
        return s.get(key, cls.DEFAULTS.get(key))

    @classmethod
    def _backup_settings(cls):
        os.makedirs(cls.BACKUP_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(cls.BACKUP_DIR, f"settings_{timestamp}.json")
        if os.path.exists(cls.SETTINGS_FILE):
            shutil.copy2(cls.SETTINGS_FILE, backup_path)
            # Keep last 10
            backups = sorted(os.listdir(cls.BACKUP_DIR))
            for old in backups[:-10]:
                os.remove(os.path.join(cls.BACKUP_DIR, old))
            return backup_path
        return None

    @classmethod
    def _log_audit(cls, action, details):
        timestamp = datetime.now().isoformat()
        entry = f"[{timestamp}] {action}: {details}\n"
        try:
            with open(cls.AUDIT_LOG, 'a') as f:
                f.write(entry)
        except: pass

    @classmethod
    def _save_with_validation(cls, settings, reason):
        # Validate
        for k, v in settings.items():
            if k in cls.VALIDATORS and not cls.VALIDATORS[k](v):
                return False, f"Invalid value for {k}"
        
        cls._backup_settings()
        with open(cls.SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=4)
        cls._log_audit("SAVE", reason)
        return True, "Settings Saved."

    # --- PERSONA MANAGER (New) ---
    @staticmethod
    def set_persona(args):
        """Usage: [PERSONA] sensei | coder | maid | default"""
        persona = args.strip().lower()
        valid_personas = ["default", "sensei", "coder", "maid"]
        
        if persona not in valid_personas:
            return f"❌ Unknown persona. Available: {', '.join(valid_personas)}"
        
        s = SettingsSkills.load_settings()
        s["ai_persona"] = persona
        
        # Adjust temperature based on persona
        if persona == "coder": s["ai_temperature"] = 0.2  # Precision
        elif persona == "sensei": s["ai_temperature"] = 0.5 # Balanced
        elif persona == "maid": s["ai_temperature"] = 0.9   # Creative/Fun
        else: s["ai_temperature"] = 0.7 # Default
        
        SettingsSkills._save_with_validation(s, f"Changed persona to {persona}")
        
        return f"🎭 Persona switched to **{persona.upper()}**. (Temp: {s['ai_temperature']})"

    @staticmethod
    def manage_settings(args):
        """Usage: [SETTINGS] list | toggle key | admin token command"""
        args = args.strip()
        
        # 1. ADMIN COMMANDS
        if args.startswith("admin"):
            try:
                _, token, cmd_str = args.split(" ", 2)
            except: return "❌ Usage: [SETTINGS] admin TOKEN command"
            
            if not SettingsSkills._verify_token(token):
                SettingsSkills._log_audit("AUTH_FAIL", "Invalid Token")
                return "❌ ACCESS DENIED: Invalid Admin Token."
            
            parts = cmd_str.split(" ")
            cmd = parts[0]
            
            if cmd == "danger_level":
                level = parts[1] if len(parts) > 1 else ""
                if level not in SettingsSkills.DANGER_LEVELS:
                    return "❌ Usage: danger_level 1|2|3"
                s = SettingsSkills.load_settings()
                s.update(SettingsSkills.DANGER_LEVELS[level])
                SettingsSkills._save_with_validation(s, f"Set Danger Level {level}")
                return f"⚠️ Danger Level set to **{level}**."

            if cmd == "factory_reset":
                EmergencyRecovery.factory_reset()
                SettingsSkills._log_audit("RESET", "Factory Reset")
                return "✅ System Reset to Defaults."
            
            if cmd == "lockdown":
                s = SettingsSkills.DEFAULTS.copy()
                SettingsSkills._save_with_validation(s, "EMERGENCY LOCKDOWN")
                return "🔒 EMERGENCY LOCKDOWN ACTIVATED."

            if cmd == "export":
                path = parts[1] if len(parts) > 1 else "mio_settings_export.json"
                s = SettingsSkills.load_settings()
                with open(path, 'w') as f: json.dump(s, f, indent=4)
                return f"✅ Exported to {path}"
            
            if cmd == "import":
                path = parts[1] if len(parts) > 1 else ""
                if not os.path.exists(path): return "❌ File not found."
                with open(path, 'r') as f: new_s = json.load(f)
                SettingsSkills._save_with_validation(new_s, f"Import from {path}")
                return "✅ Settings Imported."

            return f"❌ Unknown Admin Command: {cmd}"

        # 2. LIST (Categorized with Neural Config)
        if not args or args == "list":
            s = SettingsSkills.load_settings()
            
            cats = {
                "🛡️ Security": ["security_level", "strict_path_check", "allow_dangerous_ext"],
                "⚙️ System": ["allow_system_apps", "allow_any_executable"],
                "🧠 Brain & AI": ["ai_model", "ai_persona", "ai_temperature", "ai_context_window"],
                "🔧 Dev": ["experimental_mode", "telemetry_enabled", "auto_format_code"],
                "⚡ DANGER": ["god_mode", "allow_file_deletion"]
            }
            
            out = ["⚙️ **System Settings**"]
            for cat, keys in cats.items():
                out.append(f"\n**{cat}**")
                for k in keys:
                    v = s.get(k, False)
                    # Icons for boolean vs string
                    if isinstance(v, bool): icon = "✅" if v else "❌"
                    else: icon = "🔹"
                    
                    if k == "security_level": icon = "🔍"
                    if k in SettingsSkills.DANGER_DEFAULTS: icon = "🔒" if not s.get(k) else "⚡"
                    
                    out.append(f"  {icon} `{k}`: {v}")
            
            return "\n".join(out)

        # 3. TOGGLE
        if "|" in args and "toggle" in args:
            _, key = [x.strip() for x in args.split("|")]
            
            DANGER_KEYS = ["god_mode", "allow_any_executable", "allow_file_deletion"]
            if key in DANGER_KEYS:
                return "❌ Access Denied: Change this using Admin Token (Danger Levels)."
                
            s = SettingsSkills.load_settings()
            if key not in s: return f"❌ Unknown setting: {key}"
            
            if isinstance(s[key], bool):
                s[key] = not s[key]
                SettingsSkills._save_with_validation(s, f"Toggled {key}")
                return f"⚙️ `{key}` is now **{s[key]}**."
            else:
                return f"❌ Cannot toggle non-boolean setting '{key}'. Use 'set' command."

        return "❌ Usage: [SETTINGS] list | toggle key | admin token cmd"