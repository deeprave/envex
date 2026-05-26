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


@pytest.fixture
def shell_env(monkeypatch):
    monkeypatch.setattr(envex.dot_env, "open_env", shell_vars_env)
    return envex.load_env(search_path=".", environ={}, update=False)


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("STANDARD", "first-value"),
        ("NO_BRACES", "second-value"),
        ("DEFAULT_UNSET", "default-value"),
        ("DEFAULT_SET", "first-value"),
        ("CONDITIONAL_SET", "conditional-value"),
        ("CONDITIONAL_UNSET", ""),
        ("CONDITIONAL_EMPTY", ""),
        ("NESTED", "first-value"),
        ("NESTED_DEFAULT", "second-value"),
        ("NESTED_CONDITIONAL", "second-value"),
        ("COMPLEX", "prefix-second-value-suffix"),
        ("COMPLEX_DEFAULT", "second-value-default"),
        ("NESTED_MULTI", "actual"),
    ],
)
def test_shell_variable_substitution(shell_env, key, expected):
    assert shell_env[key] == expected


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
