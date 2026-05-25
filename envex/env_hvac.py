# -*- coding: utf-8 -*-
"""
This optional module is used to interface envex with the hvac (HashiCorp Vault) library.
"""

import logging
import os
from typing import Any, Iterator

from hvac.exceptions import InvalidPath

__all__ = ("SecretsManager",)


def _pem_file_contains(path: str | None, marker: str) -> bool:
    if path is None or not os.path.isfile(path):
        return False
    with open(path, "r") as f:
        return marker in f.read()


def expand(path: str):
    return os.path.expandvars(os.path.expanduser(path))


def read_pem(variable: str, is_key: bool = False):
    """
    Get the path from the given environment variable if it points to a valid PEM file.

    @param variable: The name of the environment variable to retrieve.
    @param is_key: Whether the file is a cert key or not
    @returns: The expanded file path if it looks valid.
    """
    value = os.getenv(variable)
    if value is not None:
        value = expand(value)
        intro = "PRIVATE KEY" if is_key else "BEGIN CERTIFICATE"
        value = value if _pem_file_contains(value, intro) else None
    return value


class SecretsManager:
    def __init__(
        self,
        url: str | None = None,
        token: str | None = None,
        cert=None,
        verify: bool | str = True,
        base_path: str | None = None,
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
            cert_path = read_pem("VAULT_CLIENT_CERT", False)
            key_path = read_pem("VAULT_CLIENT_KEY", True)
            cert_has_key = _pem_file_contains(cert_path, "PRIVATE KEY")
            if cert_path and key_path:
                cert = (cert_path, key_path)
            elif cert_path and cert_has_key:
                cert = cert_path
            elif cert_path or key_path:
                logging.warning(
                    "Ignoring incomplete Vault client certificate configuration; "
                    "VAULT_CLIENT_CERT must point to a valid PEM file containing "
                    "both certificate and private key, or VAULT_CLIENT_CERT and "
                    "VAULT_CLIENT_KEY must point to valid PEM files"
                )
                cert = None
        if base_path is None:
            base_path = os.getenv("VAULT_PATH", "")
        if not mount_point:
            mount_point = "secret"
        self._client: Any | None = None
        self.hvac_disabled = False
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
            self.hvac_disabled = True
            self._client = None
        self._mount_point = mount_point.strip("/")
        self._base_path = self.join(base_path)
        self._secrets = {}

    @staticmethod
    def join(*args, sep="/"):
        return sep.join([a.strip(sep) for a in args if a])

    @property
    def base_path(self) -> str:
        return self._base_path

    @property
    def mount_point(self) -> str:
        return self._mount_point

    def path(self, key) -> str:
        return self.join(self.base_path, key)

    @property
    def kv2(self):
        client = self.client
        return client.secrets.kv.v2 if client else None

    @property
    def client(self):
        # returns hvac.Client | None
        try:
            client = self._client
            if client is not None and client.is_authenticated():
                return client
        except Exception as exc:
            logging.debug(
                f"{exc.__class__.__name__} Vault client cannot authenticate {exc}"
            )

    @property
    def secrets(self) -> dict:
        return self._secrets

    def get_secrets(self, path: str = "") -> dict:
        kv2 = self.kv2
        if kv2:
            try:
                response = kv2.read_secret_version(
                    path=self.path(path),
                    mount_point=self.mount_point,
                    raise_on_deleted_version=True,
                )
            except InvalidPath:
                self._secrets = {}
                return self.secrets
            if response is not None and "data" in response:
                self._secrets = response["data"].get("data", {})
        return self.secrets

    def set_secrets(self, path: str = "", values: dict | None = None):
        kv2 = self.kv2
        if kv2 and values:
            self._secrets |= values
            if self.secrets:
                kv2.create_or_update_secret(
                    path=self.path(path),
                    secret=self.secrets,
                    mount_point=self.mount_point,
                )

    def delete_secrets(self, path: str = "") -> None:
        kv2 = self.kv2
        if kv2:
            kv2.delete_metadata_and_all_versions(
                path=self.path(path), mount_point=self.mount_point
            )
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
        kv2 = self.kv2
        if kv2 and not any((key is None, value is None)):
            if not self.secrets:
                self.get_secrets()
            self.secrets[key] = value
            kv2.create_or_update_secret(
                path=self.path(""),
                secret=dict(self.secrets),
                mount_point=self.mount_point,
            )

    def delete_secret(self, key: str, path: str = "") -> None:
        kv2 = self.kv2
        if kv2:
            if not self.secrets:
                self.get_secrets()
            if self.secrets and key in self.secrets:
                del self.secrets[key]
                if self.secrets:
                    kv2.create_or_update_secret(
                        path=self.path(path),
                        secret=dict(self.secrets),
                        mount_point=self.mount_point,
                    )
                else:
                    kv2.delete_metadata_and_all_versions(
                        path=self.path(path), mount_point=self.mount_point
                    )
                    self.secrets.clear()

    def list_secrets(self, path: str = "") -> Iterator[str]:
        if self.client:
            if not self.secrets:
                self.get_secrets()
            yield from self.secrets.keys()

    def seal(self):
        if self.client:
            response = self.client.sys.seal()
            return response["sealed"]
        return None

    def unseal(self, keys: list, root_token: str | None):
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
