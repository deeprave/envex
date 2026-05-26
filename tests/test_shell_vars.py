# -*- coding: utf-8 -*-
import contextlib
import io

import pytest

import envex


@contextlib.contextmanager
def shell_vars_env(ignored):
    _ = ignored
    yield io.BytesIO(
        b"""
# Test file for shell-like variable substitution
FIRST=first-value
SECOND=second-value
EMPTY=

# Test standard variable substitution
STANDARD=${FIRST}

# Test variable without braces
NO_BRACES=$SECOND

# Test default value when variable is not set
DEFAULT_UNSET=${NONEXISTENT:-default-value}

# Test default value when variable is set
DEFAULT_SET=${FIRST:-default-value}

# Test conditional value when variable is set
CONDITIONAL_SET=${FIRST:+conditional-value}

# Test conditional value when variable is not set
CONDITIONAL_UNSET=${NONEXISTENT:+conditional-value}

# Test conditional value when variable is empty
CONDITIONAL_EMPTY=${EMPTY:+conditional-value}

# Test nested variable references
NESTED=${FIRST:-${SECOND}}
NESTED_DEFAULT=${NONEXISTENT:-${SECOND}}
NESTED_CONDITIONAL=${FIRST:+${SECOND}}

# Test complex cases
COMPLEX=${FIRST:+prefix-${SECOND}-suffix}
COMPLEX_DEFAULT=${NONEXISTENT:-${SECOND}-default}

VAR3=actual
VAR2=${VAR3:-default}
VAR1=${VAR2:-${VAR3:-default}}
NESTED_MULTI=${VAR1:-${VAR2:-${VAR3:-default}}}
"""
    )


def test_standard_substitution(monkeypatch):
    """Test standard variable substitution"""
    monkeypatch.setattr(envex.dot_env, "open_env", shell_vars_env)
    env = envex.load_env(search_path=".")
    assert env["STANDARD"] == "first-value"


def test_no_braces_substitution(monkeypatch):
    """Test variable substitution without braces"""
    monkeypatch.setattr(envex.dot_env, "open_env", shell_vars_env)
    env = envex.load_env(search_path=".")
    assert env["NO_BRACES"] == "second-value"


def test_default_value(monkeypatch):
    """Test default value when variable is not set"""
    monkeypatch.setattr(envex.dot_env, "open_env", shell_vars_env)
    env = envex.load_env(search_path=".")
    assert env["DEFAULT_UNSET"] == "default-value"
    assert env["DEFAULT_SET"] == "first-value"


def test_conditional_value(monkeypatch):
    """Test conditional value when variable is set or not set"""
    monkeypatch.setattr(envex.dot_env, "open_env", shell_vars_env)
    env = envex.load_env(search_path=".")
    assert env["CONDITIONAL_SET"] == "conditional-value"
    assert env["CONDITIONAL_UNSET"] == ""
    assert env["CONDITIONAL_EMPTY"] == ""


def test_nested_references(monkeypatch):
    """Test nested variable references"""
    monkeypatch.setattr(envex.dot_env, "open_env", shell_vars_env)
    env = envex.load_env(search_path=".")
    assert env["NESTED"] == "first-value"
    assert env["NESTED_DEFAULT"] == "second-value"
    assert env["NESTED_CONDITIONAL"] == "second-value"


def test_complex_cases(monkeypatch):
    """Test complex cases with multiple substitutions"""
    monkeypatch.setattr(envex.dot_env, "open_env", shell_vars_env)
    env = envex.load_env(search_path=".")
    assert env["COMPLEX"] == "prefix-second-value-suffix"
    assert env["COMPLEX_DEFAULT"] == "second-value-default"


def test_multi_level_nested(monkeypatch):
    """Test multi-level nested variable substitution resolution"""

    monkeypatch.setattr(envex.dot_env, "open_env", shell_vars_env)
    env = envex.load_env(search_path=".")
    assert env["NESTED_MULTI"] == "actual"


def build_reference_chain(length: int, final_value: str = "resolved") -> dict[str, str]:
    environ = {f"VAR{i}": f"$VAR{i + 1}" for i in range(length)}
    environ[f"VAR{length}"] = final_value
    return environ


def build_reference_cycle(length: int) -> dict[str, str]:
    return {f"VAR{i}": f"$VAR{(i + 1) % length}" for i in range(length)}


def write_reference_dotenv(tmp_path, references: dict[str, str]) -> None:
    lines = ["VALUE=$VAR0"]
    lines.extend(f"{key}={value}" for key, value in references.items())
    (tmp_path / ".env").write_text("\n".join(lines))


@pytest.mark.parametrize(
    ("references", "expected"),
    [
        pytest.param(
            build_reference_chain(envex.dot_env.MAX_RECURSION_DEPTH - 1),
            "resolved",
            id="resolves-below-limit",
        ),
        pytest.param(
            build_reference_chain(envex.dot_env.MAX_RECURSION_DEPTH),
            f"$VAR{envex.dot_env.MAX_RECURSION_DEPTH}",
            id="stops-at-limit",
        ),
        pytest.param(
            build_reference_cycle(envex.dot_env.MAX_RECURSION_DEPTH),
            "$VAR0",
            id="cycle-stops-at-limit",
        ),
    ],
)
def test_nested_vars_recursion_depth(tmp_path, references, expected):
    write_reference_dotenv(tmp_path, references)

    env = envex.load_env(search_path=tmp_path, environ={}, update=False)

    assert env["VALUE"] == expected
