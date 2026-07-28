# -*- coding: utf-8 -*-
from types import SimpleNamespace

import hvac
import pytest
from hvac.exceptions import InvalidPath

from envex.env_hvac import SecretsManager, read_pem

BASE_URL = "http://vault.example.com:8200"
TOKEN = "s.1234567890abcdef"
CERT = ("path/to/cert.pem", "path/to/key.pem")
BASE_PATH = "base/path"


class FakeKvV2:
    def __init__(self, initial=None):
        self.store = dict(initial or {})
        self.read_calls = []
        self.write_calls = []
        self.delete_calls = []

    def read_secret_version(self, path, version=None, mount_point="secret", **kwargs):
        self.read_calls.append(
            {
                "path": path,
                "version": version,
                "mount_point": mount_point,
                "kwargs": kwargs,
            }
        )
        secret = self.store.get((mount_point, path))
        return {"data": {"data": dict(secret)}} if secret is not None else {}

    def create_or_update_secret(self, path, secret, cas=None, mount_point="secret"):
        self.write_calls.append(
            {
                "path": path,
                "secret": dict(secret),
                "cas": cas,
                "mount_point": mount_point,
            }
        )
        self.store[(mount_point, path)] = dict(secret)

    def delete_metadata_and_all_versions(self, path, mount_point="secret"):
        self.delete_calls.append({"path": path, "mount_point": mount_point})
        self.store.pop((mount_point, path), None)


class FakeClient:
    def __init__(self, kv2=None, mounts=None, authenticated=True):
        self.authenticated = authenticated
        self.seal_status = {"sealed": False}
        self.secrets = SimpleNamespace(kv=SimpleNamespace(v2=kv2 or FakeKvV2()))
        self._mounts = mounts or {"secret/": {"type": "kv"}}

    def is_authenticated(self):
        return self.authenticated

    @property
    def sys(self):
        return SimpleNamespace(
            list_mounted_secrets_engines=lambda: {"data": self._mounts},
            seal=self._seal,
            submit_unseal_keys=self._submit_unseal_keys,
        )

    def _seal(self):
        self.seal_status["sealed"] = True
        return self.seal_status

    def _submit_unseal_keys(self, keys, root_token):
        self.seal_status["sealed"] = False
        return self.seal_status


def make_manager(base_path="", mount_point="secret", kv2=None):
    manager = SecretsManager.__new__(SecretsManager)
    manager._client = FakeClient(kv2=kv2)
    manager.hvac_disabled = False
    manager._engine = None
    manager._mount_point = mount_point
    manager._base_path = SecretsManager.join(base_path)
    manager._secrets = {}
    return manager


def install_fake_hvac_client(monkeypatch, mounts=None):
    instances = []

    class InitClient(FakeClient):
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            instances.append(self)
            super().__init__(mounts=mounts)

    monkeypatch.setattr(hvac, "Client", InitClient)
    return instances


@pytest.mark.parametrize(
    ("base_path", "engine", "mount_point", "mounts", "expected_base", "expected_mount"),
    [
        (BASE_PATH, None, "secret", None, BASE_PATH, "secret"),
        (None, None, None, None, "", "secret"),
        (
            BASE_PATH,
            "kv",
            None,
            {"custom/": {"type": "kv"}},
            BASE_PATH,
            "custom",
        ),
    ],
)
def test_secrets_manager_initialization_uses_logical_paths(
    base_path,
    engine,
    mount_point,
    mounts,
    expected_base,
    expected_mount,
    monkeypatch,
):
    monkeypatch.delenv("VAULT_PATH", raising=False)
    instances = install_fake_hvac_client(monkeypatch, mounts=mounts)

    manager = SecretsManager(
        url=BASE_URL,
        token=TOKEN,
        cert=CERT,
        verify=True,
        base_path=base_path,
        engine=engine,
        mount_point=mount_point,
    )

    assert instances[0].kwargs["cert"] == CERT
    assert manager.base_path == expected_base
    assert manager.mount_point == expected_mount
    assert manager.path("app/prod") == SecretsManager.join(expected_base, "app/prod")


