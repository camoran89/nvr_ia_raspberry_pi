"""Base class for action engines."""
from typing import Any


class ActionEngine:
    """Abstract base class for action engines."""
    
    def emit(self, event_type: str, payload: Any) -> None:
        """Emit an event with payload."""
        raise NotImplementedError
