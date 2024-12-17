import pytest

from envex import Env


@pytest.mark.integration
def test_vault_secrets(vault):
    env = Env(
        url=vault.get_connection_url(),
        base_path="test",
        token=vault.root_token,
        engine="kv",
    )
    assert env is not None
    assert env.secret_manager is not None
    assert env.secret_manager.client is not None

    client = env.secret_manager.client
    assert client.is_authenticated()

    # test data set up in the vault fixture
    assert env["ABC"] == "123"
    assert env["DEF"] == "456"
    # other environment variables that have a very high chance of being set
    assert env["PATH"] is not None
    assert env["HOME"] is not None

    assert env.get("XY_ZZY") is None

    env.secret_manager.set_secret("XY_ZZY", "789")
    assert env["XY_ZZY"] == "789"

    secrets = env.secret_manager.list_secrets()
    assert secrets is not None
    assert "ABC" in secrets
    assert "DEF" in secrets
    assert "XY_ZZY" in secrets
