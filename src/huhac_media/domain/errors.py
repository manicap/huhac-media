class HuhacMediaError(Exception):
    """Base exception for expected application failures."""


class FatalError(HuhacMediaError):
    """An infrastructure failure that prevents the batch from continuing."""


class MediaError(HuhacMediaError):
    def __init__(self, code: str, message: str, *, phase: str, diagnostics: dict | None = None):
        super().__init__(message)
        self.code = code
        self.phase = phase
        self.diagnostics = diagnostics or {}

