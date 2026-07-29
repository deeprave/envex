# -*- coding: utf-8 -*-
import contextlib
import io
import os

import pytest

import envex
import envex.env_crypto as env_crypto
from envex.env_crypto import DecryptError, encrypt_data

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


@pytest.mark.parametrize(
    ("stream", "expected"),
    [
        (
            io.BytesIO(b"ONE=1\nARG2=two\nENABLED=true\n"),
            {"ONE": "1", "ARG2": "two", "ENABLED": "true"},
        ),
        (
            io.StringIO("ONE=one\nARG2=2\nENABLED=false\n"),
            {"ONE": "one", "ARG2": "2", "ENABLED": "false"},
        ),
    ],
    ids=["bytes", "text"],
)
def test_env_wrapper_streams(stream, expected):
    env = envex.Env(stream, environ={})

    for key, value in expected.items():
        assert env(key) == value


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
        (None, None),
        ("false", None),
        ("0", None),
        ("true", False),
        ("1", False),
    ],
)
def test_vault_skip_verify_uses_strict_boolean_parsing(
    skip_verify, expected_verify, monkeypatch
):
    calls = []

    class FakeSecretsManager:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            self.client = object()

    environ = {"VAULT_TOKEN": "token"}
    if skip_verify is not None:
        environ["VAULT_SKIP_VERIFY"] = skip_verify

    monkeypatch.setattr("envex.env_wrapper.SecretsManager", FakeSecretsManager)
    envex.Env(environ=environ, verify=None)

    assert calls[-1]["verify"] is expected_verify


@pytest.mark.parametrize("verify", [True, False, "/path/to/ca.pem"])
def test_explicit_vault_verify_overrides_skip_verify(verify, monkeypatch):
    calls = []

    class FakeSecretsManager:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            self.client = object()

    monkeypatch.setattr("envex.env_wrapper.SecretsManager", FakeSecretsManager)
    envex.Env(
        environ={"VAULT_SKIP_VERIFY": "true", "VAULT_TOKEN": "token"},
        verify=verify,
    )

    assert calls[-1]["verify"] == verify


def test_invalid_vault_skip_verify_raises_value_error(monkeypatch):
    class FakeSecretsManager:
        def __init__(self, **kwargs):
            raise AssertionError("SecretsManager should not be initialized")

    monkeypatch.setattr("envex.env_wrapper.SecretsManager", FakeSecretsManager)

    with pytest.raises(ValueError):
        envex.Env(environ={"VAULT_SKIP_VERIFY": "treu"}, verify=None)


def test_env_skips_vault_without_configuration(monkeypatch):
    class FakeSecretsManager:
        def __init__(self, **_kwargs):
            raise AssertionError("Vault should not be initialized")

    monkeypatch.setattr("envex.env_wrapper.SecretsManager", FakeSecretsManager)

    env = envex.Env(environ={})

    assert env.secret_manager is None


def test_env_warns_and_skips_partial_vault_configuration(monkeypatch, caplog):
    class FakeSecretsManager:
        def __init__(self, **_kwargs):
            raise AssertionError("Vault should not be initialized")

    monkeypatch.setattr("envex.env_wrapper.SecretsManager", FakeSecretsManager)

    env = envex.Env(environ={"VAULT_ADDR": "https://vault.example"})

    assert env.secret_manager is None
    assert "configuration is incomplete" in caplog.text


def test_env_creates_path_scoped_view_from_secrets_manager(monkeypatch):
    class FakeSecretsManager:
        def __init__(self, **_kwargs):
            self.client = object()

        @classmethod
        def from_manager(cls, manager, *, base_path=None, mount_point=None):
            return (manager, base_path, mount_point)

    monkeypatch.setattr("envex.env_wrapper.SecretsManager", FakeSecretsManager)
    source = FakeSecretsManager()

    env = envex.Env(
        environ={}, secrets_manager=source, base_path="other", mount_point="custom"
    )

    assert env.secret_manager == (source, "other", "custom")


def test_env_rejects_connection_options_with_secrets_manager(monkeypatch):
    class FakeSecretsManager:
        def __init__(self, **_kwargs):
            self.client = object()

        @classmethod
        def from_manager(cls, *_args, **_kwargs):
            raise AssertionError("manager view should not be created")

    monkeypatch.setattr("envex.env_wrapper.SecretsManager", FakeSecretsManager)

    with pytest.raises(ValueError, match="secrets_manager"):
        envex.Env(environ={}, secrets_manager=FakeSecretsManager(), url="https://vault")


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


