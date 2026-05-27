import logging
import sys

import pytest

from envex.scripts import env2hvac

Forbidden = type("Forbidden", (Exception,), {"__module__": "hvac.exceptions"})


class NoopSecretsManager:
    def __init__(self, **kwargs):
        pass


def test_main_supports_console_script_help(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["env2hvac", "--help"])

    with pytest.raises(SystemExit) as exc_info:
        env2hvac.main()

    assert exc_info.value.code == 0
    assert "usage:" in capsys.readouterr().out


@pytest.mark.parametrize(
    "verify_args",
    [
        ["--noverify", "--cacert", "/tmp/ca.pem"],
        ["--cacert", "/tmp/ca.pem", "--noverify"],
    ],
)
def test_main_rejects_conflicting_verify_options(
    monkeypatch, tmp_path, capsys, verify_args
):
    env_file = tmp_path / ".env"
    env_file.write_text("PUBLIC=hello\n")

    def fail_handler(*_args, **_kwargs):
        raise AssertionError("handler should not be called")

    monkeypatch.setattr(env2hvac, "handler", fail_handler)
    monkeypatch.setattr(sys, "argv", ["env2hvac", *verify_args, str(env_file)])

    with pytest.raises(SystemExit) as exc_info:
        env2hvac.main()

    assert exc_info.value.code == 2
    assert "not allowed with argument" in capsys.readouterr().err


def install_fake_secrets_manager(
    monkeypatch, fail_write=False, forbid_read=False, existing_values=None
):
    instances = []

    class FakeClient:
        def __init__(self):
            self.seal_status = {"sealed": False}

        def is_authenticated(self):
            return True

    class FakeSecretsManager:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.client = FakeClient()
            self.secrets = dict(existing_values or {})
            self.get_calls = []
            self.writes = []
            self.unseal_calls = []
            self.seal_calls = 0
            instances.append(self)

        @staticmethod
        def join(*args, sep="/"):
            return sep.join([a.strip(sep) for a in args if a])

        def get_secrets(self, path=""):
            self.get_calls.append(path)
            if forbid_read:
                raise Forbidden("permission denied")
            return self.secrets

        def set_secrets(self, path="", values=None):
            if fail_write:
                raise RuntimeError("write failed")
            self.secrets |= dict(values or {})
            self.writes.append((path, dict(self.secrets)))

        def unseal(self, keys, root_token):
            self.unseal_calls.append((keys, root_token))

        def seal(self):
            self.seal_calls += 1

    monkeypatch.setattr(env2hvac, "SecretsManager", FakeSecretsManager)
    monkeypatch.setattr("envex.env_wrapper.SecretsManager", NoopSecretsManager)
    return instances


