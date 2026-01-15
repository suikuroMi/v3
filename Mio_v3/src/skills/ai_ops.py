import os
import ollama
from src.agent.persona import MIO_IDENTITY

class AiSkills:
    @staticmethod
    def _read_file_safe(path):
        if not os.path.exists(path): return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except: return None

    @staticmethod
    def summarize_code(args):
        """Usage: [AI_SUMMARY] path/to/file.py"""
        path = args.strip()
        code = AiSkills._read_file_safe(path)
        if not code: return f"❌ File not found: {path}"
        
        # Limit token usage for speed
        if len(code) > 8000: code = code[:8000] + "\n...(truncated)"

        prompt = f"Analyze this code concisely. Explain what it does, key functions, and any potential issues:\n\n{code}"
        
        try:
            response = ollama.chat(model=MIO_IDENTITY["model"], messages=[{"role": "user", "content": prompt}])
            return f"🧠 **Code Analysis for {os.path.basename(path)}**:\n{response['message']['content']}"
        except Exception as e: return f"❌ AI Error: {e}"

    @staticmethod
    def generate_docstring(args):
        """Usage: [AI_DOC] path/to/file.py"""
        path = args.strip()
        code = AiSkills._read_file_safe(path)
        if not code: return f"❌ File not found: {path}"

        prompt = f"Generate Python docstrings for the functions in this file. Output ONLY the code with docstrings added:\n\n{code}"
        
        try:
            response = ollama.chat(model=MIO_IDENTITY["model"], messages=[{"role": "user", "content": prompt}])
            return f"📝 **suggested Documentation**:\n\n{response['message']['content']}"
        except Exception as e: return f"❌ AI Error: {e}"