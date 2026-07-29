# -*- coding: utf-8 -*-
"""
Type smart wrapper around os.environ
"""

import contextlib
import inspect
import logging
import os
import re
from pathlib import Path
from io import TextIOBase, BytesIO
from collections.abc import MutableMapping, Sequence
from typing import Any

from envex.env_hvac import SecretsManager

from .dot_env import load_env, unquote, load_stream


_MISSING = object()


class Env:
    """
    Wrapper around os.environ with .env enhancement` and django support
    """

    _exception: type[Exception]

    _BOOLEAN_TRUE_STRINGS = frozenset(("1", "en", "ok", "on", "t", "true", "y", "yes"))
    _BOOLEAN_FALSE_STRINGS = frozenset(("", "0", "f", "false", "n", "no", "off"))
    _EXCEPTION_CLS = KeyError
    _LOAD_ENV_KWARGS = frozenset(inspect.signature(load_env).parameters)
    _SOURCE_KEY = "ENVEX_SOURCE"
    _SOURCE_VALUES = frozenset(("env", "vault"))
    _VAULT_ENV_VARS = frozenset(
        (
            "VAULT_ADDR",
            "VAULT_TOKEN",
            "VAULT_PATH",
            "VAULT_CACERT",
            "VAULT_CAPATH",
            "VAULT_CLIENT_CERT",
            "VAULT_CLIENT_KEY",
            "VAULT_SKIP_VERIFY",
            "VAULT_TIMEOUT",
            "VAULT_NAMESPACE",
        )
    )

    def __init__(
        self,
        *args,
        environ: MutableMapping[str, str] | None = None,
        exception: type[Exception] | None = None,
        readenv: bool = False,
        url: str | None = None,
        token: str | None = None,
        cert=None,
        verify: bool | str | None = None,
        base_path: str | None = None,
        engine: str | None = None,
        mount_point: str | None = None,
        secrets_manager: SecretsManager | None = None,
        **kwargs,
    ):
        """

        @param args: dict (optional) environment variables
        @param environ: dict | None default base environment (os.environ is default)
        @param exception: (optional) Exception class to raise on error (default=KeyError)
        @param readenv: read values from .env files (default=False)
        @param decrypt: attempt decryption if password is used
        @param encoding: text encoding
        @param password: password to use for decryption
            - if readenv=True, the following additional args may be used
            @param env_file: str name of the environment file (.env or $ENV default)
            @param search_path: str | Path | list[str | Path] | None path(s) to search for env_file
            @param overwrite: bool whether to overwrite existing environment variables (default=False)
            @param parents: bool whether to search parent directories for env_file (default=False)
            @param update: bool whether to update os.environ with values from env_file (default=False)
            @param errors: bool whether to raise error on missing env_file (default=False)
            - kwargs for vault/secrets manager:
        @param url: (optional) vault url, default is $VAULT_ADDR
        @param token: (optional) vault token, default is $VAULT_TOKEN or ~/.vault-token
        @param cert: (optional) tuple (cert, key) or str path to client cert/key files
        @param verify: (optional) bool | str | None whether to verify server cert,
            set ca cert path, or derive verification from VAULT_SKIP_VERIFY and
            Vault CA environment when None (default=None)
        @param base_path: (optional) str base path for secrets (default=None)
        @param engine: (optional) str vault secrets engine (default=None)
        @param mount_point: (optional) str vault secrets mount point (default=None, determined by engine)
        @param secrets_manager: (optional) existing authenticated manager to reuse
        Environment values override Vault by default. Set ENVEX_SOURCE=vault
            to let Vault values override local values.
        @param working_dirs: (optional) bool whether to include PWD/CWD (default=True)
            -
        @param timeout: (optional) int timeout for requests sent to Vault.
        @param kwargs: (optional) environment variables to add/override
        """
        self._env = self.os_env() if environ is None else environ

        self.exception = exception or self._EXCEPTION_CLS

        streams = []
        for arg in args:
            if isinstance(arg, dict):
                for key, value in arg.items():
                    self.__set_initial_value(key, value)
            elif isinstance(arg, (BytesIO, TextIOBase)):
                streams.append(arg)

        stream_kwargs = kwargs.pop("streams", ())
        self._extend_streams(streams, stream_kwargs)

        timeout = kwargs.pop("timeout", None)
        load_env_kwargs = {
            key: kwargs.pop(key) for key in list(kwargs) if key in self._LOAD_ENV_KWARGS
        }

        password = self._resolve_password(
            load_env_kwargs.get("password", None), load_env_kwargs.get("decrypt", None)
        )
        load_env_kwargs["decrypt"] = bool(password)
        load_env_kwargs["password"] = password

        load_env_kwargs.setdefault("environ", self._env)
        if readenv:
            self.read_env(**load_env_kwargs)
            load_env_kwargs["environ"] = self._env
        self.read_streams(*streams, **load_env_kwargs)
        for key, value in kwargs.items():
            self.__set_initial_value(key, value)
        self.env_source = self._resolve_env_source() == "env"
        # Explicit verify wins. When omitted, VAULT_SKIP_VERIFY=true becomes an
        # explicit False; otherwise SecretsManager derives VAULT_CACERT /
        # VAULT_CAPATH / True in that order.
        if verify is None:
            vault_verify = (
                False if Env.is_true(self.__resolve("VAULT_SKIP_VERIFY", False)) else None
            )
        else:
            vault_verify = verify
        self.secret_manager = self._create_secret_manager(
            secrets_manager=secrets_manager,
            url=url,
            token=token,
            cert=cert,
            verify=vault_verify,
            connection_verify=verify,
            base_path=base_path,
            engine=engine,
            mount_point=mount_point,
            timeout=timeout,
        )

    def _create_secret_manager(
        self,
        *,
        secrets_manager: SecretsManager | None,
        url: str | None,
        token: str | None,
        cert,
        verify: bool | str | None,
        connection_verify: bool | str | None,
        base_path: str | None,
        engine: str | None,
        mount_point: str | None,
        timeout: int | None,
    ) -> SecretsManager | None:
        if secrets_manager is not None:
            self._reject_manager_connection_options(
                url=url,
                token=token,
                cert=cert,
                verify=connection_verify,
                engine=engine,
                timeout=timeout,
            )
            return SecretsManager.from_manager(
                secrets_manager, base_path=base_path, mount_point=mount_point
            )

        if not self._vault_is_configured(url=url, token=token):
            return None

        manager = SecretsManager(
            url=url,
            token=token,
            cert=cert,
            verify=verify,
            base_path=base_path,
            engine=engine,
            mount_point=mount_point,
            timeout=timeout,
        )
        if manager.client is None:
            raise RuntimeError("Vault is configured but cannot authenticate")
        return manager

    def _vault_is_configured(self, *, url: str | None, token: str | None) -> bool:
        effective_token = token or self.env.get("VAULT_TOKEN")
        if not effective_token:
            try:
                from hvac.utils import get_token_from_env
            except ImportError:
                effective_token = None
            else:
                effective_token = get_token_from_env()
        signals = bool(url or token) or any(
            self.env.get(name) is not None for name in self._VAULT_ENV_VARS
        )
        if effective_token:
            return True
        if signals:
            logging.warning("Vault is skipped because configuration is incomplete")
        return False

    @staticmethod
    def _reject_manager_connection_options(**options) -> None:
        supplied = [name for name, value in options.items() if value is not None]
        if supplied:
            raise ValueError(
                "secrets_manager cannot be combined with " + ", ".join(supplied)
            )

    @staticmethod
    def _is_stream(value):
        return isinstance(value, (BytesIO, TextIOBase))

    @classmethod
    def _extend_streams(cls, streams: list, stream_values) -> None:
        if stream_values is None:
            return
        if cls._is_stream(stream_values):
            streams.append(stream_values)
            return
        try:
            iterable = iter(stream_values)
        except TypeError as exc:
            raise TypeError("streams must be a stream or an iterable of streams") from exc
        for stream in iterable:
            if not cls._is_stream(stream):
                raise TypeError("streams must contain only stream objects")
            streams.append(stream)

    def _resolve_password_selector(self, selector: str | None) -> str | None:
        if not selector:
            return None
        if selector[0] == "$":  # indirect
            return self.env.get(selector[1:]) or None
        if selector[0] == "@":  # from file
            pw_file = Path(selector[1:])
            try:
                return pw_file.read_text().rstrip() or None
            except (IOError, PermissionError) as exc:
                raise self.exception(*exc.args) from exc
        return selector

    def _resolve_password(self, password: str | None, decrypt: bool | None) -> str | None:
        if decrypt is False:
            return None
        if password:
            return self._resolve_password_selector(password)
        return self._resolve_password_selector(self.env.get("ENV_PASSWORD"))

    @property
    def env(self):
        return self._env

    @staticmethod
    def os_env():
        return os.environ

    def _resolve_env_source(self) -> str:
        source = str(self.env.get(self._SOURCE_KEY, "env")).strip().lower()
        if source not in self._SOURCE_VALUES:
            raise ValueError(f"Invalid {self._SOURCE_KEY} value: {source!r}")
        return source

    def read_env(self, **kwargs):
        """
        :param kwargs: see load_env
            env_file: str
            search_path: str | Path | list[str | Path] | None
            overwrite: bool
            parents: bool
            update: bool
            errors: bool
            decrypt: bool
            password: str
            encoding: str
        kwargs: MutableMapping[str, str]
        """
        self._env = load_env(**kwargs)

    def read_streams(self, *streams, **kwargs):
        environ = kwargs["environ"]
        # default overwrite is different for streams
        overwrite = kwargs.get("overwrite", True)
        errors = kwargs.get("errors", False)
        decrypt = kwargs.get("decrypt", True)
        password = kwargs.get("password", None)
        encoding = kwargs.get("encoding", "utf-8")
        for stream in streams:
            load_stream(stream, environ, overwrite, errors, decrypt, password, encoding)

    @property
    def exception(self) -> type[Exception]:
        return self._exception

    @exception.setter
    def exception(self, exc: type[Exception]):
        self._exception = exc

    def __resolved_value(self, var: str):
        """Return the effective value and source for one concrete name."""
        env_value = self.env.get(var, _MISSING)
        env_value = _MISSING if env_value is None else env_value
        manager = getattr(self, "secret_manager", None)
        secret_value = _MISSING
        if (env_value is _MISSING or not self.env_source) and manager is not None:
            sm_value = manager.get_secret(var, None)
            if sm_value is not None:
                secret_value = sm_value
        if secret_value is not _MISSING and not self.env_source:
            return secret_value, "vault"
        if env_value is not _MISSING:
            return env_value, "environment"
        if secret_value is not _MISSING:
            return secret_value, "vault"
        return _MISSING, None

    def __resolve(self, var: str, default=None):
        """Resolve one concrete variable name without subclass dispatch."""
        value, _source = self.__resolved_value(var)
        return default if value is _MISSING else value

    def __resolved_candidate(self, var: str):
        for candidate in self._lookup_candidates(var):
            value, source = self.__resolved_value(candidate)
            if value is not _MISSING:
                return candidate, value, source
        return None, _MISSING, None

    def __set_raw(self, var: str, value) -> None:
        if value is None:
            self.env.pop(var, None)
        else:
            self.env[var] = str(value)

    def __set_initial_value(self, var: str, value) -> None:
        """Add a constructor value without translating Env control names."""
        if var == self._SOURCE_KEY or var in self._VAULT_ENV_VARS:
            self.__set_raw(var, value)
        else:
            Env.set(self, var, value)

    def _lookup_candidates(self, var: str):
        """Return concrete names to try, in lookup priority order."""
        return (var,)

    def _write_candidate(self, var: str):
        """Return the concrete name used for local writes."""
        return next(iter(self._lookup_candidates(var)), var)

    def get(self, var: str, default=None):
        _candidate, value, _source = self.__resolved_candidate(var)
        return default if value is _MISSING else value

    def pop(self, var, default=None):
        candidate, value, source = self.__resolved_candidate(var)
        if source == "environment":
            self.env.pop(candidate, None)
            return value
        return default

    def set(self, var: str | dict, value=None):
        if isinstance(var, dict):
            for k, v in var.items():
                Env.set(self, k, v)
        elif value is None:
            Env.unset(self, var)
        else:
            self.__set_raw(self._write_candidate(var), value)

    def setdefault(self, var, value) -> str | None:
        _candidate, current, _source = self.__resolved_candidate(var)
        if current is not _MISSING:
            return current
        candidate = self._write_candidate(var)
        self.__set_raw(candidate, value)
        return self.env.get(candidate)

    def unset(self, var):
        candidate, _value, source = self.__resolved_candidate(var)
        if source == "environment":
            self.env.pop(candidate, None)

    def is_set(self, var):
        return Env.get(self, var, None) is not None

    def is_all_set(self, *_vars):
        for v in _vars:
            # Expand list/tuple-like containers without consuming generators
            # or treating unordered mappings/sets as positional arguments.
            if isinstance(v, Sequence) and not isinstance(v, (str, bytes)):
                if not Env.is_all_set(self, *v):
                    return False
            elif not Env.is_set(self, v):
                return False
        return True

    def is_any_set(self, *_vars):
        for v in _vars:
            if isinstance(v, Sequence) and not isinstance(v, (str, bytes)):
                if Env.is_any_set(self, *v):
                    return True
            elif Env.is_set(self, v):
                return True
        return False

    def int(self, var, default: int | None = None) -> int:
        val = Env.get(self, var, default)
        return self._int(val)

    def float(self, var, default=None) -> float:
        val = Env.get(self, var, default)
        return self._float(val)

    def bool(self, var, default=None) -> bool:
        val = Env.get(self, var, default)
        return val if isinstance(val, bool) else self.is_true(val)

    def list(self, var, default=None) -> list:
        val = Env.get(self, var, default)
        return val if isinstance(val, (list, tuple)) else self._list(val)

    env_typemap = {
        "str": get,
        "int": int,
        "bool": bool,
        "float": float,
        "list": list,
    }

    # noinspection PyShadowingBuiltins
    def __call__(self, var, default=None, **kwargs):
        if default is not None and not Env.is_set(self, var):
            Env.setdefault(self, var, default)
        _type = kwargs.get("type", str)
        _type = _type if isinstance(_type, str) else _type.__name__
        with contextlib.suppress(KeyError):
            func = self.env_typemap[_type]
            return func(self, var, default=default)
        return Env.get(self, var, default)

    def export(self, *args, **kwargs):
        for arg in args:
            if not isinstance(arg, (dict,)):
                raise TypeError(
                    "export() requires either dictionaries or keyword=value pairs"
                )
            kwargs |= dict(arg.items())
        if not args and not kwargs:
            kwargs = self.env
        for k, v in kwargs.items():
            k = str(k)
            if v is None:
                candidate, _value, source = self.__resolved_candidate(k)
                if source == "environment":
                    self.env.pop(candidate, None)
                    os.environ.pop(candidate, None)
            else:
                candidate = self._write_candidate(k)
                self.__set_raw(candidate, v)
                os.environ[candidate] = str(v)

    @classmethod
    def is_true(cls, val):
        if val is None or val is False:
            return False
        if val is True:
            return True
        if isinstance(val, (int, float)):
            if val in (0, 1):
                return bool(val)
            raise ValueError(f"Invalid boolean value: {val!r}")
        if isinstance(val, bytes):
            try:
                val = val.decode()
            except UnicodeDecodeError as exc:
                raise ValueError(f"Invalid boolean value: {val!r}") from exc
        if isinstance(val, str):
            normalized = val.strip().lower()
            if normalized in cls._BOOLEAN_TRUE_STRINGS:
                return True
            if normalized in cls._BOOLEAN_FALSE_STRINGS:
                return False
            raise ValueError(f"Invalid boolean value: {val!r}")
        raise ValueError(f"Invalid boolean value: {val!r}")

    @classmethod
    def _int(cls, val):
        if val is None or val == "":
            return 0
        if isinstance(val, bool):
            return int(val)
        if isinstance(val, int):
            return val
        try:
            return int(val)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid integer value: {val!r}") from exc

    @classmethod
    def _float(cls, val):
        return val if isinstance(val, float) else float(val) if val else 0

    @classmethod
    def _list(cls, val):
        return (
            []
            if val is None
            else [unquote(part) for part in re.split(r"\s*,\s*", str(val))]
        )

    def __contains__(self, var):
        return Env.get(self, var, None) is not None

    def __setitem__(self, var: str, value: Any):
        Env.set(self, var, value)

    def __getitem__(self, var):
        if var not in self:
            raise self.exception(f"Key '{var}' not found")
        return Env.get(self, var)

    def __delitem__(self, var):
        Env.unset(self, var)

    def items(self):
        yield from self.env.items()

    def __iter__(self):
        return self.items()

    def check_var(self, var, default=None, raise_error=True):
        if not var:
            url = None
        else:
            url = Env.get(self, var, default=default) if var else default
            if not url and raise_error:
                raise self._exception(f"Expected {var} is not set in environment")
        return "" if url is None else url


env = Env()
