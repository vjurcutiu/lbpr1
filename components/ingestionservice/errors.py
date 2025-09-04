class IngestionError(Exception):
    """Base error for IngestionService."""


class BadRequestError(IngestionError):
    """Invalid input payload or unsupported combination."""


class AdapterError(IngestionError):
    """Failure from a downstream port/adapter."""


