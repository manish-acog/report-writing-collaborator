"""Loads a skill's variables.json and builds its per-call-group output schema.

variables.json groups variable extraction into call_groups; every variable
is typed by its variable_type and wrapped the same way regardless of type,
so a model's answer for a field is either found (with a value and
citations) or not_found -- never a value without evidence. See
docs/general_report_writing.md for the design.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, create_model

from report_writing_collaborator.exceptions import VariableConfigError

if TYPE_CHECKING:
    from pathlib import Path

_MIN_CITATIONS = 1

# variable_type -> the Python type its "found" value is typed as. Extend
# this when a skill needs a new kind of field (e.g. a table or an image
# reference); report_renderer then needs a matching stringifier.
_VARIABLE_TYPES: dict[str, type] = {"text": str}


class Citation(BaseModel):
    """One piece of evidence a found field's value relies on."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    page: int | None = None


@dataclass(frozen=True, slots=True)
class VariableDef:
    name: str
    variable_type: str
    description: str


@dataclass(frozen=True, slots=True)
class CallGroup:
    name: str
    variables: tuple[VariableDef, ...]


@dataclass(frozen=True, slots=True)
class VariablesConfig:
    call_groups: tuple[CallGroup, ...]


def load_variables_config(path: Path) -> VariablesConfig:
    """Reads and validates a skill's variables.json.

    Raises:
        VariableConfigError: the file is missing, isn't valid JSON, or its
            shape is invalid -- an unknown variable_type, or a variable name
            repeated within or across call_groups.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise VariableConfigError(f"Cannot read variables config: {path}") from error
    except json.JSONDecodeError as error:
        raise VariableConfigError(f"Invalid JSON in variables config: {path}") from error

    call_groups_raw = raw.get("call_groups") if isinstance(raw, dict) else None
    if not isinstance(call_groups_raw, list) or not call_groups_raw:
        raise VariableConfigError(f"'call_groups' must be a non-empty list: {path}")

    seen_names: set[str] = set()
    call_groups = tuple(_parse_call_group(group, seen_names, path) for group in call_groups_raw)

    return VariablesConfig(call_groups=call_groups)


def _parse_call_group(raw: object, seen_names: set[str], path: Path) -> CallGroup:
    if not isinstance(raw, dict):
        raise VariableConfigError(f"Each call_group must be an object: {path}")

    name = raw.get("name")
    variables_raw = raw.get("variables")
    if not isinstance(name, str) or not name.strip():
        raise VariableConfigError(f"call_group is missing a 'name': {path}")
    if not isinstance(variables_raw, list) or not variables_raw:
        raise VariableConfigError(f"call_group '{name}' has no variables: {path}")

    variables = tuple(_parse_variable(v, seen_names, path) for v in variables_raw)
    return CallGroup(name=name, variables=variables)


def _parse_variable(raw: object, seen_names: set[str], path: Path) -> VariableDef:
    if not isinstance(raw, dict):
        raise VariableConfigError(f"Each variable must be an object: {path}")

    name = raw.get("name")
    variable_type = raw.get("variable_type")
    description = raw.get("description", "")
    if not isinstance(name, str) or not name.strip():
        raise VariableConfigError(f"Variable is missing a 'name': {path}")
    if name in seen_names:
        raise VariableConfigError(f"Duplicate variable name '{name}': {path}")
    if variable_type not in _VARIABLE_TYPES:
        supported = ", ".join(sorted(_VARIABLE_TYPES))
        raise VariableConfigError(
            f"Variable '{name}' has unsupported variable_type "
            f"'{variable_type}'; expected: {supported}"
        )

    seen_names.add(name)
    return VariableDef(name=name, variable_type=variable_type, description=str(description))


def build_output_schema(call_group: CallGroup) -> type[BaseModel]:
    """Builds the schema one bounded model call for this group must satisfy.

    Every field is `{status: "found", value, citations}` or
    `{status: "not_found"}` -- a discriminated union, so a value without
    evidence, or a not_found status carrying a stray value, doesn't parse.
    """
    fields: dict[str, Any] = {
        variable.name: (_field_type(variable), ...) for variable in call_group.variables
    }
    return create_model(
        f"{call_group.name}_output",
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )


def _field_type(variable: VariableDef) -> object:
    python_type = _VARIABLE_TYPES[variable.variable_type]

    found = create_model(
        f"{variable.name}_found",
        status=(Literal["found"], ...),
        value=(python_type, ...),
        citations=(list[Citation], Field(..., min_length=_MIN_CITATIONS)),
        __config__=ConfigDict(extra="forbid"),
    )
    not_found = create_model(
        f"{variable.name}_not_found",
        status=(Literal["not_found"], ...),
        __config__=ConfigDict(extra="forbid"),
    )
    # found/not_found are runtime-built classes, not statically known types;
    # ty cannot type-check a discriminated Union built from them.
    return Annotated[found | not_found, Field(discriminator="status")]  # ty: ignore[invalid-type-form]
