import time
import logging

logger = logging.getLogger("MioUI")

class UIPerformance:
    """Tracks UI operation timings to detect lag."""
    def __init__(self):
        self.metrics = {}

    def start(self, operation):
        self.metrics[operation] = time.time()

    def end(self, operation):
        if operation in self.metrics:
            duration = time.time() - self.metrics[operation]
            if duration > 0.5: # Warning threshold
                logger.warning(f"🐢 Slow UI Operation: '{operation}' took {duration:.2f}s")
            return duration
        return 0