# -*- coding: utf-8 -*-
"""
This optional module is used to interface envex with the hvac (Hashicorp Vault) library.
"""
import logging
import os
from typing import Iterator

__all__ = ("SecretsManager",)


def expand(path: str):
    return os.path.expandvars(os.path.expanduser(path))


def read_pem(variable: str, is_key: bool = False):
    """
    Get the value of the given environment variable and return it as a PEM string.

    @param variable: The name of the environment variable to retrieve.
    @param is_key: Whether the file is a cert key or not
    @returns: The PEM string value of the environment variable if it looks valid.
    """
    value = os.getenv(variable)
    if value is not None:
        value = expand(value)
        if os.path.isfile(value):
            with open(value, "r") as f:
                value = f.read()
                intro = "PRIVATE KEY" if is_key else "BEGIN CERTIFICATE"
                value = value if intro in value else None
    return value


class SecretsManager:
    hvac_disabled = False

    def __init__(
        self,
        url: str = None,
        token: str = None,
        cert=None,
        verify: bool | str = True,
        base_path: str = None,
        engine: str | None = None,
        mount_point: str | None = None,
        timeout: int | None = None,
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
        :param kwargs (dict): Additional parameters to pass to the adapter constructor.
        """
        if verify in (True, None):
            verify = os.getenv("VAULT_CACERT") or True
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
            base_path = os.getenv("VAULT_PATH", "")
        if not mount_point:
            mount_point = "secret"
        if SecretsManager.hvac_disabled:
            self._client = None
        else:
            # noinspection PyBroadException
            try:
                import hvac

                timeout = timeout or int(os.getenv("VAULT_TIMEOUT", "5"))

                self._client: hvac.Client
                self._client = hvac.Client(
                    url=url,
                    token=token,
                    cert=cert,
                    verify=verify,
                    timeout=timeout,
                    **kwargs,
                )
                if engine:
                    self._engine = engine.lower()
                    response = self._client.sys.list_mounted_secrets_engines()
                    for path, config in response["data"].items():
                        if config["type"] == self._engine:
                            mount_point = path
                            break
                else:
                    self._engine = None  # assume kv
            except Exception as e:
                msg = f"{e.__class__.__name__} secrets manager disabled: {e}"
                logging.debug(msg)
                SecretsManager.hvac_disabled = True
                # noinspection PyUnusedLocal
                hvac = None
                self._client = None
        self._mount_point = self.join(mount_point, "data")
        self._base_path = self.join(self._mount_point, base_path)
        self._secrets = {}

    @staticmethod
    def join(*args, sep="/"):
        return sep.join([a for a in args if a])

    @property
    def base_path(self) -> str:
        return self._base_path

    def path(self, key) -> str:
        return self.join(self.base_path, key)

    @property
    def client(self):
        # returns hvac.Client | None
        try:
            if self._client.is_authenticated():
                return self._client
        except Exception as exc:
            logging.debug(
                f"{exc.__class__.__name__} Vault client cannot authenticate {exc}"
            )

    @property
    def secrets(self) -> dict:
        return self._secrets

    def get_secrets(self, path: str = "") -> dict:
        if self.client:
            response = self.client.read(self.path(path))
            if response is not None and "data" in response:
                self._secrets = response["data"].get("value", {})
        return self.secrets

    def set_secrets(self, path: str = "", values: dict | None = None):
        if self.client and values:
            self._secrets |= values
            if self.secrets:
                self.client.write(self.path(path), data=self.secrets)
            else:
                self.client.delete(self.path(path))

    def delete_secrets(self, path: str = "") -> None:
        if self.client:
            self.client.delete(self.path(path))
        self._secrets.clear()

    def get_secret(self, key: str, default: str | None = None, error: bool = False):
        if self.client:
            # Check if the secret is already in the cache
            if not self.secrets:
                self.get_secrets()
            if key in self.secrets:
                return self.secrets[key]
        if error and default is None:
            raise KeyError(key)
        # Placeholder or None value when hvac is not available or secret not found
        return default

    def set_secret(self, key: str, value: str):
        if self.client and not any((key is None, value is None)):
            if not self.secrets:
                self.get_secrets()
            self.secrets[key] = value
            self.client.write(self.path(key), **self.secrets)

    def delete_secret(self, key: str, path: str = "") -> None:
        if self.client:
            if not self.secrets:
                self.get_secrets()
            if self.secrets and key in self.secrets:
                del self.secrets[key]
                if self.secrets:
                    self.client.write(self.path(path), **self.secrets)
                else:
                    self.client.delete(self.path(path))
                self.secrets.clear()

    def list_secrets(self, path: str = "") -> Iterator[str]:
        if self.client:
            if not self.secrets:
                self.get_secrets()
            yield from self.secrets.keys()

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

    @property
    def sealed(self) -> bool | None:
        if self.client:
            response = self.client.seal_status
            return response["sealed"]
        return None
