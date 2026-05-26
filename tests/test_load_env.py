# -*- coding: utf-8 -*-
import contextlib
import errno
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


def test_empty_values_are_preserved(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("EMPTY=\n")

    env = envex.load_env(search_path=tmp_path, environ={}, update=False)

    assert env["EMPTY"] == ""


def test_empty_values_follow_overwrite_semantics(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("EMPTY=\n")

    preserved = envex.load_env(
        search_path=tmp_path,
        environ={"EMPTY": "existing"},
        update=False,
        overwrite=False,
    )
    overwritten = envex.load_env(
        search_path=tmp_path,
        environ={"EMPTY": "existing"},
        update=False,
        overwrite=True,
    )

    assert preserved["EMPTY"] == "existing"
    assert overwritten["EMPTY"] == ""


def test_export_empty_value_respects_isolated_environ(tmp_path, monkeypatch):
    monkeypatch.delenv("EMPTY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("export EMPTY=\n")

    env = envex.load_env(search_path=tmp_path, environ={}, update=False)

    assert env["EMPTY"] == ""
    assert "EMPTY" not in envex.dot_env.os.environ


def test_export_empty_values_follow_overwrite_semantics(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("export EMPTY=\n")

    preserved = envex.load_env(
        search_path=tmp_path,
        environ={"EMPTY": "existing"},
        update=False,
        overwrite=False,
    )
    overwritten = envex.load_env(
        search_path=tmp_path,
        environ={"EMPTY": "existing"},
        update=False,
        overwrite=True,
    )

    assert preserved["EMPTY"] == "existing"
    assert overwritten["EMPTY"] == ""


def test_missing_env_file_does_not_yield_phantom_path(tmp_path):
    env = envex.load_env(
        env_file=".missing",
        search_path=tmp_path,
        environ={"EXISTING": "value"},
        update=False,
        working_dirs=True,
    )

    assert env["EXISTING"] == "value"
    assert "CWD" in env
    assert "PWD" not in env


def test_missing_env_file_errors_true_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        envex.load_env(
            env_file=".missing",
            search_path=tmp_path,
            environ={},
            update=False,
            errors=True,
        )


def test_missing_env_file_error_lists_parent_search_paths(tmp_path):
    nested = tmp_path / "project" / "child"
    nested.mkdir(parents=True)

    with pytest.raises(FileNotFoundError) as exc_info:
        envex.load_env(
            env_file=".missing",
            search_path=nested,
            environ={},
            update=False,
            errors=True,
            parents=True,
        )

    message = str(exc_info.value)
    assert nested.resolve().as_posix() in message
    assert nested.parent.resolve().as_posix() in message


def test_env_file_probe_reraises_unexpected_oserror(tmp_path, monkeypatch):
    def broken_open_env(_path):
        raise OSError(errno.EIO, "read failure")

    monkeypatch.setattr(envex.dot_env, "open_env", broken_open_env)

    with pytest.raises(OSError, match="read failure"):
        envex.load_env(search_path=tmp_path, environ={}, update=False)


def test_post_process_iterates_over_snapshot():
    class IterationGuard(dict):
        iterating = False

        def items(self):
            self.iterating = True
            try:
                yield from super().items()
            finally:
                self.iterating = False

        def __setitem__(self, key, value):
            if self.iterating:
                raise RuntimeError("mutation during iteration")
            super().__setitem__(key, value)

    env = IterationGuard({"BASE": "value", "COMBINED": "$BASE"})

    result = envex.dot_env._post_process(env)

    assert result["COMBINED"] == "value"


def test_load_env_overwrite(monkeypatch, envmap):
    monkeypatch.setattr(envex.dot_env, "open_env", dotenv)
    env = envex.load_env(search_path=__file__, environ=envmap, overwrite=True)
    for var in envmap.keys():
        assert var in env
    assert "FIFTH" in env
    assert env["COMBINED"] == "first-value:alternative-third:fifth-value"


def test_load_env_accepts_bytes_search_path(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("FROM_BYTES=ok\n")

    env = envex.load_env(
        search_path=tmp_path.as_posix().encode(),
        environ={},
        update=False,
    )

    assert env["FROM_BYTES"] == "ok"


def test_load_env_accepts_iterable_search_path(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("FROM_ITERABLE=ok\n")
    search_path = (path for path in [tmp_path])

    env = envex.load_env(
        search_path=search_path,
        environ={},
        update=False,
    )

    assert env["FROM_ITERABLE"] == "ok"


def test_filesystem_path_decode_uses_surrogateescape():
    assert envex.dot_env._decode_filesystem_path(b"\xff")


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
