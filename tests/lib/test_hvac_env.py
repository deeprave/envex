# -*- coding: utf-8 -*-
import os
import pytest

from envex.lib.hvac_env import SecretsManager

try:
    import hvac
except ImportError:
    hvac = None


class TestSecretsManager:
    url = os.getenv("VAULT_ADDR")
    token = os.getenv("VAULT_TOKEN")

    #  Tests that the get_secret method retrieves a secret from the cache if it exists
    @pytest.mark.skipif(hvac is None, reason="hvac is not installed")
    def test_get_secret_from_cache(self, mocker):
        # Create a SecretsManager instance
        secrets_manager = SecretsManager(self.url, self.token, base_path="test")

        # Mock the __get_secret_from_cache method to return a secret
        mocker.patch.object(secrets_manager, "_cache")
        secrets_manager._cache.get.return_value = "secret_value"

        # Call the get_secret method
        result = secrets_manager.get_secret("key")

        # Assert that the secret is retrieved from the cache
        assert result == "secret_value"

    #  Tests that the get_secret method retrieves a secret from Vault if it is not in the cache
    @pytest.mark.skipif(hvac is None, reason="hvac is not installed")
    def test_get_secret_from_vault(self, mocker):
        # Create a SecretsManager instance
        secrets_manager = SecretsManager(self.url, self.token, base_path="test")

        # Mock the __get_secret_from_cache method to return None
        mocker.patch.object(secrets_manager, "_cache")
        secrets_manager._cache.get.return_value = None

        # Mock the _client.read method to return a response with a secret value
        mocker.patch.object(secrets_manager._client, "read")
        secrets_manager._client.read.return_value = {"data": {"value": "secret_value"}}

        # Call the get_secret method
        result = secrets_manager.get_secret("key")

        # Assert that the secret is retrieved from Vault
        assert result == "secret_value"

    #  Tests that the set_secret method sets a secret in Vault and caches it
    @pytest.mark.skipif(hvac is None, reason="hvac is not installed")
    def test_set_secret_in_vault(self, mocker):
        # Create a SecretsManager instance
        secrets_manager = SecretsManager(self.url, self.token, base_path="test")

        # Mock the _client.write method
        mocker.patch.object(secrets_manager._client, "write")
        mocker.patch.object(secrets_manager._cache, "put")

        # Call the set_secret method
        secrets_manager.set_secret("key", "secret_value")

        # Assert that the secret is set in Vault
        secrets_manager._client.write.assert_called_once_with(
            "/secret/test/key", value="secret_value"
        )

        # Assert that the secret is cached
        secrets_manager._cache.put.assert_called_once_with("key", "secret_value")

    #  Tests that the seal method seals the Vault
    @pytest.mark.skipif(hvac is None, reason="hvac is not installed")
    def test_seal_vault(self, mocker):
        # Create a SecretsManager instance
        secrets_manager = SecretsManager(self.url, self.token, base_path="test")

        # Mock the _client.sys.seal method to return a response with sealed=True
        mocker.patch.object(secrets_manager._client.sys, "seal")
        secrets_manager._client.sys.seal.return_value = {"sealed": True}

        # Call the seal method
        result = secrets_manager.seal()

        # Assert that the Vault is sealed
        assert result is True

    #  Tests that the unseal_vault method unseals the Vault with valid keys and root token
    @pytest.mark.skipif(hvac is None, reason="hvac is not installed")
    def test_unseal_vault(self, mocker):
        # Create a SecretsManager instance
        secrets_manager = SecretsManager(self.url, self.token, base_path="test")

        # Mock the _client.sys.submit_unseal_keys method to return a response with sealed=False
        mocker.patch.object(secrets_manager._client.sys, "submit_unseal_keys")
        secrets_manager._client.sys.submit_unseal_keys.return_value = {"sealed": False}

        # Call the unseal_vault method
        result = secrets_manager.unseal_vault(["key1", "key2"], "root_token")

        # Assert that the Vault is unsealed
        assert result is True

    #  Tests that the unseal_vault method does not unseal the Vault with invalid keys or root token
    @pytest.mark.skipif(hvac is None, reason="hvac is not installed")
    def test_unseal_vault_invalid_keys(self, mocker):
        # Create a SecretsManager instance
        secrets_manager = SecretsManager(self.url, self.token, base_path="test")

        # Mock the _client.sys.submit_unseal_keys method to return a response with sealed=True
        mocker.patch.object(secrets_manager._client.sys, "submit_unseal_keys")
        secrets_manager._client.sys.submit_unseal_keys.return_value = {"sealed": True}

        # Call the unseal_vault method with invalid keys and root token
        result = secrets_manager.unseal_vault(["invalid_key"], "invalid_root_token")

        # Assert that the Vault is not unsealed
        assert result is False
