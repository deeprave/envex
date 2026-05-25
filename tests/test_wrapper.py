# -*- coding: utf-8 -*-
import contextlib
import io

import pytest

import envex
from envex.env_crypto import encrypt_data

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

TEST_ENV_STREAM = io.BytesIO("\n".join(TEST_ENV).encode("utf-8"))


@pytest.fixture
def password():
    return "ajf4vDFa_849&s"


def write_encrypted_env(tmp_path, password, data=b"ONE=1\nARG2=two\nENABLED=true\n"):
    env_file = tmp_path / ".env.enc"
    stream = encrypt_data(io.BytesIO(data), password)
    env_file.write_bytes(stream.getvalue())
    return env_file


@contextlib.contextmanager
def dotenv(_ignored):
    TEST_ENV_STREAM.seek(0)
    yield TEST_ENV_STREAM


def test_env_wrapper():
    env = envex.Env()
    assert "HOME" in env
    assert "USER" in env


def test_env_wrapper_dict():
    values = dict(TEST="one", ARG2="two", ENABLED=3)
    env = envex.Env(values, environ={})
    assert env("TEST") == "one"
    assert env("ARG2") == "two"
    assert env("ENABLED") == "3"


def test_env_wrapper_dict_none_is_unset():
    env = envex.Env({"TEST": "one", "ARG2": None}, environ={})

    assert env("TEST") == "one"
    assert "ARG2" not in env.env


def test_env_wrapper_stream_bytes():
    stream = io.BytesIO(b"ONE=1\nARG2=two\nENABLED=true\n")
    env = envex.Env(stream, environ={})
    assert env("ONE") == "1"
    assert env("ARG2") == "two"
    assert env("ENABLED") == "true"


def test_env_wrapper_stream_text():
    stream = io.StringIO("ONE=one\nARG2=2\nENABLED=false\n")
    env = envex.Env(stream, environ={})
    assert env("ONE") == "one"
    assert env("ARG2") == "2"
    assert env("ENABLED") == "false"


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
    assert env.int("MISSINGINTVALUE") == 0


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("-42", -42),
        ("+42", 42),
        (" 42 ", 42),
    ],
)
def test_env_int_accepts_signed_integer_values(value, expected):
    env = envex.Env({"PORT": value}, environ={})

    assert env.int("PORT") == expected


@pytest.mark.parametrize("value", ["12abc", "4.2", "--42", object()])
def test_env_int_rejects_invalid_values(value):
    env = envex.Env(environ={"PORT": value})

    with pytest.raises(ValueError):
        env.int("PORT")


def test_env_kwargs_are_environment_values():
    env = envex.Env(environ={}, EXTRA_VALUE="extra", PORT=8080, OMITTED=None)

    assert env["EXTRA_VALUE"] == "extra"
    assert env["PORT"] == "8080"
    assert "OMITTED" not in env.env


def test_env_kwargs_are_not_forwarded_to_load_env(monkeypatch):
    captured_kwargs = {}

    def fake_load_env(**kwargs):
        captured_kwargs.update(kwargs)
        return kwargs["environ"]

    monkeypatch.setattr(envex.env_wrapper, "load_env", fake_load_env)

    env = envex.Env(readenv=True, update=False, environ={}, EXTRA_VALUE="extra")

    assert env["EXTRA_VALUE"] == "extra"
    assert captured_kwargs["update"] is False
    assert "EXTRA_VALUE" not in captured_kwargs


def test_env_kwargs_override_loaded_env_values(monkeypatch):
    monkeypatch.setattr(envex.dot_env, "open_env", dotenv)

    env = envex.Env(
        readenv=True,
        update=False,
        overwrite=True,
        environ={},
        INTVALUE=999,
    )

    assert env["INTVALUE"] == "999"


def test_env_kwargs_override_stream_values():
    stream = io.BytesIO(b"FOO=stream\n")

    env = envex.Env(stream, environ={}, FOO="kwarg")

    assert env["FOO"] == "kwarg"


