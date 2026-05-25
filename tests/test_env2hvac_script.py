import logging

import pytest

from envex.scripts import env2hvac


class NoopSecretsManager:
    def __init__(self, **kwargs):
        pass


def install_fake_secrets_manager(monkeypatch, fail_write=False, existing_values=None):
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
