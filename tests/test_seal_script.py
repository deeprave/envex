import builtins
import sys

import pytest

from envex.scripts import seal


def test_main_supports_console_script_help(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["seal", "--help"])

    with pytest.raises(SystemExit) as exc_info:
        seal.main()

    assert exc_info.value.code == 0
    assert "usage:" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("sealed", "expected_status"),
    [
        (True, "Sealed"),
        (False, "Unsealed"),
    ],
)
def test_seal_status_uses_boolean_value_and_default_verify(
    sealed, expected_status, monkeypatch, capsys
):
    calls = []

    class FakeClient:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            self.seal_status = {
                "sealed": sealed,
                "type": "shamir",
                "t": 3,
                "n": 5,
            }

    monkeypatch.delenv("VAULT_CACERT", raising=False)
    monkeypatch.delenv("VAULT_CAPATH", raising=False)
    monkeypatch.setattr(seal, "_create_client", lambda **kwargs: FakeClient(**kwargs))
    monkeypatch.setattr(
        sys, "argv", ["seal", "--address", "http://vault.local", "--token", "token"]
    )

    seal.main()

    assert calls[-1]["verify"] is True
    assert capsys.readouterr().out.strip() == (
        f"Vault Status: {expected_status} type=shamir shares=3/5"
    )


def test_seal_expands_cacert_path(monkeypatch, capsys):
    calls = []

    class FakeClient:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            self.seal_status = {
                "sealed": False,
                "type": "shamir",
                "t": 3,
                "n": 5,
            }

    monkeypatch.setenv("HOME", "/tmp/envex-home")
    monkeypatch.setattr(seal, "_create_client", lambda **kwargs: FakeClient(**kwargs))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "seal",
            "--address",
            "http://vault.local",
            "--token",
            "token",
            "--cacert",
            "~/ca.pem",
        ],
    )

    seal.main()

    assert calls[-1]["verify"] == "/tmp/envex-home/ca.pem"
    assert "Vault Status: Unsealed" in capsys.readouterr().out


def test_seal_uses_vault_capath_default(monkeypatch, tmp_path, capsys):
    calls = []
    ca_dir = tmp_path / "ca-dir"
    ca_dir.mkdir()

    class FakeClient:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            self.seal_status = {
                "sealed": False,
                "type": "shamir",
                "t": 3,
                "n": 5,
            }

    monkeypatch.delenv("VAULT_CACERT", raising=False)
    monkeypatch.setenv("VAULT_CAPATH", ca_dir.as_posix())
    monkeypatch.setattr(seal, "_create_client", lambda **kwargs: FakeClient(**kwargs))
    monkeypatch.setattr(
        sys, "argv", ["seal", "--address", "http://vault.local", "--token", "token"]
    )

    seal.main()

    assert calls[-1]["verify"] == ca_dir.as_posix()
    assert "Vault Status: Unsealed" in capsys.readouterr().out


def test_seal_invalid_vault_capath_exits_nonzero(monkeypatch, tmp_path, caplog):
    missing_path = tmp_path / "missing-ca-path"
    monkeypatch.delenv("VAULT_CACERT", raising=False)
    monkeypatch.setenv("VAULT_CAPATH", missing_path.as_posix())
    monkeypatch.setattr(
        sys, "argv", ["seal", "--address", "http://vault.local", "--token", "token"]
    )
    caplog.set_level("ERROR")

    with pytest.raises(SystemExit) as exc_info:
        seal.main()

    assert exc_info.value.code == 1
    assert f"VAULT_CAPATH={missing_path.as_posix()!r}" in caplog.text


def test_seal_help_does_not_require_hvac(monkeypatch, capsys):
    real_import = builtins.__import__

    def import_without_hvac(name, *args, **kwargs):
        if name == "hvac":
            raise ModuleNotFoundError("No module named 'hvac'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_hvac)
    monkeypatch.setattr(sys, "argv", ["seal", "--help"])

    with pytest.raises(SystemExit) as exc_info:
        seal.main()

    assert exc_info.value.code == 0
    assert "usage:" in capsys.readouterr().out


def test_seal_operation_without_hvac_exits_nonzero(monkeypatch, caplog):
    real_import = builtins.__import__

    def import_without_hvac(name, *args, **kwargs):
        if name == "hvac":
            raise ModuleNotFoundError("No module named 'hvac'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_hvac)
    monkeypatch.setattr(
        sys, "argv", ["seal", "--address", "http://vault.local", "--token", "token"]
    )
    caplog.set_level("ERROR")

    with pytest.raises(SystemExit) as exc_info:
        seal.main()

    assert exc_info.value.code == 1
    assert "hvac is required to operate the seal command" in caplog.text
    assert "RuntimeError:" not in caplog.text