def test_vault_capath_is_used_when_cacert_is_absent(tmp_path, monkeypatch):
    ca_dir = tmp_path / "ca-dir"
    ca_dir.mkdir()
    monkeypatch.delenv("VAULT_CACERT", raising=False)
    monkeypatch.setenv("VAULT_CAPATH", ca_dir.as_posix())
    instances = install_fake_hvac_client(monkeypatch)

    SecretsManager()

    assert instances[0].kwargs["verify"] == ca_dir.as_posix()


def test_vault_cacert_takes_precedence_over_vault_capath(tmp_path, monkeypatch):
    ca_cert = tmp_path / "ca.pem"
    ca_cert.write_text("certificate bundle")
    ca_dir = tmp_path / "ca-dir"
    ca_dir.mkdir()
    monkeypatch.setenv("VAULT_CACERT", ca_cert.as_posix())
    monkeypatch.setenv("VAULT_CAPATH", ca_dir.as_posix())
    instances = install_fake_hvac_client(monkeypatch)

    SecretsManager()

    assert instances[0].kwargs["verify"] == ca_cert.as_posix()


def test_vault_capath_file_is_used_as_ca_bundle(tmp_path, monkeypatch):
    ca_file = tmp_path / "ca-file.pem"
    ca_file.write_text("not a directory")
    monkeypatch.delenv("VAULT_CACERT", raising=False)
    monkeypatch.setenv("VAULT_CAPATH", ca_file.as_posix())
    instances = install_fake_hvac_client(monkeypatch)

    SecretsManager()

    assert instances[0].kwargs["verify"] == ca_file.as_posix()


def test_invalid_vault_capath_raises_value_error(tmp_path, monkeypatch):
    missing_path = tmp_path / "missing-ca-path"
    monkeypatch.delenv("VAULT_CACERT", raising=False)
    monkeypatch.setenv("VAULT_CAPATH", missing_path.as_posix())
    install_fake_hvac_client(monkeypatch)

    with pytest.raises(ValueError, match=f"VAULT_CAPATH={missing_path.as_posix()!r}"):
        SecretsManager()


@pytest.mark.parametrize("verify", [True, False, "/explicit/ca.pem"])
def test_explicit_verify_overrides_vault_capath(verify, tmp_path, monkeypatch):
    monkeypatch.setenv("VAULT_CACERT", (tmp_path / "env-ca.pem").as_posix())
    monkeypatch.setenv("VAULT_CAPATH", (tmp_path / "env-ca-dir").as_posix())
    instances = install_fake_hvac_client(monkeypatch)

    SecretsManager(verify=verify)

    assert instances[0].kwargs["verify"] == verify


