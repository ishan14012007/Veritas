import threading
from typing import Callable, Any, Dict, Tuple

class _Call:
    def __init__(self):
        self.event = threading.Event()
        self.result: Any = None
        self.error: Exception = None
        self.subscribers: int = 1

class SingleFlightGroup:
    """
    Prevents duplicate concurrent executions for the same target key (e.g. root domain).
    Ensures that if 1,000 requests hit simultaneously for an unverified merchant,
    the expensive verification crawler runs exactly once, and all callers receive the result.
    """
    def __init__(self):
        self._mutex = threading.Lock()
        self._calls: Dict[str, _Call] = {}

    def execute(self, key: str, fn: Callable[..., Any], *args, **kwargs) -> Tuple[Any, int]:
        """
        Executes fn(*args, **kwargs) keyed by 'key'.
        Returns: (result, subscribers_count)
        """
        with self._mutex:
            if key in self._calls:
                call = self._calls[key]
                call.subscribers += 1
                is_leader = False
            else:
                call = _Call()
                self._calls[key] = call
                is_leader = True

        if not is_leader:
            # Follower: Wait for leader to complete the job
            call.event.wait()
            if call.error:
                raise call.error
            return call.result, call.subscribers

        # Leader: Execute the expensive operation
        try:
            res = fn(*args, **kwargs)
            call.result = res
        except Exception as e:
            call.error = e
        finally:
            with self._mutex:
                del self._calls[key]
            # Unblock all waiting subscribers
            call.event.set()

        if call.error:
            raise call.error
        return call.result, call.subscribers

# Global singleton coordinator
SINGLE_FLIGHT = SingleFlightGroup()