def test_lookup_candidate_hook_supports_optional_instance_prefix():
    class PrefixedEnv(envex.Env):
        def __init__(self, *args, prefix="DJANGO_", **kwargs):
            self.prefix = prefix
            super().__init__(*args, **kwargs)

        def _lookup_candidates(self, var):
            if not self.prefix or var.startswith(self.prefix):
                return (var,)
            return var, f"{self.prefix}{var}"

    env = PrefixedEnv(
        environ={
            "DATABASE_URL": "raw",
            "DJANGO_DATABASE_URL": "prefixed",
            "DJANGO_DATABASE_PORT": "5432",
        }
    )

    assert env.get("DATABASE_URL") == "raw"
    assert env.get("DJANGO_DATABASE_URL") == "prefixed"
    assert env.int("DATABASE_PORT") == 5432
    assert env.is_set("DATABASE_PORT")

    assert env.pop("DATABASE_URL") == "raw"
    assert env.get("DATABASE_URL") == "prefixed"
    assert env.pop("DATABASE_URL") == "prefixed"
    assert env.pop("DATABASE_URL", "missing") == "missing"


def test_candidate_mutations_preserve_fallback_precedence():
    class PrefixedEnv(envex.Env):
        prefix = "DJANGO_"

        def _lookup_candidates(self, var):
            if var.startswith(self.prefix):
                return (var,)
            return var, f"{self.prefix}{var}"

    env = PrefixedEnv(environ={"DJANGO_DATABASE_URL": "prefixed"})

    assert env.setdefault("DATABASE_URL", "default") == "prefixed"
    assert "DATABASE_URL" not in env.env

    env["DATABASE_URL"] = "raw"
    del env["DATABASE_URL"]
    assert env.get("DATABASE_URL") == "prefixed"
    del env["DATABASE_URL"]
    assert not env.is_set("DATABASE_URL")


def test_candidate_write_target_can_prefer_a_prefix():
    class PrefixFirstEnv(envex.Env):
        prefix = "DJANGO_"

        def _lookup_candidates(self, var):
            if var.startswith(self.prefix):
                return (var,)
            return f"{self.prefix}{var}", var

    env = PrefixFirstEnv(environ={})

    assert env("DATABASE_URL", default="default") == "default"
    assert env.env == {"DJANGO_DATABASE_URL": "default"}


def test_pop_does_not_return_a_lower_priority_environment_value():
    class FakeSecretsManager:
        def get_secret(self, key, default=None):
            return {"DATABASE_URL": "vault"}.get(key, default)

    env = envex.Env(environ={"ENVEX_SOURCE": "vault", "DATABASE_URL": "env"})
    env.secret_manager = FakeSecretsManager()

    assert env.pop("DATABASE_URL", "missing") == "missing"
    assert env.env["DATABASE_URL"] == "env"


def test_is_set_does_not_reenter_a_legacy_get_override():
    class LegacyEnv(envex.Env):
        def get(self, var, default=None):
            return super().is_set(var)

    env = LegacyEnv(environ={"SETTING": "value"})

    assert env.is_set("SETTING")


def test_vault_settings_bypass_lookup_candidates(monkeypatch):
    calls = []

    class FakeSecretsManager:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            self.client = object()

    class PrefixedEnv(envex.Env):
        prefix = "DJANGO_"

        def _lookup_candidates(self, var):
            return var, f"{self.prefix}{var}"

    monkeypatch.setattr("envex.env_wrapper.SecretsManager", FakeSecretsManager)
    PrefixedEnv(
        environ={"VAULT_TOKEN": "token", "DJANGO_VAULT_SKIP_VERIFY": "true"},
        verify=None,
    )

    assert calls[-1]["verify"] is None


def test_env_source_uses_canonical_variable_for_vault_precedence(monkeypatch):
    class FakeSecretsManager:
        def __init__(self, **_kwargs):
            self.client = object()

        def get_secret(self, key, default=None):
            return {"SECRET": "vault"}.get(key, default)

    monkeypatch.setattr("envex.env_wrapper.SecretsManager", FakeSecretsManager)

    env = envex.Env(
        environ={"ENVEX_SOURCE": "vault", "SECRET": "env", "VAULT_TOKEN": "token"}
    )

    assert env.get("SECRET") == "vault"


@pytest.mark.parametrize("source", ["vault", " Vault ", "VAULT"])
def test_env_source_normalizes_vault_precedence(source, monkeypatch):
    class FakeSecretsManager:
        def __init__(self, **_kwargs):
            self.client = object()

        def get_secret(self, key, default=None):
            return {"SECRET": "vault"}.get(key, default)

    monkeypatch.setattr("envex.env_wrapper.SecretsManager", FakeSecretsManager)

    env = envex.Env(
        environ={"ENVEX_SOURCE": source, "SECRET": "env", "VAULT_TOKEN": "token"}
    )

    assert env.get("SECRET") == "vault"


