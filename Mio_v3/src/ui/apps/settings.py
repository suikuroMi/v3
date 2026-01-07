from .base_app import BaseApp
from src.skills.settings_ops import SettingsSkills

class SettingsApp(BaseApp):
    def __init__(self):
        super().__init__("Settings", "settings.png", "#607D8B") # Blue Grey
        
        self.add_card_button("🧠 Change Persona", "Switch between Maid, Sensei, etc.", "[SETTINGS] list")
        self.add_card_button("🛡️ Security Level", "View security and permissions", lambda: self.command_signal.emit("Check my [SETTINGS] security"))
        self.add_card_button("🔧 Factory Reset", "Reset all configs (Requires Admin)", "[SETTINGS] admin TOKEN factory_reset")
        self.add_card_button("🎤 Audio Settings", "Select Input Device", "[AUDIO_DEVICES]")