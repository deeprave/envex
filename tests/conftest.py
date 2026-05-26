# -*- coding: utf-8 -*-
import pytest

try:
    import hvac
    from hvac.exceptions import InvalidRequest
    from testcontainers.core.container import DockerContainer
    from testcontainers.core.wait_strategies import HttpWaitStrategy

    use_hvac = True

    container_name = "hashicorp/vault:1.14.4"

    test_data = {
        "ABC": "123",
        "DEF": "456",
    }

    class VaultContainer(DockerContainer):
        def __init__(
            self,
            image: str = container_name,
            port: int = 8200,
            root_token: str = "toor",
        ) -> None:
            super().__init__(image)
            self.port = port
            self.root_token = root_token
            self.with_exposed_ports(self.port)
            self.with_env("VAULT_DEV_ROOT_TOKEN_ID", self.root_token)
            self.waiting_for(
                HttpWaitStrategy(self.port, "/v1/sys/health").for_status_code(200)
            )

        def get_connection_url(self) -> str:
            host_ip = self.get_container_host_ip()
            exposed_port = self.get_exposed_port(self.port)
            return f"http://{host_ip}:{exposed_port}"

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
    config.addinivalue_line("markers", "vault: requires a local Vault test container")


def pytest_collection_modifyitems(config, items):
    _ = config
    skip_vault = pytest.mark.skipif(
        not use_hvac, reason="Test skipped because hvac_module is not available"
    )
    for item in items:
        if "vault" in item.keywords:
            item.add_marker(skip_vault)
