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


class WorkspaceBuildError(Exception):
    """Raised when a workspace cannot be built or published."""


class ElnNormalizationError(Exception):
    """Base error for fatal ELN normalization failures."""


class ElnAuthenticationError(ElnNormalizationError):
    """Raised when Benchling API authentication fails."""


class ElnFetchError(ElnNormalizationError):
    """Raised when fetching an entry or its external files fails."""


class ElnParseError(ElnNormalizationError):
    """Raised when a fetched entry cannot be rendered to Markdown."""


class VariableConfigError(Exception):
    """Raised when a skill's variables.json is missing or invalid."""


class ReportRenderError(Exception):
    """Raised when a completed value map cannot be rendered against a template."""
