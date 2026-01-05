import os
import sys

def create_structure():
    project_name = "Mio_v3"
    
    # The V3 Architecture
    structure = {
        # 1. Configuration & Metadata
        "": ["requirements.txt", "README.md", "setup_mio.py", ".gitignore"],
        "config": ["settings.json", "prompts.py", "keybindings.json"],
        
        # 2. Long-term Storage (Memory/Logs)
        "data": ["memory.json", "history.log", "user_profile.json", "analytics.json"],
        "data/db": [], # For SQLite if needed later
        
        # 3. Assets (Images/Sounds)
        "assets/avatars": ["mio_idle.png", "mio_think.png", "mio_happy.png"],
        "assets/sounds": ["alarm.wav", "startup.wav"],
        
        # 4. Source Code
        "src": ["__init__.py", "main.py"],
        
        # A. The Agent (Brain)
        "src/agent": {
            "__init__.py": "",
            "llm_engine.py": "# Handles Ollama/API connection",
            "memory_manager.py": "# RAG & Context handling",
            "persona.py": "# System prompts & Personality",
            "scheduler.py": "# Proactive tasks (timers/cron)"
        },
        
        # B. The Skills (Tools) - Modularized
        "src/skills": {
            "__init__.py": "",
            "registry.py": "# Tool registration logic",
            "file_ops.py": "# Move, Write, Read, Mkdir",
            "web_ops.py": "# Search, Download, Scrape",
            "coding_ops.py": "# Git, Linter, Syntax Check",
            "system_ops.py": "# Clipboard, App Open, Hardware Stats",
            "vision_ops.py": "# LLaVA/Vision processing"
        },
        
        # C. The Interface (GUI/Voice)
        "src/ui": {
            "__init__.py": "",
            "window.py": "# Main PySide6 Container",
            "widgets.py": "# Custom bubbles, inputs",
            "overlay.py": "# Floating widget logic",
            "styles.qss": "/* CSS-like styling for Qt */"
        },
        
        # D. Input/Output (Ears/Voice)
        "src/io": {
            "__init__.py": "",
            "audio_listener.py": "# Mic handling",
            "audio_player.py": "# TTS handling"
        },

        # E. Cross-Platform Utils
        "src/core": {
            "__init__.py": "",
            "os_handler.py": "# Windows/Linux compatibility layer",
            "logger.py": "# Central logging"
        }
    }

    def recursive_create(base_path, structure):
        for name, content in structure.items():
            path = os.path.join(base_path, name)
            
            if isinstance(content, dict):
                os.makedirs(path, exist_ok=True)
                print(f"📁 [DIR]  {path}")
                recursive_create(path, content)
            
            elif isinstance(content, list):
                if name: # If key is not empty string, make the dir
                    os.makedirs(path, exist_ok=True)
                    print(f"📁 [DIR]  {path}")
                
                for filename in content:
                    fpath = os.path.join(path, filename) if name else os.path.join(base_path, filename)
                    if not os.path.exists(fpath):
                        with open(fpath, 'w', encoding='utf-8') as f:
                            if filename.endswith(".py"):
                                f.write(f'# {filename} - Module for Mio v3\n')
                            elif filename == ".gitignore":
                                f.write("output/\n__pycache__/\n*.pyc\n.env\n")
                        print(f"📄 [FILE] {fpath}")

    print(f"🚀 Initializing {project_name} Protocol...")
    
    try:
        os.makedirs(project_name, exist_ok=True)
        recursive_create(project_name, structure)
        print("\n✅ Structure Created Successfully!")
        print(f"👉 Open '{project_name}' in VS Code to begin.")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    create_structure()