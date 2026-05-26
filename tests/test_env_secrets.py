import pytest

from envex import Env


@pytest.mark.integration
@pytest.mark.vault
def test_vault_secrets(vault):
    env = Env(
        url=vault.get_connection_url(),
        base_path="test",
        token=vault.root_token,
        engine="kv",
    )
    client = env.secret_manager.client
    assert client.is_authenticated()

    assert env["ABC"] == "123"
    assert env["DEF"] == "456"

    assert env.get("XY_ZZY") is None

    env.secret_manager.set_secret("XY_ZZY", "789")
    assert env["XY_ZZY"] == "789"

    assert set(env.secret_manager.list_secrets()) == {"ABC", "DEF", "XY_ZZY"}