def test_streams_load_into_env_returned_by_readenv_update_false(monkeypatch):
    monkeypatch.setattr(envex.dot_env, "open_env", dotenv)
    stream = io.BytesIO(b"STREAM_ONLY=stream\n")

    env = envex.Env(stream, readenv=True, update=False, environ={})

    assert env["INTVALUE"] == "225"
    assert env["STREAM_ONLY"] == "stream"


def test_env_streams_kwarg_accepts_iterables():
    def stream_values():
        yield io.BytesIO(b"FIRST=one\n")
        yield io.StringIO("SECOND=two\n")

    env = envex.Env(streams=stream_values(), environ={})

    assert env["FIRST"] == "one"
    assert env["SECOND"] == "two"


@pytest.mark.parametrize("streams", [object(), ["not a stream"]])
def test_env_streams_kwarg_rejects_invalid_values(streams):
    with pytest.raises(TypeError, match="streams must"):
        envex.Env(streams=streams, environ={})


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
    assert env.is_true(1.0)
    assert env.is_true("1")
    assert not env.is_true(0)
    assert not env.is_true(0.0)
    assert not env.is_true("0")
    assert not env.is_true(False)
    assert not env.is_true(None)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (" true ", True),
        ("  FALSE\n", False),
        ("YeS", True),
        ("TrUe", True),
        ("No", False),
        (b"true", True),
        (b"YES", True),
        (b"0", False),
    ],
)
def test_is_true_normalizes_strings_and_bytes(value, expected):
    env = envex.Env()
    assert env.is_true(value) is expected


@pytest.mark.parametrize("value", ["treu", "truthy", "onward", "yesplease", "2"])
def test_is_true_rejects_invalid_strings(value):
    env = envex.Env()
    with pytest.raises(ValueError):
        env.is_true(value)


@pytest.mark.parametrize("value", [2, 2.0, 0.5, [], [1], {}, object()])
def test_is_true_rejects_invalid_non_string_values(value):
    env = envex.Env()
    with pytest.raises(ValueError):
        env.is_true(value)


def test_env_bool(monkeypatch):
    monkeypatch.setattr(envex.dot_env, "open_env", dotenv)
    env = envex.Env(readenv=True)
    assert env.bool("BOOLVALUETRUE", default=False)
    assert env.bool("DEFAULTBOOLVALUETRUE", default=True)
    assert env("DEFAULTBOOLVALUETRUE", default=True, type=bool)
    assert not env.bool("BOOLVALUEFALSE", default=True)
    assert not env.bool("DEFAULTBOOLVALUEFALSE", default=False)
    assert not env("DEFAULTBOOLVALUEFALSE", type=bool)


@pytest.mark.parametrize("value", ["treu", "truthy", "onward", "yesplease", "2"])
def test_env_bool_rejects_invalid_strings(value):
    env = envex.Env({"FLAG": value}, environ={})
    with pytest.raises(ValueError):
        env.bool("FLAG")


@pytest.mark.parametrize(
    ("skip_verify", "expected_verify"),
    [
        (None, True),
        ("false", True),
        ("0", True),
        ("true", False),
        ("1", False),
    ],
)
def test_vault_skip_verify_uses_strict_boolean_parsing(
    skip_verify, expected_verify, monkeypatch
):
    class FakeSecretsManager:
        calls = []

        def __init__(self, **kwargs):
            self.calls.append(kwargs)

    environ = {}
    if skip_verify is not None:
        environ["VAULT_SKIP_VERIFY"] = skip_verify

    monkeypatch.setattr("envex.env_wrapper.SecretsManager", FakeSecretsManager)
    envex.Env(environ=environ, verify=None)

    assert FakeSecretsManager.calls[-1]["verify"] is expected_verify


