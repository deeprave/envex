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
    monkeypatch.setattr(seal.hvac, "Client", FakeClient)
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
    monkeypatch.setattr(seal.hvac, "Client", FakeClient)
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
