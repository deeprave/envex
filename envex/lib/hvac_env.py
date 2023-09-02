# -*- coding: utf-8 -*-
"""
This optional module is used to interface envex with the hvac (Hashicorp Vault) library.
"""
import logging

from envex.lib.cache import new_string_cache


class SecretsManager:
    def __init__(
        self,
        url: str = None,
        token: str = None,
        cert=None,
        verify: bool = True,
        cache_enabled: bool = True,
        base_path: str = None,
        **kwargs,
    ):
        """
        Initializes a Vault object with the given parameters.

        Parameters:
        :param url (str): Base URL for the Vault instance being addressed.
        :param token (str): Authentication token to include in requests sent to Vault.
        :param cert tuple(cert, key): Certificates for use in requests sent to the Vault instance.
            This should be a tuple with the certificate and then key.
        :param verify: (bool | str) Either a boolean to indicate whether TLS verification should be performed
            when sending requests to Vault, or a string pointing at the CA bundle to use for verification.
            See https://docs.python-requests.org/en/master/user/advanced/#ssl-cert-verification.
        :param timeout (int): The timeout value for requests sent to Vault.
        :param proxies (dict): Proxies to use when performing requests.
            See: https://docs.python-requests.org/en/master/user/advanced/#proxies
        :param allow_redirects (bool): Whether to follow redirects when sending requests to Vault.
        :param session (request.Session): Optional session object to use when performing request.
        :param namespace (str): Optional Vault Namespace.
        :cache_enabled (bool): Whether to enable caching for Vault operations. Defaults to True.
        :param kwargs (dict): Additional parameters to pass to the adapter constructor.
        """
        try:
            import hvac

            self._client = hvac.Client(url=url, token=token, cert=cert, verify=verify, **kwargs)
            self._base_path = f"/secret/{base_path}" if base_path else "/secrets"
        except ImportError:
            hvac = None
            self._client = None
            self._base_path = f"/secret/{base_path}" if base_path else "/secrets"
        self._cache = new_string_cache(64 if cache_enabled else 0)

    @property
    def client(self):
        # returns hvac.Client | None
        try:
            if self._client.is_authenticated():
                return self._client
        except Exception as exc:
            logging.debug(f"{exc.__class__.__name__} Vault client cannot authenticate {exc}")

    @property
    def base_path(self) -> str:
        return self._base_path

    def reset_cache(self):
        self._cache = self._cache.clear()

    def __get_secret_from_cache(self, key) -> str | None:
        return self._cache.get(key, default=None)

    def __store_secret_in_cache(self, key, value):
        self._cache[key] = value

    def get_secret(
        self,
        key: str,
        default: str | None = None,
        error: bool = False,
        nocache: bool = False,
    ):
        if self.client:
            # Check if the secret is already in the cache
            if (secret := self.__get_secret_from_cache(key)) is not None:
                return secret

            # Retrieve the secret from Hashicorp Vault
            if (response := self.client.read(f"{self.base_path}/{key}")) is not None and "data" in response:
                secret_value = response["data"].get("value")
                if secret_value is not None:
                    # Store the secret in the cache for future access
                    if not nocache:
                        self.__store_secret_in_cache(key, secret_value)
                    return secret_value

        if error and default is None:
            raise KeyError(key)
        # Placeholder or None value when hvac is not available or secret not found
        return default

    def set_secret(self, key: str, value: str, nocache: bool = False):
        if self.client and not any((key is None, value is None)):
            self.client.write(f"{self.base_path}/{key}", value=value)
            if not nocache:
                self.__store_secret_in_cache(key, value)

    def __getitem__(self, item: str):
        return self.get_secret(item, error=True)

    def __setitem__(self, key: str, value: str):
        assert value is not None, "Secret value cannot be None"
        self.set_secret(key, value)

    def seal(self):
        if self.client:
            response = self.client.sys.seal()
            return response["sealed"]
        return None

    def unseal_vault(self, keys: list, root_token: str):
        if self.client:
            response = self.client.sys.submit_unseal_keys(keys, root_token)
            return not response["sealed"]
        return None
