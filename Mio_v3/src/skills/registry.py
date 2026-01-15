from src.skills.file_ops import FileSkills
from src.skills.system_ops import SystemSkills
from src.skills.coding_ops import CodingSkills
from src.skills.web_ops import WebSkills
from src.skills.git_ops import GitSkills
from src.skills.dev_tools import DevSkills         
from src.skills.productivity import ProductivitySkills 
from src.skills.config_gen import ConfigSkills
from src.skills.ai_ops import AiSkills
from src.skills.db_ops import DbSkills
from src.skills.settings_ops import SettingsSkills
from src.skills.audio_ops import AudioSkills 

class ToolRegistry:
    def __init__(self):
        self.tools = {}
        self.register_all()
        self._tool_usage = {}

    # V5.1: Tool Aliases (Synonyms)
    TOOL_ALIASES = {
        "DIR": "LIST", "LS": "LIST",
        "MD": "MKDIR", "CREATE": "MKDIR",
        "REN": "MOVE", "RENAME": "MOVE", "MV": "MOVE",
        "CODE": "VSCODE",
        "GIT": "GITHUB",
        "STATUS": "GITSTAT",
        "CONFIG": "SETTINGS",
        "HELP": "MIO_HELP" 
    }

    # V5.1: Tool Descriptions for Help Menu
    TOOL_CATEGORIES = {
        "📂 File Management": ["LIST", "MKDIR", "MOVE", "BATCH_MOVE", "PREVIEW_MOVE", "UNDO"],
        "💻 System & OS": ["OPEN", "SYSTEM_INFO", "APP_STATS", "SCREENSHOT"],
        "👩‍💻 Development": ["WRITE", "VSCODE", "TEMPLATE", "LINT", "SNIPPET", "PROJECT"],
        "🐙 Git & Version Control": ["GITHUB", "GITSTAT", "CONFIG_GIT"],
        "🗄️ Database": ["DB_QUERY", "DB_MOD", "DB_INFO", "DB_SCHEMA", "DB_EXPORT", "DB_BACKUP"],
        "🎧 Audio & Hearing": ["LISTEN", "TRANSCRIBE", "LIVESTREAM", "LISTEN_START", "LISTEN_STOP", "AUDIO_DEVICES", "SET_MIC"],
        "🧠 AI & Persona": ["AI_SUMMARY", "AI_DOC", "PERSONA"],
        "🌐 Web": ["SEARCH", "DOWNLOAD"],
        "⚙️ Admin": ["SETTINGS"]
    }

    def register_all(self):
        # --- FILES ---
        self.register("LIST", FileSkills.list_files)
        self.register("MKDIR", FileSkills.make_directory)
        self.register("MOVE", FileSkills.move_file)
        self.register("BATCH_MOVE", FileSkills.batch_move)
        self.register("PREVIEW_MOVE", FileSkills.preview_move)
        self.register("UNDO", FileSkills.undo_last_move)

        # --- SYSTEM ---
        self.register("OPEN", SystemSkills.open_app)
        self.register("SCREENSHOT", SystemSkills.take_screenshot)
        self.register("SYSTEM_INFO", SystemSkills.system_info)
        self.register("APP_STATS", SystemSkills.get_app_stats) 

        # --- CODING ---
        self.register("WRITE", CodingSkills.write_file)
        self.register("VSCODE", CodingSkills.open_vscode)
        self.register("TEMPLATE", CodingSkills.create_template)
        
        # --- GIT ---
        self.register("GITHUB", GitSkills.git_manager) 
        self.register("CONFIG_GIT", ConfigSkills.generate_git_config)

        # --- DATABASE ---
        self.register("DB_QUERY", DbSkills.query_sqlite)
        self.register("DB_MOD", DbSkills.modify_schema)
        self.register("DB_INFO", DbSkills.db_info)
        self.register("DB_SCHEMA", DbSkills.schema_view)
        self.register("DB_EXPORT", DbSkills.export_data)
        self.register("DB_BACKUP", DbSkills.backup_db)

        # --- AI & PERSONA ---
        self.register("AI_SUMMARY", AiSkills.summarize_code)
        self.register("AI_DOC", AiSkills.generate_docstring)
        self.register("PERSONA", SettingsSkills.set_persona) 
        
        # --- AUDIO (V6 Updated) ---
        self.register("TRANSCRIBE", AudioSkills.transcribe)      # Handles Files & URLs
        self.register("LISTEN", AudioSkills.listen_live)         # Listen for X seconds
        self.register("AUDIO_DEVICES", AudioSkills.list_devices) # List Mics
        self.register("SET_MIC", AudioSkills.set_input_device)   # Select Mic ID
        self.register("MIO_OPEN_NOTES", AudioSkills.get_latest_notes)
        
        # Continuous / Stream Commands
        self.register("LISTEN_START", lambda args: AudioSkills.start_continuous_mode(print)) 
        self.register("LISTEN_STOP", lambda args: AudioSkills.stop_continuous_mode())
        self.register("LIVESTREAM", AudioSkills.livestream_wrapper) # Safe wrapper for registry

        # --- WEB ---
        self.register("SEARCH", WebSkills.search_google)
        self.register("DOWNLOAD", WebSkills.download_media)

        # --- DEV TOOLS ---
        self.register("SNIPPET", DevSkills.manage_snippets)
        self.register("PROJECT", DevSkills.project_switcher)
        self.register("LINT", DevSkills.quick_lint)
        self.register("GITSTAT", DevSkills.git_status)
        
        # --- PRODUCTIVITY ---
        self.register("TIMER", ProductivitySkills.start_focus_timer)

        # --- ADMIN ---
        self.register("SETTINGS", SettingsSkills.manage_settings)
        
        # --- HELP ---
        self.register("MIO_HELP", self.list_tools_by_category) 

    def register(self, name, func):
        self.tools[name] = func

    def list_tools_by_category(self, args=""):
        """Generates a help menu."""
        output = ["📚 **Mio Tool Capability List**\n"]
        for category, tools in self.TOOL_CATEGORIES.items():
            output.append(f"**{category}**")
            # Filter tools that are actually registered
            valid_tools = [t for t in tools if t in self.tools]
            if valid_tools:
                output.append("  `" + "`, `".join(valid_tools) + "`")
        return "\n".join(output)

    def execute(self, tool_name, args):
        # 1. Resolve Aliases
        actual_tool = self.TOOL_ALIASES.get(tool_name.upper(), tool_name.upper())
        
        if actual_tool in self.tools:
            # 2. Track Usage
            self._tool_usage[actual_tool] = self._tool_usage.get(actual_tool, 0) + 1
            
            try: 
                return self.tools[actual_tool](args)
            except Exception as e: 
                return f"❌ Registry Error: Tool '{actual_tool}' crashed -> {e}"
                
        return f"❓ Unknown Tool: {tool_name} (Try [HELP])"