def test_initialization_failure_is_instance_local(monkeypatch):
    calls = 0

    def fake_client(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary import/auth setup failure")
        return FakeClient()

    monkeypatch.setattr(hvac, "Client", fake_client)

    failed = SecretsManager()
    working = SecretsManager()

    assert failed.hvac_disabled
    assert failed.client is None
    assert not working.hvac_disabled
    assert working.client is working._client


@pytest.mark.parametrize(
    ("env_name", "contents", "is_key"),
    [
        ("VAULT_CLIENT_CERT", "-----BEGIN CERTIFICATE-----\n", False),
        ("VAULT_CLIENT_KEY", "not a real PRIVATE KEY\n", True),
    ],
)
def test_read_pem_returns_valid_file_path(
    tmp_path, monkeypatch, env_name, contents, is_key
):
    pem_file = tmp_path / f"{env_name}.pem"
    pem_file.write_text(contents)
    monkeypatch.setenv(env_name, pem_file.as_posix())

    assert read_pem(env_name, is_key=is_key) == pem_file.as_posix()


def test_read_pem_rejects_inline_or_invalid_pem(tmp_path, monkeypatch):
    pem_file = tmp_path / "invalid.pem"
    pem_file.write_text("not a certificate")
    monkeypatch.setenv("INLINE_PEM", "-----BEGIN CERTIFICATE-----\n")
    monkeypatch.setenv("INVALID_PEM", pem_file.as_posix())

    assert read_pem("INLINE_PEM") is None
    assert read_pem("INVALID_PEM") is None


def test_client_certificate_env_vars_are_passed_as_paths(tmp_path, monkeypatch):
    cert = tmp_path / "client.pem"
    key = tmp_path / "client-key.pem"
    cert.write_text("-----BEGIN CERTIFICATE-----\n")
    key.write_text("not a real PRIVATE KEY\n")
    monkeypatch.setenv("VAULT_CLIENT_CERT", cert.as_posix())
    monkeypatch.setenv("VAULT_CLIENT_KEY", key.as_posix())
    instances = install_fake_hvac_client(monkeypatch)

    SecretsManager()

    assert instances[0].kwargs["cert"] == (cert.as_posix(), key.as_posix())


def test_combined_client_certificate_file_is_passed_as_single_path(
    tmp_path, monkeypatch, caplog
):
    cert = tmp_path / "client-combined.pem"
    cert.write_text("-----BEGIN CERTIFICATE-----\nnot a real PRIVATE KEY\n")
    monkeypatch.setenv("VAULT_CLIENT_CERT", cert.as_posix())
    monkeypatch.delenv("VAULT_CLIENT_KEY", raising=False)
    instances = install_fake_hvac_client(monkeypatch)

    SecretsManager()

    assert instances[0].kwargs["cert"] == cert.as_posix()
    assert "Ignoring incomplete Vault client certificate configuration" not in caplog.text


def test_client_certificate_env_vars_require_cert_and_key(tmp_path, monkeypatch, caplog):
    cert = tmp_path / "client.pem"
    cert.write_text("-----BEGIN CERTIFICATE-----\n")
    monkeypatch.setenv("VAULT_CLIENT_CERT", cert.as_posix())
    monkeypatch.delenv("VAULT_CLIENT_KEY", raising=False)
    instances = install_fake_hvac_client(monkeypatch)

    SecretsManager()

    assert instances[0].kwargs["cert"] is None
    assert "Ignoring incomplete Vault client certificate configuration" in caplog.text


def test_get_secrets_uses_kv_v2_read_with_mount_and_logical_path():
    kv2 = FakeKvV2({("custom", "base/app"): {"secret_key": "secret_value"}})
    manager = make_manager(base_path="base", mount_point="custom", kv2=kv2)

    assert manager.get_secrets("app") == {"secret_key": "secret_value"}

    assert kv2.read_calls == [
        {
            "path": "base/app",
            "version": None,
            "mount_point": "custom",
            "kwargs": {"raise_on_deleted_version": True},
        }
    ]


def test_secret_snapshots_do_not_expose_the_internal_cache():
    kv2 = FakeKvV2({("secret", "base/app"): {"KEY": "original"}})
    manager = make_manager(base_path="base", kv2=kv2)

    fetched = manager.get_secrets("app")
    fetched["KEY"] = "changed"

    assert manager._cached("app") == {"KEY": "original"}
    manager._secrets = {"DEFAULT": "original"}
    snapshot = manager.secrets
    snapshot["DEFAULT"] = "changed"
    assert manager._secrets == {"DEFAULT": "original"}


def test_get_secrets_treats_missing_kv_path_as_empty():
    class MissingKvV2(FakeKvV2):
        def read_secret_version(self, path, version=None, mount_point="secret", **kwargs):
            super().read_secret_version(path, version, mount_point, **kwargs)
            raise InvalidPath("missing secret")

    kv2 = MissingKvV2()
    manager = make_manager(kv2=kv2)
    manager._secrets = {"OLD": "stale"}

    assert manager.get_secrets("missing") == {}


def test_set_secrets_uses_kv_v2_write_with_mount_and_logical_path():
    kv2 = FakeKvV2({("custom", "base/app"): {"EXISTING": "keep"}})
    manager = make_manager(base_path="base", mount_point="custom", kv2=kv2)

    manager.set_secrets("app", values={"PUBLIC": "hello"})

    assert kv2.write_calls == [
        {
            "path": "base/app",
            "secret": {"EXISTING": "keep", "PUBLIC": "hello"},
            "cas": None,
            "mount_point": "custom",
        }
    ]
    assert kv2.read_calls == [
        {
            "path": "base/app",
            "version": None,
            "mount_point": "custom",
            "kwargs": {"raise_on_deleted_version": True},
        }
    ]


def test_set_secrets_with_empty_values_is_not_destructive():
    kv2 = FakeKvV2({("secret", "base/app"): {"PUBLIC": "hello"}})
    manager = make_manager(base_path="base", kv2=kv2)
    manager._secrets = {}

    manager.set_secrets("app", values={})

    assert kv2.write_calls == []
    assert kv2.delete_calls == []
    assert kv2.store == {("secret", "base/app"): {"PUBLIC": "hello"}}


def test_delete_secrets_uses_kv_v2_metadata_delete():
    kv2 = FakeKvV2({("secret", "base/app"): {"PUBLIC": "hello"}})
    manager = make_manager(base_path="base", kv2=kv2)
    manager._secrets = {"PUBLIC": "hello"}

    manager.delete_secrets("app")

    assert kv2.delete_calls == [{"path": "base/app", "mount_point": "secret"}]
    assert manager.secrets == {"PUBLIC": "hello"}


def test_cache_entries_are_isolated_by_path_and_shared_by_manager_views():
    kv2 = FakeKvV2(
        {
            ("secret", "one"): {"VALUE": "one"},
            ("secret", "two"): {"VALUE": "two"},
        }
    )
    source = make_manager(base_path="one", kv2=kv2)
    view = SecretsManager.from_manager(source, base_path="two")

    assert source.get_secrets() == {"VALUE": "one"}
    assert view.get_secrets() == {"VALUE": "two"}
    assert source.secrets == {"VALUE": "one"}
    assert view.secrets == {"VALUE": "two"}


def test_manager_view_requires_authenticated_source():
    source = make_manager()
    source._client.authenticated = False

    with pytest.raises(ValueError, match="authenticated"):
        SecretsManager.from_manager(source)


def test_get_set_list_and_delete_secret():
    kv2 = FakeKvV2({("secret", "base"): {"ABC": "123", "DEF": "456"}})
    manager = make_manager(base_path="base", kv2=kv2)

    assert manager.get_secret("ABC") == "123"

    manager.set_secret("XYZ", "789")
    assert manager.get_secret("XYZ") == "789"
    assert list(manager.list_secrets()) == ["ABC", "DEF", "XYZ"]
    assert kv2.write_calls[-1] == {
        "path": "base",
        "secret": {"ABC": "123", "DEF": "456", "XYZ": "789"},
        "cas": None,
        "mount_point": "secret",
    }

    manager.delete_secret("XYZ")
    assert "XYZ" not in manager.secrets
    assert kv2.write_calls[-1]["secret"] == {"ABC": "123", "DEF": "456"}


def test_delete_secret_removes_empty_vault_document():
    kv2 = FakeKvV2({("secret", "base"): {"ABC": "123"}})
    manager = make_manager(base_path="base", kv2=kv2)

    assert manager.get_secret("ABC") == "123"

    manager.delete_secret("ABC")

    assert manager.secrets == {}
    assert kv2.delete_calls == [{"path": "base", "mount_point": "secret"}]


def test_seal_unseal():
    manager = make_manager()

    manager.seal()
    assert manager.sealed
    manager.unseal([], None)
    assert not manager.sealed


def test_sealed_reads_raw_client_when_authentication_fails():
    manager = make_manager()
    manager._client.authenticated = False
    manager._client.seal_status["sealed"] = True

    assert manager.client is None
    assert manager.sealed is True


def test_seal_uses_raw_client_when_authentication_fails():
    manager = make_manager()
    manager._client.authenticated = False
    manager._client.seal_status["sealed"] = False

    assert manager.client is None
    assert manager.seal() is True
    assert manager.sealed is True


def test_unseal_uses_raw_client_when_authentication_fails():
    manager = make_manager()
    manager._client.authenticated = False
    manager._client.seal_status["sealed"] = True

    assert manager.client is None
    assert manager.unseal(["key-1", "key-2"], "root-token") is True
    assert manager.sealed is False