@pytest.mark.parametrize("source", ["env", " ENV ", "ENV"])
def test_env_source_normalizes_env_precedence(source, monkeypatch):
    class FakeSecretsManager:
        def __init__(self, **_kwargs):
            pass

        def get_secret(self, key, default=None):
            return {"SECRET": "vault"}.get(key, default)

    monkeypatch.setattr("envex.env_wrapper.SecretsManager", FakeSecretsManager)

    env = envex.Env(environ={"ENVEX_SOURCE": source, "SECRET": "env"})

    assert env.get("SECRET") == "env"


def test_invalid_env_source_raises_value_error_before_vault_init(monkeypatch):
    class FakeSecretsManager:
        def __init__(self, **_kwargs):
            raise AssertionError("SecretsManager should not be initialized")

    monkeypatch.setattr("envex.env_wrapper.SecretsManager", FakeSecretsManager)

    with pytest.raises(ValueError, match="Invalid ENVEX_SOURCE value"):
        envex.Env(environ={"ENVEX_SOURCE": "treu"})


def test_env_list(monkeypatch):
    monkeypatch.setattr(envex.dot_env, "open_env", dotenv)
    env = envex.Env(readenv=True)

    assert_env_list_value(env, "ALISTOFIPS", ["::1", "127.0.0.1", "mydomain.com"])
    assert_env_list_value(
        env, "ALISTOFIPS", ["::1", "127.0.0.1", "mydomain.com"], via_call=True
    )

    expected_quoted_values = ["1", "two", "3", "four"]
    assert_env_list_value(env, "LISTOFQUOTEDVALUES", expected_quoted_values)
    assert_env_list_value(
        env, "LISTOFQUOTEDVALUES", expected_quoted_values, via_call=True
    )


def assert_env_list_value(env, key, expected, *, via_call=False):
    result = env(key, type=list) if via_call else env.list(key)
    assert isinstance(result, list)
    assert result == expected


def test_env_iter(monkeypatch):
    monkeypatch.setattr(envex.dot_env, "open_env", dotenv)
    env = envex.Env(readenv=True, update=False)

    assert list(env) == list(env.items())
    assert dict(env)["DATABASE_URL"] == (
        "postgresql://username:password@localhost/database_name"
    )


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

    env.set(values)
    env.export()
    for k, v in values.items():
        assert os.environ[k] == str(v)


def test_is_all_set_checks_remaining_args_after_nested_collection():
    env = envex.Env({"A": "1"}, environ={})

    assert not env.is_all_set(["A"], "B")

    env.set("B", "2")

    assert env.is_all_set(["A"], "B")


def test_is_any_set_checks_remaining_args_after_nested_collection():
    env = envex.Env({"A": "1"}, environ={})

    assert env.is_any_set(["missing"], "A")
    assert not env.is_any_set(["missing"], "also_missing")


def test_is_set_helpers_recurse_into_sequence_collections():
    env = envex.Env({"A": "1", "B": "2"}, environ={})

    assert env.is_all_set(("A", "B"))
    assert not env.is_all_set(("A", "missing"))
    assert env.is_any_set(("missing", "A"))
    assert not env.is_any_set(("missing", "also_missing"))


def test_is_set_helpers_do_not_consume_generators_as_nested_vars():
    env = envex.Env({"A": "1", "B": "2"}, environ={})

    assert not env.is_all_set(key for key in ["A", "B"])
    assert not env.is_any_set(key for key in ["missing", "B"])


def test_env_export_none_removes_process_env_without_keyerror(monkeypatch):
    monkeypatch.setenv("REMOVE_ME", "value")
    env = envex.Env({"REMOVE_ME": "value"}, environ={})

    env.export(REMOVE_ME=None)
    env.export(REMOVE_ME=None)

    assert "REMOVE_ME" not in env.env
    assert "REMOVE_ME" not in os.environ


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
    with pytest.raises(KeyError):
        env.check_var("UNDEFINEDVARIABLE")
    assert env.check_var(None) == ""


@pytest.mark.parametrize(
    ("initial", "default", "expected_result", "expected_env"),
    [
        ({}, 123, "123", {"var": "123"}),
        ({}, None, None, {}),
        ({"var": "value"}, None, "value", {"var": "value"}),
        ({"var": "abc"}, "def", "abc", {"var": "abc"}),
    ],
    ids=[
        "sets-value",
        "skips-none",
        "preserves-existing-with-none",
        "preserves-existing",
    ],
)
def test_setdefault(initial, default, expected_result, expected_env):
    env = envex.Env(initial, environ={})

    result = env.setdefault("var", default)

    assert result == expected_result
    assert env.env == expected_env


def test_set_none_unsets_existing_value():
    env = envex.Env({"var1": "value"}, environ={})

    env.set("var1", None)

    assert "var1" not in env.env


def test_set_dict_none_unsets_existing_value():
    env = envex.Env({"var1": "value", "var2": "keep"}, environ={})

    env.set({"var1": None, "var2": 123})

    assert "var1" not in env.env
    assert env.env["var2"] == "123"