@pytest.mark.parametrize("verify", [True, False, "/path/to/ca.pem"])
def test_explicit_vault_verify_overrides_skip_verify(verify, monkeypatch):
    class FakeSecretsManager:
        calls = []

        def __init__(self, **kwargs):
            self.calls.append(kwargs)

    monkeypatch.setattr("envex.env_wrapper.SecretsManager", FakeSecretsManager)
    envex.Env(environ={"VAULT_SKIP_VERIFY": "true"}, verify=verify)

    assert FakeSecretsManager.calls[-1]["verify"] == verify


def test_invalid_vault_skip_verify_raises_value_error(monkeypatch):
    class FakeSecretsManager:
        def __init__(self, **kwargs):
            raise AssertionError("SecretsManager should not be initialized")

    monkeypatch.setattr("envex.env_wrapper.SecretsManager", FakeSecretsManager)

    with pytest.raises(ValueError):
        envex.Env(environ={"VAULT_SKIP_VERIFY": "treu"}, verify=None)


def test_is_set_uses_secret_manager_values():
    class FakeSecretsManager:
        def __init__(self, secrets):
            self.secrets = secrets

        def get_secret(self, key, default=None):
            return self.secrets.get(key, default)

    env = envex.Env(environ={})
    env.secret_manager = FakeSecretsManager({"SECRET_ONLY": "value", "EMPTY_SECRET": ""})

    assert env.is_set("SECRET_ONLY")
    assert env.is_set("EMPTY_SECRET")
    assert not env.is_set("MISSING_SECRET")


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
    # sourcery skip: no-loop-in-tests
    for k, v in values.items():
        assert env[k] == str(v)
    assert env.is_all_set(list(values.keys()))
    assert not env.is_all_set("NOTSETVAR")
    env.export({k: None for k in values})
    assert not env.is_any_set(list(values.keys()))
    env["NOT_MYVARIABLE"] = "somevalue"
    assert env.is_any_set("NOT_MYVARIABLE")

    env.export(**values)
    for k, v in values.items():
        assert env[k] == str(v)
    assert env.is_all_set(list(values.keys()))
    env.export({k: None for k in values})
    assert not env.is_any_set(list(values.keys()))

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

    result = env.setdefault("var2", None)

    assert result is None
    assert "var2" not in env.env
    env.setdefault("var2", 543)
    assert env.env["var2"] == "543"


def test_setdefault_none_preserves_existing_value():
    env = envex.Env({"var2": "value"}, environ={})

    result = env.setdefault("var2", None)

    assert result == "value"
    assert env.env["var2"] == "value"


def test_set_none_unsets_existing_value():
    env = envex.Env({"var1": "value"}, environ={})

    env.set("var1", None)

    assert "var1" not in env.env


def test_set_dict_none_unsets_existing_value():
    env = envex.Env({"var1": "value", "var2": "keep"}, environ={})

    env.set({"var1": None, "var2": 123})

    assert "var1" not in env.env
    assert env.env["var2"] == "123"


def test_setdefault_exists():
    env = envex.Env(environ={})
    # Test when variable already exists
    env.env["var3"] = "abc"
    result = env.setdefault("var3", "def")
    assert result == "abc"
    assert env.env["var3"] == "abc"


def test_encrypted_stream_bytes(password):
    data = b"ONE=1\nARG2=two\nENABLED=true\n"
    stream = encrypt_data(io.BytesIO(data), password)
    env = envex.Env(stream, password=password)
    assert env("ONE") == "1"
    assert env("ARG2") == "two"
    assert env("ENABLED") == "true"


def test_encrypted_stream_text(password):
    data = "ONE=one\nARG2=2\nENABLED=false\n"
    stream = encrypt_data(io.StringIO(data), password)
    env = envex.Env(stream, decrypt=True, password=password)
    assert env("ONE") == "one"
    assert env("ARG2") == "2"
    assert env("ENABLED") == "false"


def test_encrypted_stream_bytes_env(password):
    import os

    os.environ["TEST_PASSWORD"] = password
    data = b"ONE=1\nARG2=two\nENABLED=true\n"
    stream = encrypt_data(io.BytesIO(data), password)
    env = envex.Env(stream, decrypt=True, password="$TEST_PASSWORD")
    assert env("ONE") == "1"
    assert env("ARG2") == "two"
    assert env("ENABLED") == "true"


