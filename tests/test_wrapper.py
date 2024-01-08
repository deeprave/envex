# -*- coding: utf-8 -*-
import contextlib
import io

import pytest

import envex

TEST_ENV = [
    "# This is an example .env file",
    "DATABASE_URL=postgresql://username:password@localhost/database_name",
    "CACHE_URL=memcache://localhost:11211",
    "REDIS_URL=redis://localhost:6379/5",
    'QUOTED_VALUE="some double quoted value"',
    "INTVALUE=225",
    "FLOATVALUE=54.92",
    "BOOLVALUETRUE=True",
    "BOOLVALUEFALSE=off",
    "LISTOFQUOTEDVALUES=1,\"two\",3,'four'",
    "ALISTOFIPS=::1,127.0.0.1,mydomain.com",
]


@contextlib.contextmanager
def dotenv(ignored):
    _ = ignored
    yield io.StringIO("\n".join(TEST_ENV))


def test_env_wrapper():
    env = envex.Env()
    assert "HOME" in env
    assert "USER" in env


def test_env_get():
    env = envex.Env(environ={})
    var, val = "MY_VARIABLE", "MY_VARIABLE_VALUE"
    assert var not in env
    value = env.get(var)
    assert value is None
    value = env.get(var, val)
    assert value == val
    assert var not in env
    with pytest.raises(KeyError):
        _ = env[var]
    env[var] = val
    val = env.pop(var)
    assert value == val
    assert var not in env


def test_env_call():
    env = envex.Env()
    var, val = "MY_VARIABLE", "MY_VARIABLE_VALUE"
    assert var not in env
    value = env(var)
    assert value is None
    value = env(var, val)
    assert value == val
    assert var in env
    assert env[var] == val
    value = env(var, type="notdefined")
    assert value == val


def test_env_int(monkeypatch):
    monkeypatch.setattr(envex.dot_env, "open_env", dotenv)
    env = envex.Env(readenv=True)
    assert env.int("INTVALUE", default=99) == 225
    assert env("INTVALUE", default=99, type=int) == 225
    assert env.int("DEFAULTINTVALUE", default=981) == 981
    assert env("DEFAULTINTVALUE", default=981, type=int) == 981
    assert env("DEFAULTINTVALUE", type=int) == 981


def test_env_float(monkeypatch):
    monkeypatch.setattr(envex.dot_env, "open_env", dotenv)
    env = envex.Env(readenv=True)
    assert env.float("FLOATVALUE", default=99.9999) == 54.92
    assert env("FLOATVALUE", default=99.9999, type=float) == 54.92
    assert env.float("DEFAULTFLOATVALUE", default=83.6) == 83.6
    assert env("DEFAULTFLOATVALUE", default=83.6, type=float) == 83.6
    assert env("DEFAULTFLOATVALUE", type=float) == 83.6


def test_is_true():
    env = envex.Env()
    assert env.is_true(1)
    assert env.is_true("1")
    assert not env.is_true(0)
    assert not env.is_true("0")
    assert not env.is_true(b"0")
    assert not env.is_true(False)
    assert not env.is_true("False")
    assert not env.is_true(None)


def test_env_bool(monkeypatch):
    monkeypatch.setattr(envex.dot_env, "open_env", dotenv)
    env = envex.Env(readenv=True)
    assert env.bool("BOOLVALUETRUE", default=False)
    assert env.bool("DEFAULTBOOLVALUETRUE", default=True)
    assert env("DEFAULTBOOLVALUETRUE", default=True, type=bool)
    assert not env.bool("BOOLVALUEFALSE", default=True)
    assert not env.bool("DEFAULTBOOLVALUEFALSE", default=False)
    assert not env("DEFAULTBOOLVALUEFALSE", type=bool)


def test_env_list(monkeypatch):
    monkeypatch.setattr(envex.dot_env, "open_env", dotenv)
    env = envex.Env(readenv=True)

    result = _extracted_from_test_env_list_5(env, "ALISTOFIPS", 3)
    assert result == ["::1", "127.0.0.1", "mydomain.com"]

    result = _extracted_from_test_env_list_10(env, "ALISTOFIPS", 3)
    assert result == ["::1", "127.0.0.1", "mydomain.com"]

    result = _extracted_from_test_env_list_5(env, "LISTOFQUOTEDVALUES", 4)
    assert result == ["1", "two", "3", "four"]

    result = _extracted_from_test_env_list_10(env, "LISTOFQUOTEDVALUES", 4)
    assert result == ["1", "two", "3", "four"]


