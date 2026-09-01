"""Loads a skill's variables.json and builds its per-call-group output schema.

variables.json groups variable extraction into call_groups; every variable
is typed by its variable_type and wrapped the same way regardless of type,
so a model's answer for a field is either found (with a value and
citations) or not_found -- never a value without evidence. See
docs/general_report_writing.md for the design.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator

from report_writing_collaborator.exceptions import VariableConfigError

if TYPE_CHECKING:
    from pathlib import Path


class Table(BaseModel):
    """A found field's table value: column headers and row data."""

    model_config = ConfigDict(extra="forbid")

    headers: list[str]
    rows: list[list[str]]


class Citation(BaseModel):
    """One piece of evidence a found field's value relies on."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    section_id: str | None = None
    page: int | None = None


_MIN_CITATIONS = 1
# Matches a report_renderer.CITATION_MARKER_PATTERN marker inside a found
# field's value, so an out-of-range index is caught here -- one call_group's
# turn -- instead of surviving to the end of the run.
_CITATION_MARKER_PATTERN = re.compile(r"\[\[cite:(\d+)\]\]")

# variable_type -> the Python type its "found" value is typed as. Extend
# this when a skill needs a new kind of field (e.g. an image reference);
# report_renderer then needs a matching stringifier, and a
# _FIELD_DESCRIPTIONS entry below.
_VARIABLE_TYPES: dict[str, type] = {"text": str, "table": Table}

# variable_type -> (citations field description, value field description).
# Restates each type's marker rule next to where the model generates it,
# not only in evidence-grounding/SKILL.md's shared prose.
_FIELD_DESCRIPTIONS: dict[str, tuple[str, str]] = {
    "text": (
        "Evidence for value, in generation order. A [[cite:N]] marker "
        "in value refers to this array's 0-based index N.",
        "Prose with a [[cite:N]] marker after every factual claim, where "
        "N is the 0-based index of its evidence in this field's own citations array.",
    ),
    "table": (
        "Evidence for the whole table, in generation order. Unlike a text "
        "field, no [[cite:N]] marker is placed in value -- these citations "
        "back the table as a whole, shown once alongside it.",
        "The table's data: column headers and row values. Never place a "
        "[[cite:N]] marker inside a cell -- citations backs the table as a "
        "whole, not individual cells.",
    ),
}


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
    citations_description, value_description = _FIELD_DESCRIPTIONS[variable.variable_type]

    def check_citation_markers(found: BaseModel) -> BaseModel:
        """Rejects a [[cite:N]] marker in value with no matching citations entry.

        Runs as part of model_validate_json, so a bad index fails inside its
        own call_group's turn instead of surviving to
        report_renderer.render() after every other turn has already run.

        `found`'s fields are only known at runtime -- this class is built
        fresh per variable_type below -- so its attributes are read via
        getattr rather than static access.

        A table's citations back the whole field, not per-cell markers --
        only a str value (a text field) has markers to check.
        """
        value = getattr(found, "value", None)
        if not isinstance(value, str):
            return found

        citations: list[Citation] = getattr(found, "citations", [])
        citation_count = len(citations)
        out_of_range = sorted(
            {int(index) for index in _CITATION_MARKER_PATTERN.findall(value)}
            - set(range(citation_count))
        )
        if out_of_range:
            raise ValueError(
                f"Citation marker index {out_of_range[0]} is out of range for field "
                f"'{variable.name}' -- only {citation_count} citations declared "
                f"(valid: 0-{citation_count - 1})"
            )
        return found

    # create_model's own stubs type __validators__ as dict[str, Callable[..., Any]],
    # narrower than what model_validator(...)(fn) actually returns
    # (PydanticDescriptorProxy) -- the documented pydantic pattern regardless.
    validators: dict[str, Any] = {
        "_check_citation_markers": model_validator(mode="after")(check_citation_markers)
    }
    found = create_model(
        f"{variable.name}_found",
        status=(Literal["found"], ...),
        # citations before value: the model commits its evidence list before
        # writing prose that references it by 0-based position.
        citations=(
            list[Citation],
            Field(..., min_length=_MIN_CITATIONS, description=citations_description),
        ),
        value=(python_type, Field(..., description=value_description)),
        __config__=ConfigDict(extra="forbid"),
        __validators__=validators,
    )
    not_found = create_model(
        f"{variable.name}_not_found",
        status=(Literal["not_found"], ...),
        __config__=ConfigDict(extra="forbid"),
    )
    # Deliberately not a discriminated union: Pydantic renders
    # Field(discriminator=...) as JSON Schema `oneOf` (plus a `discriminator`
    # keyword), which Azure OpenAI's structured-output strict schema
    # validation rejects ("'oneOf' is not permitted"). A plain union renders
    # as `anyOf`, which is supported, and validates identically here since
    # each branch's literal `status` value still disambiguates it.
    return found | not_found
