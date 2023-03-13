# -*- coding: utf-8 -*-
import contextlib
import io
import envex
import pytest


TEST_ENV = [
    '# This is an example .env file',
    'DATABASE_URL=postgresql://username:password@localhost/database_name',
    'CACHE_URL=memcache://localhost:11211',
    'REDIS_URL=redis://localhost:6379/5',
    'QUOTED_VALUE="some double quoted value"',
    'INTVALUE=225',
    'FLOATVALUE=54.92',
    'BOOLVALUETRUE=True',
    'BOOLVALUEFALSE=off',
    'LISTOFQUOTEDVALUES=1,"two",3,\'four\'',
    'ALISTOFIPS=::1,127.0.0.1,mydomain.com',
]


@contextlib.contextmanager
def dotenv(ignored):
    _ = ignored
    yield io.StringIO("\n".join(TEST_ENV))


def test_env_wrapper():
    env = envex.Env()
    assert 'HOME' in env
    assert 'USER' in env


def test_env_call():
    env = envex.Env()
    var, val = 'MY_VARIABLE', 'MY_VARIABLE_VALUE'
    assert var not in env
    value = env(var)
    assert value is None
    value = env(var, val)
    assert value == val
    assert var in env
    assert env[var] == val


def test_env_int(monkeypatch):
    monkeypatch.setattr(envex.dot_env, 'open_env', dotenv)
    env = envex.Env(readenv=True)
    assert env.int('INTVALUE', default=99) == 225
    assert env('INTVALUE', default=99, type=int) == 225
    assert env.int('DEFAULTINTVALUE', default=981) == 981
    assert env('DEFAULTINTVALUE', default=981, type=int) == 981
    assert env('DEFAULTINTVALUE', type=int) == 981


def test_env_float(monkeypatch):
    monkeypatch.setattr(envex.dot_env, 'open_env', dotenv)
    env = envex.Env(readenv=True)
    assert env.float('FLOATVALUE', default=99.9999) == 54.92
    assert env('FLOATVALUE', default=99.9999, type=float) == 54.92
    assert env.float('DEFAULTFLOATVALUE', default=83.6) == 83.6
    assert env('DEFAULTFLOATVALUE', default=83.6, type=float) == 83.6
    assert env('DEFAULTFLOATVALUE', type=float) == 83.6


def test_is_true():
    env = envex.Env()
    assert env.is_true(1)
    assert env.is_true('1')
    assert not env.is_true(0)
    assert not env.is_true('0')
    assert not env.is_true(b'0')
    assert not env.is_true(False)
    assert not env.is_true('False')
    assert not env.is_true(None)


def test_env_bool(monkeypatch):
    monkeypatch.setattr(envex.dot_env, 'open_env', dotenv)
    env = envex.Env(readenv=True)
    assert env.bool('BOOLVALUETRUE', default=False)
    assert env.bool('DEFAULTBOOLVALUETRUE', default=True)
    assert env('DEFAULTBOOLVALUETRUE', default=True, type=bool)
    assert not env.bool('BOOLVALUEFALSE', default=True)
    assert not env.bool('DEFAULTBOOLVALUEFALSE', default=False)
    assert not env('DEFAULTBOOLVALUEFALSE', type=bool)


def test_env_list(monkeypatch):
    monkeypatch.setattr(envex.dot_env, 'open_env', dotenv)
    env = envex.Env(readenv=True)

    result = env.list('ALISTOFIPS')
    assert isinstance(result, list)
    assert len(result) == 3
    assert result == ['::1', '127.0.0.1', 'mydomain.com']

    result = env('ALISTOFIPS', type=list)
    assert isinstance(result, list)
    assert len(result) == 3
    assert result == ['::1', '127.0.0.1', 'mydomain.com']

    result = env.list('LISTOFQUOTEDVALUES')
    assert isinstance(result, list)
    assert len(result) == 4
    assert result == ['1', 'two', '3', 'four']

    result = env('LISTOFQUOTEDVALUES', type=list)
    assert isinstance(result, list)
    assert len(result) == 4
    assert result == ['1', 'two', '3', 'four']


def test_env_iter(monkeypatch):
    monkeypatch.setattr(envex.dot_env, 'open_env', dotenv)
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
        _ = env['UNDEFINEDVARIABLE']


def test_env_export():
    env = envex.Env()
    assert 'MYVARIABLE' not in env
    env.export(MYVARIABLE='somevalue')
    assert env['MYVARIABLE'] == 'somevalue'
    env.export(MYVARIABLE=None)
    with pytest.raises(KeyError):
        _ = env['MYVARIABLE']

    values = dict(MYVARIABLE='somevalue', MYVARIABLE2=1, MYVARIABLE3='...')

    env.export(values)
    for k, v in values.items():
        assert env[k] == str(v)
    env.export({k: None for k in values.keys()})
    assert not env.is_any_set([k for k in values.keys()])

    env.export(**values)
    for k, v in values.items():
        assert env[k] == str(v)
    env.export({k: None for k in values.keys()})
    assert not env.is_any_set([k for k in values.keys()])

    import os

    env.export(**values)
    for k, v in values.items():
        assert os.environ[k] == str(v)


def test_env_contains(monkeypatch):
    monkeypatch.setattr(envex.dot_env, 'open_env', dotenv)
    env = envex.Env()
    # must be explicitly read in
    env.read_env()

    assert 'DATABASE_URL' in env
    assert env['DATABASE_URL'] == "postgresql://username:password@localhost/database_name"
    assert 'CACHE_URL' in env
    assert env['CACHE_URL'] == "memcache://localhost:11211"
    assert 'REDIS_URL' in env
    assert env['REDIS_URL'] == "redis://localhost:6379/5"
