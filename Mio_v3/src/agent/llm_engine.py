import ollama
import re
import json
import os
import time
import hashlib
from enum import Enum
from collections import OrderedDict
from src.agent.persona import SYSTEM_PROMPT, MIO_IDENTITY
from src.skills.registry import ToolRegistry

# --- CONSTANTS ---
MAX_TURNS = 5
MAX_CONTEXT_TOKENS = 4096   
PRUNE_THRESHOLD = 3500      
SUMMARY_BATCH_SIZE = 6
MAX_CACHE_SIZE = 50  # V7: Prevent memory leaks

class ToolStatus(Enum):
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    FAILED = "FAILED"
    INVALID_ARGS = "INVALID_ARGS"

class BrainEngine:
    def __init__(self):
        self.model = MIO_IDENTITY["model"]
        self.tools = ToolRegistry()
        # Index 0 is strictly anchored to System Prompt
        self.history = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.session_id = f"session_{int(time.time())}"
        # V7: LRU Cache (OrderedDict for eviction)
        self.summary_cache = OrderedDict()

    # --- V7: SOPHISTICATED CODE VISION ---
    def _looks_like_code(self, text):
        """
        Analyzes text structure to determine if it's code or prose.
        Checks for indentation, brackets, and keywords.
        """
        lines = text.split('\n')
        if len(lines) < 2: return False # Single lines usually treated as text
        
        # 1. Structural Indicators
        has_indentation = any(line.startswith('    ') or line.startswith('\t') for line in lines)
        has_brackets = ('{' in text and '}' in text) or ('[' in text and ']' in text) or ('(' in text and ')' in text)
        
        # 2. Keyword Indicators
        keywords = ['def ', 'class ', 'import ', 'return ', 'var ', 'const ', 'if ', 'for ', 'while ', 'print(']
        keyword_hits = sum(1 for kw in keywords if kw in text)
        
        # 3. Decision Matrix
        # Strong signal: Keywords + Brackets OR Keywords + Indentation
        if keyword_hits >= 2 and (has_brackets or has_indentation):
            return True
        # Medium signal: High density of distinct code symbols
        if text.count('=') + text.count(';') + text.count('()') > 4:
            return True
            
        return False

    def _estimate_tokens(self, text):
        """V7: Precision estimation using Code Vision."""
        if not text: return 0
        s_text = str(text)
        
        # Dynamic divisor based on content type
        if self._looks_like_code(s_text):
            divisor = 3.5 # Code is dense
        else:
            divisor = 1.3 # Prose is sparse
            
        return int(len(s_text) / divisor)

    def _get_current_token_count(self):
        return sum(self._estimate_tokens(m.get("content", "")) for m in self.history)

    # --- V7: PERSISTENT BOUNDED CACHE ---
    def _cache_summary(self, key, value):
        """LRU Strategy: Remove oldest if full, then add new."""
        if key in self.summary_cache:
            self.summary_cache.move_to_end(key) # Mark as recently used
        self.summary_cache[key] = value
        
        if len(self.summary_cache) > MAX_CACHE_SIZE:
            self.summary_cache.popitem(last=False) # Remove oldest (FIFO)

    def _summarize_old_context(self, messages_to_summarize):
        try:
            raw_text = str(messages_to_summarize)
            
            # 1. Cost Benefit
            if self._estimate_tokens(raw_text) < 100: 
                return None 
                
            # 2. Check Cache
            ctx_hash = hashlib.md5(raw_text.encode('utf-8')).hexdigest()
            if ctx_hash in self.summary_cache:
                # Move to end to show it was used recently
                self.summary_cache.move_to_end(ctx_hash)
                return self.summary_cache[ctx_hash]

            # 3. Generate
            prompt = (
                "Summarize the following conversation history concisely. "
                "Retain key facts, user requests, and outcomes:\n\n" + raw_text
            )
            response = ollama.chat(model=self.model, messages=[{"role": "user", "content": prompt}])
            summary = response['message']['content']
            
            # 4. Store in LRU Cache
            self._cache_summary(ctx_hash, summary)
            return summary
            
        except Exception as e:
            print(f"⚠️ Summarization failed: {e}")
            return None

    def _manage_memory(self):
        current_tokens = self._get_current_token_count()
        
        if current_tokens > PRUNE_THRESHOLD:
            print(f"🧹 Memory Limit Hit ({current_tokens}/{MAX_CONTEXT_TOKENS}). Analyzing...")
            if len(self.history) <= 3: return 

            slice_end = 1 + SUMMARY_BATCH_SIZE
            old_chunk = self.history[1:slice_end]
            
            summary_text = self._summarize_old_context(old_chunk)
            
            if summary_text:
                memory_block = {
                    "role": "system", 
                    "content": f"[MEMORY RECALL]: {summary_text}"
                }
                self.history = [self.history[0], memory_block] + self.history[slice_end:]
                print(f"📉 Compressed memory block. New count: {self._get_current_token_count()}")
            else:
                self.history.pop(1)
                print("🗑️ Dropped oldest message (Compression skipped).")

    # --- VALIDATION LAYER ---
    def _validate_tool_args(self, tool_name, args):
        if not args or args.strip() == "":
            return False, "Arguments cannot be empty."
        if tool_name in ["WRITE", "MKDIR", "MOVE"] and (".." in args):
             return False, "Security: Parent directory traversal (..) not allowed."
        return True, ""

    def _extract_tool_calls(self, reply):
        pattern = r"\[([a-zA-Z_][a-zA-Z0-9_]*)\](.*?)\[/\1\]"
        matches = []
        try:
            iterator = re.finditer(pattern, reply, re.DOTALL | re.IGNORECASE)
            for match in iterator:
                tool_name = match.group(1).upper()
                args = match.group(2).strip()
                if tool_name in self.tools.tools or tool_name in self.tools.TOOL_ALIASES:
                    matches.append((tool_name, args))
                else:
                    print(f"⚠️ Unknown tool '{tool_name}' ignored.")
        except re.error: pass
        return matches

    def _analyze_result(self, tool_name, result_string):
        result_lower = result_string.lower()
        tool_error_patterns = {
            "SEARCH": ["no results", "failed", "connection"],
            "CALCULATE": ["division by zero", "syntax error"],
            "FILE": ["not found", "permission denied", "io error", "no such"],
            "GIT": ["fatal:", "error:", "conflict", "repository not found"],
            "CMD": ["not found", "not recognized"]
        }
        for key, patterns in tool_error_patterns.items():
            if tool_name == key or tool_name.startswith(f"{key}_"): 
                for pattern in patterns:
                    if pattern in result_lower:
                        return ToolStatus.FAILED, f"Tool '{tool_name}' failure: {pattern}"

        if any(i in result_lower for i in ["❌", "✗", "fail", "error", "unable to", "exception", "traceback"]):
            return ToolStatus.FAILED, f"Tool '{tool_name}' error."
        if any(i in result_lower for i in ["⚠️", "warning", "note:", "consider"]):
            return ToolStatus.WARNING, f"Tool '{tool_name}' warning."

        return ToolStatus.SUCCESS, "Success."

    # --- V7: FULL STATE PERSISTENCE ---
    def save_session(self):
        """Saves History AND Cache (Brain Dump)."""
        try:
            os.makedirs("data/sessions", exist_ok=True)
            data = {
                "version": "v7",
                "history": self.history,
                "cache": dict(self.summary_cache) # Convert OrderedDict to dict for JSON
            }
            with open(f"data/sessions/{self.session_id}.json", 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except: pass

    def load_session(self, session_id):
        """Smart Load: Handles V1-V6 (Lists) and V7+ (Dicts)."""
        path = f"data/sessions/{session_id}.json"
        if not os.path.exists(path): return False, "Not found."
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # Migration Logic
                if isinstance(data, list): # Legacy (V1-V6)
                    self.history = data
                    self.summary_cache.clear()
                    print("⚠️ Loaded legacy session (No cache).")
                elif isinstance(data, dict): # Modern (V7+)
                    self.history = data.get("history", [])
                    # Reconstruct OrderedDict
                    self.summary_cache = OrderedDict(data.get("cache", {}))
                
                self.session_id = session_id
                return True, f"Loaded {session_id}"
        except Exception as e: return False, str(e)

    # --- STREAMING CORE ---
    def think_stream(self, user_input, attachment=None):
        if attachment: user_input += f"\n[Attachment: {attachment}]"
        self.history.append({"role": "user", "content": user_input})
        self._manage_memory()

        for turn in range(MAX_TURNS):
            yield f"🧠 Thinking (Turn {turn+1})..."
            
            try:
                stream = ollama.chat(model=self.model, messages=self.history, stream=True)
                full_reply_buffer = [] 
                
                for chunk in stream:
                    content = chunk['message']['content']
                    full_reply_buffer.append(content)
                    yield content 
                
                full_reply = "".join(full_reply_buffer)
                
            except Exception as e:
                yield f"❌ Brain Error: {e}"
                return

            tool_calls = self._extract_tool_calls(full_reply)
            
            if not tool_calls:
                self.history.append({"role": "assistant", "content": full_reply})
                self.save_session()
                return 

            yield f"\n⚙️ Tools detected: {len(tool_calls)}\n"
            execution_logs = []
            turn_status = ToolStatus.SUCCESS
            
            for tool_name, args in tool_calls:
                is_valid, val_msg = self._validate_tool_args(tool_name, args)
                if not is_valid:
                    status, result = ToolStatus.INVALID_ARGS, val_msg
                else:
                    result = self.tools.execute(tool_name, args)
                    status, _ = self._analyze_result(tool_name, result)
                
                if status == ToolStatus.FAILED or status == ToolStatus.INVALID_ARGS: 
                    turn_status = ToolStatus.FAILED
                elif status == ToolStatus.WARNING and turn_status != ToolStatus.FAILED: 
                    turn_status = ToolStatus.WARNING
                
                log = f"🔧 {tool_name} [{status.value}]: {result}"
                execution_logs.append(log)
                yield f"{log}\n"

            full_turn = full_reply + "\n\n" + "\n".join(execution_logs)
            self.history.append({"role": "assistant", "content": full_turn})

            if turn_status == ToolStatus.FAILED:
                note = "SYSTEM ALERT: Tools FAILED. Fix arguments or retry."
            elif turn_status == ToolStatus.WARNING:
                note = "SYSTEM NOTE: Warnings detected. Verify results."
            else:
                note = "SYSTEM NOTE: Success. Continue."

            self.history.append({"role": "system", "content": note})
            self.save_session()

        yield "🐺 Limit reached (5 turns)."

    def think(self, user_input, attachment=None):
        """Legacy Wrapper: Consumes stream for backward compatibility."""
        generator = self.think_stream(user_input, attachment)
        ai_response_buffer = []
        
        for chunk in generator:
            if "🧠" not in chunk and "⚙️" not in chunk and "🔧" not in chunk:
                 ai_response_buffer.append(chunk)

        if self.history and self.history[-1]['role'] == 'assistant':
             return self.history[-1]['content']
        
        return "".join(ai_response_buffer)

    def clear_memory(self):
        self.history = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.session_id = f"session_{int(time.time())}"
        self.summary_cache.clear()