def test_encrypted_env_file_uses_plain_env_password(password, tmp_path):
    write_encrypted_env(tmp_path, password)

    env = envex.Env(
        readenv=True,
        environ={"ENV_PASSWORD": password},
        env_file=".env",
        search_path=tmp_path,
        update=False,
    )

    assert env("ONE") == "1"
    assert env("ARG2") == "two"
    assert env("ENABLED") == "true"


def test_encrypted_env_file_uses_indirect_env_password(password, tmp_path):
    write_encrypted_env(tmp_path, password)

    env = envex.Env(
        readenv=True,
        environ={"ENV_PASSWORD": "$TEST_PASSWORD", "TEST_PASSWORD": password},
        env_file=".env",
        search_path=tmp_path,
        update=False,
    )

    assert env("ONE") == "1"
    assert env("ARG2") == "two"
    assert env("ENABLED") == "true"


def test_encrypted_env_file_uses_file_env_password(password, tmp_path):
    write_encrypted_env(tmp_path, password)
    password_file = tmp_path / "password.txt"
    password_file.write_text(f"{password}\n")

    env = envex.Env(
        readenv=True,
        environ={"ENV_PASSWORD": f"@{password_file}"},
        env_file=".env",
        search_path=tmp_path,
        update=False,
    )

    assert env("ONE") == "1"
    assert env("ARG2") == "two"
    assert env("ENABLED") == "true"


def test_plain_env_file_fallback_with_env_password_is_not_corrupted(password, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("ONE=1\nARG2=two\nENABLED=true\n")

    env = envex.Env(
        readenv=True,
        environ={"ENV_PASSWORD": password},
        env_file=".env",
        search_path=tmp_path,
        update=False,
    )

    assert env("ONE") == "1"
    assert env("ARG2") == "two"
    assert env("ENABLED") == "true"


def test_plain_stream_with_env_password_is_not_corrupted(password):
    stream = io.BytesIO(b"ONE=1\nARG2=two\nENABLED=true\n")

    env = envex.Env(stream, environ={"ENV_PASSWORD": password})

    assert env("ONE") == "1"
    assert env("ARG2") == "two"
    assert env("ENABLED") == "true"


def test_decrypt_false_ignores_env_password(password, tmp_path):
    write_encrypted_env(tmp_path, password)

    env = envex.Env(
        readenv=True,
        decrypt=False,
        environ={"ENV_PASSWORD": password},
        env_file=".env",
        search_path=tmp_path,
        update=False,
    )

    assert env.get("ONE") is None


def test_explicit_password_file_selector(password, tmp_path):
    data = b"ONE=1\nARG2=two\nENABLED=true\n"
    stream = encrypt_data(io.BytesIO(data), password)
    password_file = tmp_path / "password.txt"
    password_file.write_text(f"{password}\n")

    env = envex.Env(stream, decrypt=True, password=f"@{password_file}", environ={})

    assert env("ONE") == "1"
    assert env("ARG2") == "two"
    assert env("ENABLED") == "true"


def test_encrypted_stream_bytes2(password):
    data = b"ONE=1\nARG2=two\nENABLED=true\n"
    stream = encrypt_data(io.BytesIO(data), password)
    env = envex.Env(stream, decrypt=True, password=password)
    assert env("ONE") == "1"
    assert env("ARG2") == "two"
    assert env("ENABLED") == "true"


def test_encrypted_stream_invalid_plaintext_fallback_decode_error(password):
    # 0xff/0xfe/0xfa are invalid leading bytes in UTF-8.
    invalid_data = b"\xff\xfe\xfa=not-utf-8\n"

    with pytest.raises(UnicodeDecodeError):
        envex.Env(io.BytesIO(invalid_data), decrypt=True, password=password)
