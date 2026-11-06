"""Fixed domain error codes shared by the local runtime."""


class DomainError(Exception):
    def __init__(self, code: str, message: str | None = None):
        self.code = code
        super().__init__(message or code)
