# -*- coding: utf-8 -*-
import contextlib
import io

import pytest

import envex


@pytest.fixture
def envmap():
    return {
        "FIRST": "first-value",
        "SECOND": "second-value",
        "THIRD": "third-value",
        "FORTH": "forth-value",
    }


@contextlib.contextmanager
def dotenv(ignored):
    _ = ignored
    yield io.BytesIO(
        b"""
# This is an example .env file
SECOND=a-second-value
THIRD=alternative-third
export FIFTH=fifth-value
COMBINED=${FIRST}:${THIRD}:${FIFTH}
DOUBLE_QUOTED="a quoted value"
SINGLE_QUOTED='a quoted value'
"""
    )


def test_load_env(monkeypatch, envmap):
    monkeypatch.setattr(envex.dot_env, "open_env", dotenv)
    env = envex.load_env(search_path=__file__, environ=envmap)
    for var in envmap.keys():
        assert var in env
    assert "FIFTH" in env
    assert env["COMBINED"] == "first-value:third-value:fifth-value"


def test_load_env_overwrite(monkeypatch, envmap):
    monkeypatch.setattr(envex.dot_env, "open_env", dotenv)
    env = envex.load_env(search_path=__file__, environ=envmap, overwrite=True)
    for var in envmap.keys():
        assert var in env
    assert "FIFTH" in env
    assert env["COMBINED"] == "first-value:alternative-third:fifth-value"


def test_quoted_value(monkeypatch, envmap):
    monkeypatch.setattr(envex.dot_env, "open_env", dotenv)
    env = envex.load_env(search_path=__file__, environ=envmap)
    assert env["DOUBLE_QUOTED"] == "a quoted value"
    assert env["SINGLE_QUOTED"] == "a quoted value"
