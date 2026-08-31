class VariableConfigError(Exception):
    """Raised when a skill's variables.json is missing or invalid."""


class ReportRenderError(Exception):
    """Raised when a completed value map cannot be rendered against a template."""
