# -*- coding: utf-8 -*-
"""
This optional module is used to interface envex with the hvac (Hashicorp Vault) library.
"""
import logging
import os
from typing import Iterator

from envex.lib.cache import new_string_cache

__all__ = ("SecretsManager",)


def expand(path: str):
    return os.path.expandvars(os.path.expanduser(path))


def read_pem(variable: str, is_key: bool = False):
    """
    Get the value of the given environment variable and return it as a PEM string.

    :param variable: The name of the environment variable to retrieve.
    :return: The PEM string value of the environment variable if it looks valid.
    """
    value = os.getenv(variable)
    if value is not None:
        value = expand(value)
        if os.path.isfile(value):
            with open(value, "r") as f:
                value = f.read()
                if is_key:
                    intro = "PRIVATE KEY"
                else:
                    intro = "BEGIN CERTIFICATE"
                value = value if intro in value else None
    return value


class SecretsManager:
    def __init__(
        self,
        url: str = None,
        token: str = None,
        cert=None,
        verify: bool | str = True,
        cache_enabled: bool = True,
        base_path: str = None,
        engine: str | None = None,
        mount_point: str | None = None,
        **kwargs,
    ):
        """
        Initialises a Vault object with the given parameters.

        Parameters:
        :param url (str): Base URL for the Vault instance being addressed.
        :param token (str): Authentication token to include in requests sent to Vault.
        :param cert tuple(cert, key): Certificates for use in requests sent to the Vault instance.
            This should be a tuple with the certificate and then key.
        :param verify: (Bool | str) Either a boolean to indicate whether TLS verification should be performed
            when sending requests to Vault, or a string path of the CA bundle to use for verification.
            See https://docs.python-requests.org/en/master/user/advanced/#ssl-cert-verification.
        :param timeout (int): The timeout value for requests sent to Vault.
        :param proxies (dict): Proxies to use when performing requests.
            See: https://docs.python-requests.org/en/master/user/advanced/#proxies
        :param allow_redirects (bool): Whether to follow redirects when sending requests to Vault.
        :param session (request.Session): Optional session object to use when performing request.
        :param namespace (str): Optional Vault Namespace.
        :param cache_enabled (bool): Whether to enable caching for Vault operations.
            Defaults to True.
        :param kwargs (dict): Additional parameters to pass to the adapter constructor.
        """
        self._mount_point = None
        if verify in (True, None):
            verify = os.getenv("VAULT_åCACERT") or True
        if isinstance(verify, str):
            verify = expand(verify)
        if cert is None:
            cert = (
                read_pem("VAULT_CLIENT_CERT", False),
                read_pem("VAULT_CLIENT_KEY", True),
            )
            if cert[0] is None:
                cert = None
        if base_path is None:
            base_path = os.getenv("VAULT_PATH", None)
        # noinspection PyBroadException
        try:
            import hvac

            self._client: hvac.Client
            self._client = hvac.Client(url=url, token=token, cert=cert, verify=verify, **kwargs)
            if engine:
                self._engine = engine.lower()
                self._mount_point = mount_point
                response = self._client.sys.list_mounted_secrets_engines()
                for path, config in response["data"].items():
                    if config["type"] == self._engine:
                        self._mount_point = path
                        break
            else:
                self._engine = None
                self._mount_point = "secret"
            if mount_point:
                self._mount_point = mount_point
        except Exception as e:
            logging.debug(f"secrets manager disabled: {e.__class__.__name__} {e}")
            # noinspection PyUnusedLocal
            hvac = None
            self._client = None
        self._base_path = self.join(mount_point, base_path)
        self._cache = new_string_cache(64 if cache_enabled else 0)

    @staticmethod
    def join(*args, sep="/"):
        return sep.join([a for a in args if a])

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

    def path(self, key) -> str:
        return self.join(self.base_path, key)

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
            if (response := self.client.read(self.path(key))) is not None and "data" in response:
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
            self.client.write(self.path(key), value=value)
            if not nocache:
                self.__store_secret_in_cache(key, value)

    def __getitem__(self, item: str):
        return self.get_secret(item, error=True)

    def __setitem__(self, key: str, value: str):
        assert value is not None, "Secret value cannot be None"
        self.set_secret(key, value)

    def __delitem__(self, key: str):
        self.delete_secret(key)

    def seal(self):
        if self.client:
            response = self.client.sys.seal()
            return response["sealed"]
        return None

    def unseal(self, keys: list, root_token: str):
        if self.client:
            response = self.client.sys.submit_unseal_keys(keys, root_token)
            return not response["sealed"]
        return None

    def list_secrets(self, key) -> Iterator[str]:
        if self.client:
            response = self.client.list(self.path(key))
            if response is not None:
                data = response["data"]
                if "keys" in data:
                    for key in data["keys"]:
                        yield key

    def delete_secret(self, path) -> None:
        if self.client:
            self.client.delete(self.path(path))
            # clear it and contained elements as well
            for k in self._cache.match(self.join(path, "*")):
                self._cache.pop(k)
            self._cache.pop(path)
