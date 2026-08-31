from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from google.adk.utils._schema_utils import validate_schema

from report_writing_collaborator import (
    VariableConfigError,
    build_output_schema,
    load_variables_config,
)

if TYPE_CHECKING:
    from pathlib import Path


def _write_config(tmp_path: Path, config: dict) -> Path:
    path = tmp_path / "variables.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def test_load_variables_config_parses_call_groups_and_variables(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        {
            "call_groups": [
                {
                    "name": "report_fields",
                    "variables": [
                        {"name": "title", "variable_type": "text", "description": "Title."},
                        {"name": "conclusion", "variable_type": "text", "description": "Conc."},
                    ],
                }
            ]
        },
    )

    config = load_variables_config(path)

    assert len(config.call_groups) == 1
    group = config.call_groups[0]
    assert group.name == "report_fields"
    assert [v.name for v in group.variables] == ["title", "conclusion"]
    assert group.variables[0].variable_type == "text"
    assert group.variables[0].description == "Title."


def test_load_variables_config_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(VariableConfigError, match="Cannot read"):
        load_variables_config(tmp_path / "does-not-exist.json")


def test_load_variables_config_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "variables.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(VariableConfigError, match="Invalid JSON"):
        load_variables_config(path)


def test_load_variables_config_rejects_empty_call_groups(tmp_path: Path) -> None:
    path = _write_config(tmp_path, {"call_groups": []})

    with pytest.raises(VariableConfigError, match="non-empty list"):
        load_variables_config(path)


def test_load_variables_config_rejects_unsupported_variable_type(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        {
            "call_groups": [
                {
                    "name": "g",
                    "variables": [{"name": "x", "variable_type": "table", "description": ""}],
                }
            ]
        },
    )

    with pytest.raises(VariableConfigError, match="unsupported variable_type"):
        load_variables_config(path)


def test_load_variables_config_rejects_duplicate_variable_name_within_group(
    tmp_path: Path,
) -> None:
    path = _write_config(
        tmp_path,
        {
            "call_groups": [
                {
                    "name": "g",
                    "variables": [
                        {"name": "x", "variable_type": "text", "description": ""},
                        {"name": "x", "variable_type": "text", "description": ""},
                    ],
                }
            ]
        },
    )

    with pytest.raises(VariableConfigError, match="Duplicate variable name"):
        load_variables_config(path)


def test_load_variables_config_rejects_duplicate_variable_name_across_groups(
    tmp_path: Path,
) -> None:
    path = _write_config(
        tmp_path,
        {
            "call_groups": [
                {"name": "g1", "variables": [{"name": "x", "variable_type": "text"}]},
                {"name": "g2", "variables": [{"name": "x", "variable_type": "text"}]},
            ]
        },
    )

    with pytest.raises(VariableConfigError, match="Duplicate variable name"):
        load_variables_config(path)


def test_build_output_schema_accepts_found_with_citations(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        {"call_groups": [{"name": "g", "variables": [{"name": "title", "variable_type": "text"}]}]},
    )
    schema = build_output_schema(load_variables_config(path).call_groups[0])

    result = validate_schema(
        schema,
        json.dumps(
            {
                "title": {
                    "status": "found",
                    "value": "Report",
                    "citations": [{"source_id": "s", "section_id": "sec_findings", "page": 2}],
                }
            }
        ),
    )

    assert result == {
        "title": {
            "status": "found",
            "value": "Report",
            "citations": [{"source_id": "s", "section_id": "sec_findings", "page": 2}],
        }
    }


def test_build_output_schema_accepts_not_found_without_value_or_citations(
    tmp_path: Path,
) -> None:
    path = _write_config(
        tmp_path,
        {"call_groups": [{"name": "g", "variables": [{"name": "title", "variable_type": "text"}]}]},
    )
    schema = build_output_schema(load_variables_config(path).call_groups[0])

    result = validate_schema(schema, json.dumps({"title": {"status": "not_found"}}))

    assert result == {"title": {"status": "not_found"}}


def test_build_output_schema_rejects_found_without_citations(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        {"call_groups": [{"name": "g", "variables": [{"name": "title", "variable_type": "text"}]}]},
    )
    schema = build_output_schema(load_variables_config(path).call_groups[0])

    with pytest.raises(Exception, match="citations"):
        validate_schema(
            schema, json.dumps({"title": {"status": "found", "value": "x", "citations": []}})
        )


def test_build_output_schema_rejects_not_found_with_a_value(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        {"call_groups": [{"name": "g", "variables": [{"name": "title", "variable_type": "text"}]}]},
    )
    schema = build_output_schema(load_variables_config(path).call_groups[0])

    with pytest.raises(Exception, match="Extra inputs are not permitted"):
        validate_schema(schema, json.dumps({"title": {"status": "not_found", "value": "x"}}))
