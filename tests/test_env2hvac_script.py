import logging

import pytest

from envex.scripts import env2hvac


class NoopSecretsManager:
    def __init__(self, **kwargs):
        pass


def install_fake_secrets_manager(monkeypatch, fail_write=False):
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
            self.writes = []
            self.unseal_calls = []
            self.seal_calls = 0
            instances.append(self)

        @staticmethod
        def join(*args, sep="/"):
            return sep.join([a.strip(sep) for a in args if a])

        def set_secrets(self, path="", values=None):
            if fail_write:
                raise RuntimeError("write failed")
            self.writes.append((path, dict(values or {})))

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


def test_handler_skips_working_dir_values(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("PUBLIC=hello\n")

    instances = install_fake_secrets_manager(monkeypatch)

    env2hvac.handler([str(env_file)], namespace="myapp", environ="prod")

    written_values = instances[0].writes[0][1]
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
