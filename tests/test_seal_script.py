import sys

import pytest

from envex.scripts import seal


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
    class FakeClient:
        calls = []

        def __init__(self, **kwargs):
            self.calls.append(kwargs)
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

    assert FakeClient.calls[-1]["verify"] is True
    assert capsys.readouterr().out.strip() == (
        f"Vault Status: {expected_status} type=shamir shares=3/5"
    )


def test_seal_expands_cacert_path(monkeypatch, capsys):
    class FakeClient:
        calls = []

        def __init__(self, **kwargs):
            self.calls.append(kwargs)
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

    assert FakeClient.calls[-1]["verify"] == "/tmp/envex-home/ca.pem"
    assert "Vault Status: Unsealed" in capsys.readouterr().out