@pytest.mark.parametrize(
    "selector",
    [
        pytest.param("plain", id="plain"),
        pytest.param("environment", id="environment"),
        pytest.param("file", id="file"),
    ],
)
def test_encrypted_stream_uses_password_selector(password, tmp_path, selector):
    environ = {}
    if selector == "environment":
        environ = {"TEST_PASSWORD": password}
        password_arg = "$TEST_PASSWORD"
    elif selector == "file":
        password_file = tmp_path / "password.txt"
        password_file.write_text(f"{password}\n")
        password_arg = f"@{password_file}"
    else:
        password_arg = password

    data = b"ONE=1\nARG2=two\nENABLED=true\n"
    stream = encrypt_data(io.BytesIO(data), password)
    env = envex.Env(stream, decrypt=True, password=password_arg, environ=environ)

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


@pytest.mark.parametrize(
    "selector",
    [
        pytest.param("plain", id="plain"),
        pytest.param("environment", id="environment"),
        pytest.param("file", id="file"),
    ],
)
def test_encrypted_env_file_uses_env_password_selector(password, tmp_path, selector):
    write_encrypted_env(tmp_path, password)
    environ = {"ENV_PASSWORD": password}
    if selector == "environment":
        environ = {"ENV_PASSWORD": "$TEST_PASSWORD", "TEST_PASSWORD": password}
    elif selector == "file":
        password_file = tmp_path / "password.txt"
        password_file.write_text(f"{password}\n")
        environ = {"ENV_PASSWORD": f"@{password_file}"}

    env = envex.Env(
        readenv=True,
        environ=environ,
        env_file=".env",
        search_path=tmp_path,
        update=False,
    )

    assert env("ONE") == "1"
    assert env("ARG2") == "two"
    assert env("ENABLED") == "true"


@pytest.mark.parametrize("source", ["env-file", "stream"])
def test_plaintext_fallback_with_env_password_is_not_corrupted(
    password, tmp_path, source
):
    data = "ONE=1\nARG2=two\nENABLED=true\n"
    if source == "env-file":
        env_file = tmp_path / ".env"
        env_file.write_text(data)
        env = envex.Env(
            readenv=True,
            environ={"ENV_PASSWORD": password},
            env_file=".env",
            search_path=tmp_path,
            update=False,
        )
    else:
        env = envex.Env(io.BytesIO(data.encode()), environ={"ENV_PASSWORD": password})

    assert env("ONE") == "1"
    assert env("ARG2") == "two"
    assert env("ENABLED") == "true"


@pytest.mark.parametrize("key", ["SECG_KEY", "SECF_KEY"])
@pytest.mark.parametrize("source", ["env-file", "stream"])
@pytest.mark.parametrize("prefix", ["", "# comment\n\n"])
def test_plaintext_magic_prefix_key_with_env_password_is_not_rejected(
    password, tmp_path, key, source, prefix
):
    data = f"{prefix}{key}=value\n"
    if source == "env-file":
        env_file = tmp_path / ".env"
        env_file.write_text(data)
        env = envex.Env(
            readenv=True,
            environ={"ENV_PASSWORD": password},
            env_file=".env",
            search_path=tmp_path,
            update=False,
        )
    else:
        env = envex.Env(io.BytesIO(data.encode()), environ={"ENV_PASSWORD": password})

    assert env[key] == "value"


def test_encrypted_stream_wrong_password_raises_decrypt_error(password, monkeypatch):
    def token_bytes(size):
        if size == env_crypto.SALT_LENGTH:
            return b"=\n" + b"s" * (size - 2)
        if size == env_crypto.GCM_NONCE_LENGTH:
            return b"n" * size
        return b"x" * size

    monkeypatch.setattr(env_crypto.secrets, "token_bytes", token_bytes)
    stream = encrypt_data(io.BytesIO(b"ONE=1\n"), password)
    assert stream.getvalue().startswith(b"SECG=\n")

    with pytest.raises(DecryptError):
        envex.Env(stream, decrypt=True, password="wrong-password")


def test_legacy_encrypted_stream_without_opt_in_raises_decrypt_error(password):
    stream = io.BytesIO(env_crypto.MAGIC_BYTES + b"legacy-data")

    with pytest.raises(DecryptError, match="Legacy AES-CBC data requires explicit"):
        envex.Env(stream, decrypt=True, password=password)


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


def test_encrypted_stream_invalid_plaintext_fallback_decode_error(password):
    # 0xff/0xfe/0xfa are invalid leading bytes in UTF-8.
    invalid_data = b"\xff\xfe\xfa=not-utf-8\n"

    with pytest.raises(UnicodeDecodeError):
        envex.Env(io.BytesIO(invalid_data), decrypt=True, password=password)