def _extracted_from_test_env_list_5(env, arg1, arg2):
    result = env.list(arg1)
    return _extracted_from__extracted_from_test_env_list_10_11(result, arg2)


def _extracted_from__extracted_from_test_env_list_10_11(result, arg2):
    assert isinstance(result, list)
    assert len(result) == arg2
    return result


def _extracted_from_test_env_list_10(env, arg1, arg2):
    result = env(arg1, type=list)
    return _extracted_from__extracted_from_test_env_list_10_11(result, arg2)


def test_env_iter(monkeypatch):
    monkeypatch.setattr(envex.dot_env, "open_env", dotenv)
    env = envex.Env(readenv=True, update=False)

    # test items() itself (returned by __iter__)
    for var, val in env.items():
        assert isinstance(var, str)
        assert isinstance(val, str)

    # test __iter__ via list()
    for var, val in list(env):
        assert isinstance(var, str)
        assert isinstance(val, str)

    # test __iter__ via dict()
    for var, val in dict(env).items():
        assert isinstance(var, str)
        assert isinstance(val, str)


def test_env_exception():
    class MyException(Exception):
        pass

    env = envex.Env(exception=MyException)
    with pytest.raises(MyException):
        _ = env["UNDEFINEDVARIABLE"]


def test_env_export():
    env = envex.Env(environ={})
    assert "MYVARIABLE" not in env
    env.export(MYVARIABLE="somevalue")
    assert env["MYVARIABLE"] == "somevalue"
    env.export(MYVARIABLE=None)
    with pytest.raises(KeyError):
        _ = env["MYVARIABLE"]
    with pytest.raises(TypeError):
        _ = env.export("NOT_MYVARIABLE")
    env.export(NOT_MYVARIABLE=None)

    values = dict(MYVARIABLE="somevalue", MYVARIABLE2=1, MYVARIABLE3="...")

    env.export(values)
    for k, v in values.items():
        assert env[k] == str(v)
    assert env.is_all_set([k for k in values.keys()])
    assert not env.is_all_set("NOTSETVAR")
    env.export({k: None for k in values.keys()})
    assert not env.is_any_set([k for k in values.keys()])
    env["NOT_MYVARIABLE"] = "somevalue"
    assert env.is_any_set("NOT_MYVARIABLE")

    env.export(**values)
    for k, v in values.items():
        assert env[k] == str(v)
    assert env.is_all_set([k for k in values.keys()])
    env.export({k: None for k in values.keys()})
    assert not env.is_any_set([k for k in values.keys()])

    import os

    env.set(values)
    env.export()
    for k, v in values.items():
        assert os.environ[k] == str(v)


def test_env_contains(monkeypatch):
    monkeypatch.setattr(envex.dot_env, "open_env", dotenv)
    env = envex.Env()
    # must be explicitly read in
    env.read_env()

    assert "DATABASE_URL" in env
    assert env["DATABASE_URL"] == "postgresql://username:password@localhost/database_name"
    assert "CACHE_URL" in env
    assert env["CACHE_URL"] == "memcache://localhost:11211"
    assert "REDIS_URL" in env
    assert env["REDIS_URL"] == "redis://localhost:6379/5"

    del env["DATABASE_URL"]
    assert "DATABASE_URL" not in env


def test_check_var(monkeypatch):
    monkeypatch.setattr(envex.dot_env, "open_env", dotenv)
    env = envex.Env()
    env.read_env()

    assert env.check_var("DATABASE_URL") != ""
    pytest.raises(KeyError, env.check_var, "UNDEFINEDVARIABLE")
    assert env.check_var(None) == ""


def test_setdefault_non_none():
    env = envex.Env(environ={})
    # Test when value is not None
    result = env.setdefault("var1", 123)
    assert result == "123"
    assert env.env["var1"] == "123"
    env.setdefault("var1", 543)
    assert env.env["var1"] == "123"


def test_setdefault_none():
    env = envex.Env(environ={})
    # Test when value is None
    result = env.setdefault("var2", None)
    assert result is None
    assert env.env["var2"] is None
    env.setdefault("var2", 543)
    assert env.env["var2"] is None


def test_setdefault_exists():
    env = envex.Env(environ={})
    # Test when variable already exists
    env.env["var3"] = "abc"
    result = env.setdefault("var3", "def")
    assert result == "abc"
    assert env.env["var3"] == "abc"
