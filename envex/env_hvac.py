# -*- coding: utf-8 -*-
"""
This optional module is used to interface envex with the hvac (HashiCorp Vault) library.
"""

import logging
import os
from typing import Any, Iterator

__all__ = ("SecretsManager",)


def _is_invalid_path(exc: Exception) -> bool:
    try:
        from hvac.exceptions import InvalidPath
    except ImportError:
        return False
    return isinstance(exc, InvalidPath)


def _pem_file_contains(path: str | None, marker: str) -> bool:
    if path is None or not os.path.isfile(path):
        return False
    with open(path, "r") as f:
        return marker in f.read()


def expand(path: str):
    return os.path.expandvars(os.path.expanduser(path))


def _vault_verify_from_env() -> bool | str:
    cacert = os.getenv("VAULT_CACERT")
    if cacert:
        return expand(cacert)

    capath = os.getenv("VAULT_CAPATH")
    if capath:
        capath = expand(capath)
        # requests accepts a CA bundle file or an OpenSSL-hashed CA directory.
        # Prefer honoring a file-valued VAULT_CAPATH over falling back to system
        # CAs, which would silently weaken a pinned trust configuration.
        if os.path.isfile(capath) or os.path.isdir(capath):
            return capath
        raise ValueError(
            f"VAULT_CAPATH={capath!r} must point to a CA bundle file "
            "or CA certificate directory"
        )

    return True


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
        verify: bool | str | None = None,
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
        :param verify: (Bool | str | None) Either a boolean to indicate whether TLS verification should be
            performed when sending requests to Vault, a string path of the CA bundle or OpenSSL-hashed CA
            directory to use for verification, or None to derive verification from VAULT_CACERT, then a
            VAULT_CAPATH CA directory, then True.
            See https://docs.python-requests.org/en/master/user/advanced/#ssl-cert-verification.
        :param timeout (int): The timeout value for requests sent to Vault.
        :param proxies (dict): Proxies to use when performing requests.
            See: https://docs.python-requests.org/en/master/user/advanced/#proxies
        :param allow_redirects (bool): Whether to follow redirects when sending requests to Vault.
        :param session (request.Session): Optional session object to use when performing request.
        :param namespace (str): Optional Vault Namespace.
        :param kwargs (dict): Additional parameters to pass to the adapter constructor.
        """
        if verify is None:
            verify = _vault_verify_from_env()
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
        self._cache: dict[tuple[str, str], dict] = {}

    @classmethod
    def from_manager(
        cls,
        manager: "SecretsManager",
        *,
        base_path: str | None = None,
        mount_point: str | None = None,
    ) -> "SecretsManager":
        """Create a path-scoped view that borrows an authenticated manager client."""
        if not isinstance(manager, cls):
            raise TypeError("manager must be a SecretsManager instance")
        if manager.client is None:
            raise ValueError("manager must have an authenticated Vault client")

        view = cls.__new__(cls)
        view._client = manager._client
        view.hvac_disabled = manager.hvac_disabled
        view._engine = manager._engine
        view._mount_point = (mount_point or manager.mount_point).strip("/")
        view._base_path = cls.join(manager.base_path if base_path is None else base_path)
        view._cache = manager._cache
        return view

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

    def _cache_key(self, path: str = "") -> tuple[str, str]:
        return self.mount_point, self.path(path)

    def _cached(self, path: str = "") -> dict:
        return self._cache.setdefault(self._cache_key(path), {})

    def _cache_entry(self, path: str = "") -> dict | None:
        return self._cache.get(self._cache_key(path))

    def _replace_cached(self, path: str, values: dict) -> dict:
        cached = dict(values)
        self._cache[self._cache_key(path)] = cached
        return cached

    @staticmethod
    def _response_values(response: Any) -> dict | None:
        if not isinstance(response, dict):
            return None
        data = response.get("data")
        if not isinstance(data, dict):
            return None
        values = data.get("data")
        return dict(values) if isinstance(values, dict) else None

    def _clear_cached(self, path: str = "") -> None:
        self._cache.pop(self._cache_key(path), None)

    @property
    def _secrets(self) -> dict:
        """Compatibility alias for the manager's default-path cache entry."""
        return self._cache_entry() or {}

    @_secrets.setter
    def _secrets(self, values: dict) -> None:
        if not hasattr(self, "_cache"):
            self._cache = {}
        self._replace_cached("", values)

    @property
    def kv2(self):
        client = self.client
        return client.secrets.kv.v2 if client else None

    @property
    def client(self):
        # returns hvac.Client | None
        client = self._client
        if client is not None and client.is_authenticated():
            return client

    @property
    def secrets(self) -> dict:
        """Return a snapshot of the default-path secrets."""
        return dict(self._secrets)

    def get_secrets(self, path: str = "") -> dict:
        kv2 = self.kv2
        if kv2:
            try:
                response = kv2.read_secret_version(
                    path=self.path(path),
                    mount_point=self.mount_point,
                    raise_on_deleted_version=True,
                )
            except Exception as exc:
                if not _is_invalid_path(exc):
                    raise
                return dict(self._replace_cached(path, {}))
            values = self._response_values(response)
            if values is not None:
                return dict(self._replace_cached(path, values))
        return dict(self._cache_entry(path) or {})

    def set_secrets(self, path: str = "", values: dict | None = None):
        kv2 = self.kv2
        if kv2 and values:
            if self._cache_key(path) not in self._cache:
                self.get_secrets(path)
            secrets = self._cached(path)
            secrets.update(values)
            if secrets:
                kv2.create_or_update_secret(
                    path=self.path(path),
                    secret=dict(secrets),
                    mount_point=self.mount_point,
                )

    def delete_secrets(self, path: str = "") -> None:
        kv2 = self.kv2
        if kv2:
            kv2.delete_metadata_and_all_versions(
                path=self.path(path), mount_point=self.mount_point
            )
        self._clear_cached(path)

    def get_secret(self, key: str, default: str | None = None, error: bool = False):
        secrets = self._cache_entry()
        if secrets is None:
            self.get_secrets()
            secrets = self._cache_entry()
        if secrets is not None and key in secrets:
            return secrets[key]
        if error and default is None:
            raise KeyError(key)
        # Placeholder or None value when hvac is not available or secret not found
        return default

    def set_secret(self, key: str, value: str):
        kv2 = self.kv2
        if kv2 and not any((key is None, value is None)):
            secrets = self._cached()
            if not secrets:
                self.get_secrets()
                secrets = self._cached()
            secrets[key] = value
            kv2.create_or_update_secret(
                path=self.path(""),
                secret=dict(secrets),
                mount_point=self.mount_point,
            )

    def delete_secret(self, key: str, path: str = "") -> None:
        kv2 = self.kv2
        if kv2:
            secrets = self._cached(path)
            if not secrets:
                self.get_secrets(path)
                secrets = self._cached(path)
            if key in secrets:
                del secrets[key]
                if secrets:
                    kv2.create_or_update_secret(
                        path=self.path(path),
                        secret=dict(secrets),
                        mount_point=self.mount_point,
                    )
                else:
                    kv2.delete_metadata_and_all_versions(
                        path=self.path(path), mount_point=self.mount_point
                    )
                    self._clear_cached(path)

    def list_secrets(self, path: str = "") -> Iterator[str]:
        if self.client:
            secrets = self._cached(path)
            if not secrets:
                self.get_secrets(path)
                secrets = self._cached(path)
            yield from secrets.keys()

    def seal(self):
        # Seal/status/unseal operations must work before authentication succeeds:
        # a sealed Vault can reject authenticated checks until unseal keys are submitted.
        if self._client:
            response = self._client.sys.seal()
            return response["sealed"]
        return None

    def unseal(self, keys: list, root_token: str | None):
        # Intentionally bypasses self.client so unseal can run while Vault is sealed.
        if self._client:
            response = self._client.sys.submit_unseal_keys(keys, root_token)
            return not response["sealed"]
        return None

    @property
    def sealed(self) -> bool | None:
        # Intentionally bypasses self.client so status works before authentication.
        if self._client:
            response = self._client.seal_status
            return response["sealed"]
        return None