def test_handler_writes_env_values_to_secret_manager(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("PUBLIC=hello\nSECRET=shh\n")

    instances = install_fake_secrets_manager(monkeypatch)

    env2hvac.handler([str(env_file)], namespace="myapp", environ="prod")

    assert instances[0].writes == [
        (
            "myapp/prod",
            {
                "PUBLIC": "hello",
                "SECRET": "shh",
            },
        )
    ]
    assert instances[0].get_calls == ["myapp/prod"]


def test_handler_passes_omitted_verify_as_vault_default(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("PUBLIC=hello\n")

    instances = install_fake_secrets_manager(monkeypatch)

    env2hvac.handler([str(env_file)], namespace="myapp", environ="prod")

    assert instances[0].kwargs["verify"] is None


def test_handler_writes_when_existing_secret_read_is_forbidden(
    tmp_path, monkeypatch, caplog
):
    env_file = tmp_path / ".env"
    env_file.write_text("PUBLIC=hello\n")

    instances = install_fake_secrets_manager(monkeypatch, forbid_read=True)
    caplog.set_level(logging.WARNING)

    env2hvac.handler([str(env_file)], namespace="myapp", environ="prod")

    assert instances[0].get_calls == ["myapp/prod"]
    assert instances[0].writes == [("myapp/prod", {"PUBLIC": "hello"})]
    assert "importing without preserving existing values" in caplog.text


def test_handler_preserves_existing_secret_values(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("PUBLIC=updated\n")

    instances = install_fake_secrets_manager(
        monkeypatch, existing_values={"EXISTING": "keep", "PUBLIC": "old"}
    )

    env2hvac.handler([str(env_file)], namespace="myapp", environ="prod")

    assert instances[0].writes == [
        (
            "myapp/prod",
            {
                "EXISTING": "keep",
                "PUBLIC": "updated",
            },
        )
    ]


def test_handler_skips_working_dir_values(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("CWD=/from/file/cwd\nPWD=/from/file/pwd\nPUBLIC=hello\n")

    instances = install_fake_secrets_manager(monkeypatch)

    env2hvac.handler([str(env_file)], namespace="myapp", environ="prod")

    written_values = instances[0].writes[0][1]
    assert written_values["PUBLIC"] == "hello"
    assert "CWD" not in written_values
    assert "PWD" not in written_values


def test_handler_logs_success_after_write(tmp_path, monkeypatch, caplog):
    env_file = tmp_path / ".env"
    env_file.write_text("PUBLIC=hello\n")

    install_fake_secrets_manager(monkeypatch, fail_write=True)
    caplog.set_level(logging.INFO)

    with pytest.raises(RuntimeError, match="write failed"):
        env2hvac.handler([str(env_file)], namespace="myapp", environ="prod")

    assert "Added or updated" not in caplog.text


def test_handler_submits_unseal_keys_before_authentication_check(
    tmp_path, monkeypatch, caplog
):
    env_file = tmp_path / ".env"
    env_file.write_text("PUBLIC=hello\n")
    events = []
    instances = []

    class FakeSecretsManager:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.unseal_calls = []
            instances.append(self)

        @staticmethod
        def join(*args, sep="/"):
            return sep.join([a.strip(sep) for a in args if a])

        @property
        def client(self):
            events.append("client")
            return None

        def unseal(self, keys, root_token):
            events.append("unseal")
            self.unseal_calls.append((keys, root_token))

    monkeypatch.setattr(env2hvac, "SecretsManager", FakeSecretsManager)
    caplog.set_level(logging.CRITICAL)

    with pytest.raises(SystemExit) as exc_info:
        env2hvac.handler(
            [str(env_file)],
            token="root-token",
            unseal="key-1,key-2",
            namespace="myapp",
            environ="prod",
        )

    assert exc_info.value.code == 1
    assert instances[0].unseal_calls == [(["key-1", "key-2"], "root-token")]
    assert events == ["unseal", "client"]
    assert "Can't connect or authenticate with Vault" in caplog.text


def test_handler_fails_when_explicit_input_file_is_missing(tmp_path, monkeypatch, caplog):
    missing_file = tmp_path / "missing.env"
    instances = install_fake_secrets_manager(monkeypatch)
    caplog.set_level(logging.CRITICAL)

    with pytest.raises(SystemExit) as exc_info:
        env2hvac.handler([str(missing_file)], namespace="myapp", environ="prod")

    assert exc_info.value.code == 1
    assert instances == []
    assert f"{missing_file}: input file does not exist" in caplog.text


def test_handler_validates_all_input_files_before_writing(tmp_path, monkeypatch, caplog):
    env_file = tmp_path / ".env"
    env_file.write_text("PUBLIC=hello\n")
    missing_file = tmp_path / "missing.env"
    instances = install_fake_secrets_manager(monkeypatch)
    caplog.set_level(logging.CRITICAL)

    with pytest.raises(SystemExit) as exc_info:
        env2hvac.handler(
            [str(env_file), str(missing_file)], namespace="myapp", environ="prod"
        )

    assert exc_info.value.code == 1
    assert instances == []
    assert f"{missing_file}: input file does not exist" in caplog.text


def test_handler_fails_when_explicit_input_file_is_unreadable(
    tmp_path, monkeypatch, caplog
):
    env_file = tmp_path / ".env"
    env_file.write_text("PUBLIC=hello\n")
    instances = install_fake_secrets_manager(monkeypatch)
    real_open = open

    def fake_open(path, *args, **kwargs):
        if path == str(env_file):
            raise PermissionError(13, "permission denied", str(env_file))
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(env2hvac, "open", fake_open, raising=False)
    caplog.set_level(logging.CRITICAL)

    with pytest.raises(SystemExit) as exc_info:
        env2hvac.handler([str(env_file)], namespace="myapp", environ="prod")

    assert exc_info.value.code == 1
    assert instances == []
    assert f"{env_file}: input file is not readable" in caplog.text
