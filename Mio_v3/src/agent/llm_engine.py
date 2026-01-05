import ollama
import re
from src.agent.persona import SYSTEM_PROMPT, MIO_IDENTITY
from src.skills.registry import ToolRegistry

class BrainEngine:
    def __init__(self):
        self.model = MIO_IDENTITY["model"]
        self.tools = ToolRegistry()
        # Initialize with System Prompt (Anchored at index 0)
        self.history = [{"role": "system", "content": SYSTEM_PROMPT}]

    def _manage_memory(self):
        """
        V4.1 Memory Strategy:
        - Index 0: System Prompt (Anchored)
        - Last 10: Recent context (The working memory)
        - Prunes the middle to prevent 'Context Window Exceeded' errors.
        """
        if len(self.history) > 20:
            self.history = [self.history[0]] + self.history[-10:]
            print("🧹 Memory Pruned (Preserved System Identity).")

    def _analyze_result(self, tool_name, result_string):
        """
        V4.1 Enhanced Analysis:
        Uses broad keyword matching to detect failures and warnings.
        Returns: (status_code, message)
        """
        result_lower = result_string.lower()
        
        # 1. Broad Error Detection (The "Naive" fix)
        error_indicators = [
            "❌", "✗", "×", "fail", "error", "err:", "unable",
            "cannot", "could not", "not found", "does not exist",
            "permission denied", "invalid", "incorrect", "exception"
        ]
        
        for indicator in error_indicators:
            if indicator in result_lower:
                return "FAILED", f"Tool '{tool_name}' encountered an error."

        # 2. Warning Detection (Nuance)
        warning_indicators = ["⚠️", "warning", "note:", "consider", "partial"]
        for indicator in warning_indicators:
            if indicator in result_lower:
                return "WARNING", f"Tool '{tool_name}' succeeded with warnings."

        # 3. Default Success
        return "SUCCESS", f"Tool '{tool_name}' executed successfully."

    def think(self, user_input, attachment=None):
        if attachment: user_input += f"\n[Attachment: {attachment}]"
        self.history.append({"role": "user", "content": user_input})
        
        self._manage_memory()

        # --- REACT LOOP (Max 5 Turns) ---
        max_turns = 5
        
        for turn in range(max_turns):
            print(f"🧠 Mio is thinking... (Turn {turn+1}/{max_turns})")
            
            try:
                response = ollama.chat(model=self.model, messages=self.history)
                reply = response['message']['content']
            except Exception as e:
                return f"Brain Freeze! 🥶 Error: {e}"

            # Detect Tools
            tool_matches = list(re.finditer(r"\[([a-zA-Z]+)\](.*?)\[/\1\]", reply, re.DOTALL | re.IGNORECASE))
            
            # STOP CONDITION: No tools -> Return reply to user
            if not tool_matches:
                self.history.append({"role": "assistant", "content": reply})
                return reply

            # Execute Tools
            execution_logs = []
            turn_status = "SUCCESS" # Overall status for this turn
            
            print(f"⚙️ Detected {len(tool_matches)} tools...")
            
            for match in tool_matches:
                tool_name = match.group(1).upper()
                args = match.group(2).strip()
                
                result = self.tools.execute(tool_name, args)
                
                # Enhanced Analysis (Passing tool_name for future specific logic)
                status, msg = self._analyze_result(tool_name, result)
                
                # Determine overall turn health
                if status == "FAILED": turn_status = "FAILED"
                elif status == "WARNING" and turn_status != "FAILED": turn_status = "WARNING"
                
                log = f"🔧 {tool_name} [{status}]: {result}"
                execution_logs.append(log)
                print(log)

            # Update History
            full_turn = reply + "\n\n" + "\n".join(execution_logs)
            self.history.append({"role": "assistant", "content": full_turn})

            # ADAPTIVE INJECTION (The "Intelligence" Part)
            if turn_status == "FAILED":
                system_note = (
                    "SYSTEM ALERT: One or more tools FAILED. "
                    "Analyze the error message above carefully. "
                    "You MUST correct the arguments or use a different tool to fix this immediately."
                )
            elif turn_status == "WARNING":
                system_note = (
                    "SYSTEM NOTE: Tools executed with WARNINGS. "
                    "Check if the result is sufficient. If not, retry with different parameters."
                )
            else:
                system_note = (
                    "SYSTEM NOTE: Tools executed SUCCESSFULLY. "
                    "Determine if the task is complete. "
                    "If complete, reply to the user to finish. "
                    "If not, proceed to the next step."
                )

            self.history.append({"role": "system", "content": system_note})
            
            # Loop continues...

        return "🐺 I've hit my limit (5 steps). Please check if I finished the task!"

    def clear_memory(self):
        self.history = [{"role": "system", "content": SYSTEM_PROMPT}]