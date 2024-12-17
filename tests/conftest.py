# -*- coding: utf-8 -*-
import pytest

try:
    import hvac
    from hvac.exceptions import InvalidRequest

    use_hvac = True

    from testcontainers.vault import VaultContainer

    container_name = "hashicorp/vault:1.14.4"

    test_data = {
        "ABC": "123",
        "DEF": "456",
    }

    @pytest.fixture(scope="session")
    def vault(request) -> VaultContainer:
        vault = VaultContainer(container_name)

        vault.start()
        connection_url = vault.get_connection_url()
        client = hvac.Client(url=connection_url, token=vault.root_token)
        assert client.is_authenticated()

        try:
            client.sys.enable_secrets_engine("kv", path="secret")
        except InvalidRequest as e:
            if "path is already in use at" not in str(e):
                raise

        client.write_data("secret/data/test", data=dict(data=test_data))

        def vault_stop():
            vault.stop()

        request.addfinalizer(vault_stop)
        return vault

    @pytest.fixture(scope="session")
    def vault_client(vault) -> hvac.Client:
        return hvac.Client(url=vault.get_connection_url(), token=vault.root_token)

except ImportError:
    use_hvac = False


def pytest_configure(config):
    config.addinivalue_line("markers", "vault: vault module is available")
    # Register the slow marker
    pytest.mark.vault = pytest.mark.skipif(
        not use_hvac, reason="Test skipped because hvac_module is not available"
    )
