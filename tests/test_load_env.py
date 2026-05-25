# -*- coding: utf-8 -*-
import contextlib
import io
import importlib.util

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


def load_module(module_path):
    spec = importlib.util.spec_from_file_location(module_path.stem, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_load_env(monkeypatch, envmap):
    monkeypatch.setattr(envex.dot_env, "open_env", dotenv)
    env = envex.load_env(search_path=__file__, environ=envmap)
    for var in envmap.keys():
        assert var in env
    assert "FIFTH" in env
    assert env["COMBINED"] == "first-value:third-value:fifth-value"


def test_export_command_respects_isolated_environ(monkeypatch, envmap):
    monkeypatch.delenv("FIFTH", raising=False)
    monkeypatch.setattr(envex.dot_env, "open_env", dotenv)

    env = envex.load_env(search_path=__file__, environ=envmap, update=False)

    assert env["FIFTH"] == "fifth-value"
    assert "FIFTH" not in envex.dot_env.os.environ


def test_export_command_updates_os_environ_only_when_requested(monkeypatch, envmap):
    monkeypatch.delenv("FIFTH", raising=False)
    monkeypatch.setattr(envex.dot_env, "open_env", dotenv)

    env = envex.load_env(search_path=__file__, environ=envmap, update=True)

    assert env["FIFTH"] == "fifth-value"
    assert envex.dot_env.os.environ["FIFTH"] == "fifth-value"


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


def test_load_env_default_search_path_uses_external_caller(tmp_path, monkeypatch):
    caller_dir = tmp_path / "caller"
    caller_dir.mkdir()
    (caller_dir / ".env").write_text("FROM_CALLER=direct\n")
    module_path = caller_dir / "caller_module.py"
    module_path.write_text(
        "import envex\n"
        "\n"
        "def load():\n"
        "    return envex.load_env(environ={}, update=False, working_dirs=False)\n"
    )
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)

    module = load_module(module_path)
    env = module.load()

    assert env["FROM_CALLER"] == "direct"


def test_env_readenv_default_search_path_skips_envex_wrappers(tmp_path, monkeypatch):
    caller_dir = tmp_path / "caller"
    caller_dir.mkdir()
    (caller_dir / ".env").write_text("FROM_CALLER=wrapper\n")
    module_path = caller_dir / "caller_module.py"
    module_path.write_text(
        "import envex\n"
        "\n"
        "def load():\n"
        "    return envex.Env(readenv=True, environ={}, update=False, working_dirs=False)\n"
    )
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)

    module = load_module(module_path)
    env = module.load()

    assert env["FROM_CALLER"] == "wrapper"
