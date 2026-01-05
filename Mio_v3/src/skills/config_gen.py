import json
import os

class ConfigSkills:
    @staticmethod
    def generate_git_config(args):
        """Creates a default ~/.mio_git_config.json file."""
        config_path = os.path.expanduser("~/.mio_git_config.json")
        
        if os.path.exists(config_path):
            return f"⚠️ Config file already exists at: {config_path}"
            
        default_config = {
            "desktop_path": os.path.join(os.path.expanduser("~"), "Desktop"),
            "default_branch": "main",
            "default_visibility": "public",
            "telemetry_enabled": True,
            "show_progress": True,
            "log_max_mb": 10
        }
        
        try:
            with open(config_path, 'w') as f:
                json.dump(default_config, f, indent=4)
            return f"✅ Created Git Config at: {config_path}\nYou can edit this file to change Mio's git behavior."
        except Exception as e:
            return f"❌ Failed to create config: {e}"