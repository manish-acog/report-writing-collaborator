class DocumentNormalizationError(Exception):
    """Base error for fatal document normalization failures."""


class UnsupportedDocumentTypeError(DocumentNormalizationError):
    """Raised when a source type has no normalization path."""


class DocumentConversionError(DocumentNormalizationError):
    """Raised when Office-to-PDF conversion fails."""


class DocumentParseError(DocumentNormalizationError):
    """Raised when a PDF cannot be inspected or normalized."""


class StructureIndexingError(Exception):
    """Raised when normalized Markdown cannot be read or indexed."""
