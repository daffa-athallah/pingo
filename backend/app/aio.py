import asyncio
import sys

if sys.version_info >= (3, 11):
    timeout = asyncio.timeout
else:
    class timeout:
        """asyncio.timeout for Python 3.10 (the backend venv): cancel the current task after `seconds`, raise TimeoutError."""
        def __init__(self, seconds): self.seconds, self.fired = seconds, False

        async def __aenter__(self):
            task = asyncio.current_task()
            def fire(): self.fired = True; task.cancel()
            self.handle = asyncio.get_running_loop().call_later(self.seconds, fire)
            return self

        async def __aexit__(self, kind, error, trace):
            self.handle.cancel()
            if self.fired and kind is asyncio.CancelledError:
                raise TimeoutError from error
            return False
