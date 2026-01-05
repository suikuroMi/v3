import json
import os
import datetime

MEMORY_FILE = os.path.join("data", "long_term_memory.json")

class MemoryCore:
    def __init__(self):
        self.data = self._load_memory()

    def _load_memory(self):
        if os.path.exists(MEMORY_FILE):
            try:
                with open(MEMORY_FILE, "r") as f:
                    return json.load(f)
            except: pass
        # Default Structure
        return {
            "user_profile": {
                "name": "User",
                "coding_style": "python",
                "favorite_tools": []
            },
            "project_history": [],
            "snippets": {},
            "preferences": {
                "fuzzy_search": True,
                "proactive_mode": True,
                "sensei_mode": False
            }
        }

    def save(self):
        os.makedirs("data", exist_ok=True)
        with open(MEMORY_FILE, "w") as f:
            json.dump(self.data, f, indent=4)

    # --- INTELLIGENCE API ---
    def update_profile(self, key, value):
        self.data["user_profile"][key] = value
        self.save()

    def add_project(self, path):
        if path not in self.data["project_history"]:
            self.data["project_history"].insert(0, path)
            self.data["project_history"] = self.data["project_history"][:10] # Keep last 10
            self.save()

    def get_preference(self, key):
        return self.data["preferences"].get(key, True)

    def set_preference(self, key, value):
        self.data["preferences"][key] = value
        self.save()

    # --- SNIPPETS ---
    def save_snippet(self, name, code):
        self.data["snippets"][name] = code
        self.save()
        return f"✅ Snippet '{name}' saved."

    def get_snippet(self, name):
        return self.data["snippets"].get(name, "❌ Snippet not found.")

    def list_snippets(self):
        return list(self.data["snippets"].keys())