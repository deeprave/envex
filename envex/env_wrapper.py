# -*- coding: utf-8 -*-
"""
Type smart wrapper around os.environ
"""

import contextlib
import re
from pathlib import Path
from io import TextIOBase, BytesIO
from typing import Any, List, MutableMapping, Type

from envex.env_hvac import SecretsManager

from .dot_env import load_env, unquote, load_stream, update_env


class Env:
    """
    Wrapper around os.environ with .env enhancement` and django support
    """

    _exception: Type[Exception]

    _BOOLEAN_TRUE_STRINGS = ("T", "t", "1", "on", "ok", "Y", "y", "en")
    _BOOLEAN_TRUE_BYTES = (b"T", b"t", b"1", b"on", b"ok", b"Y", b"y", b"en")
    _EXCEPTION_CLS = KeyError

    def __init__(
        self,
        *args,
        environ: MutableMapping[str, str] = None,
        exception: Type[Exception] | None = None,
        readenv: bool = False,
        url: str = None,
        token: str = None,
        cert=None,
        verify: bool = True,
        base_path: str = None,
        engine: str | None = None,
        mount_point: str | None = None,
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
            @param search_path: None | Union[List[str], List[Path]], str] path(s) to search for env_file
            @param overwrite: bool whether to overwrite existing environment variables (default=False)
            @param parents: bool whether to search parent directories for env_file (default=False)
            @param update: bool whether to update os.environ with values from env_file (default=False)
            @param errors: bool whether to raise error on missing env_file (default=False)
            - kwargs for vault/secrets manager:
        @param url: (optional) vault url, default is $VAULT_ADDR
        @param token: (optional) vault token, default is $VAULT_TOKEN or ~/.vault-token
        @param cert: (optional) tuple (cert, key) or str path to client cert/key files
        @param verify: (optional) bool | str whether to verify server cert or set ca cert path (default=True)
        @param base_path: (optional) str base path for secrets (default=None)
        @param engine: (optional) str vault secrets engine (default=None)
        @param mount_point: (optional) str vault secrets mount point (default=None, determined by engine)
        @param working_dirs: (optional) bool whether to include PWD/CWD (default=True)
            -
        @param kwargs: (optional) environment variables to add/override
        """
        self._env = self.os_env() if environ is None else environ

        streams = []
        for arg in args:
            if isinstance(arg, dict):
                update_env(self._env, arg)
            elif isinstance(arg, (BytesIO, TextIOBase)):
                streams.append(arg)

        self.exception = exception or self._EXCEPTION_CLS

        if "streams" in kwargs and isinstance(kwargs["streams"], (tuple, list)):
            streams.extend(kwargs.pop("streams"))

        password = self._resolve_password(
            kwargs.get("password", None),
            kwargs.get("decrypt", None)
        )
        kwargs["decrypt"] = bool(password)
        kwargs["password"] = password

        kwargs.setdefault("environ", self._env)
        if readenv:
            self.read_env(**kwargs)
        self.read_streams(*streams, **kwargs)
        self.env_source = self.env.get("ENVEX_SOURCE", "env") == "env"
        self.secret_manager = SecretsManager(
            url=url,
            token=token,
            cert=cert,
            verify=verify
            if verify is not None
            else not self.env.get("VAULT_SKIP_VERIFY", False),
            base_path=base_path,
            engine=engine,
            mount_point=mount_point,
            timeout=kwargs.get("timeout", None),
        )

    def _resolve_password(self, password: str|None, decrypt: bool|None) -> str|None:
        if decrypt is False:
            return None
        env_var = None
        if decrypt is None and not password:
            for env_var in ("ENV_PASSWORD", "$ENV_PASSWORD", "@ENV_PASSWORD"):
                if env_var in self.env:
                    break
            else:
                env_var = None
        elif password:
            env_var = password
        if env_var:
            if env_var[0] == "$":    # indirect
                password = self.env.get(env_var[1:])
            elif env_var[0] == "@":  # from file
                 pw_file = Path(env_var[1:])
                 try:
                     password = pw_file.read_text().rstrip()
                 except (IOError, PermissionError) as exc:
                     raise self.exception(*exc.args) from exc
        return password or None

    @property
    def env(self):
        return self._env

    @staticmethod
    def os_env():
        import os

        return os.environ

    def read_env(self, **kwargs):
        """
        :param kwargs: see load_env
            env_file: str
            search_path: Union[None, Union[List[str], List[Path]], str]
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
    def exception(self) -> Type[Exception]:
        return self._exception

    @exception.setter
    def exception(self, exc: Type[Exception]):
        self._exception = exc

    def get(self, var: str, default=None):
        # getting from the environment is the least expensive
        value = self.env.get(var, None)
        # not set or isn't primary, check secrets manager
        if (value is None or not self.env_source) and hasattr(self, "secret_manager"):
            sm_value = self.secret_manager.get_secret(var, None)
            if sm_value is not None:
                value = sm_value
        return default if value is None else value

    def pop(self, var, default=None):
        val = self.get(var, default)
        self.unset(var)
        return val

    def set(self, var: str | dict, value=None):
        if isinstance(var, dict):
            for k, v in var.items():
                self.set(k, v)
        else:
            self.env[var] = str(value) if value is not None else value

    def setdefault(self, var, value) -> str | None:
        return self.env.setdefault(var, str(value) if value is not None else value)

    def unset(self, var):
        if var in self.env:
            del self.env[var]

    def is_set(self, var):
        return var in self.env

    def is_all_set(self, *_vars: str | List[str | list | tuple]):
        for v in _vars:
            if isinstance(v, (list, tuple)):
                return self.is_all_set(*v)
            if not self.is_set(v):
                return False
        return True

    def is_any_set(self, *_vars: str | List[str | list | tuple]):
        for v in _vars:
            if isinstance(v, (list, tuple)):
                return self.is_any_set(*v)
            if self.is_set(v):
                return True
        return False

    def int(self, var, default: int | None = None) -> int:
        val = self.get(var, default)
        return self._int(val)

    def float(self, var, default=None) -> float:
        val = self.get(var, default)
        return self._float(val)

    def bool(self, var, default=None) -> bool:
        val = self.get(var, default)
        return val if isinstance(val, (bool, int)) else self.is_true(val)

    def list(self, var, default=None) -> list:
        val = self.get(var, default)
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
        if default is not None and not self.is_set(var):
            self.set(var, default)
        _type = kwargs.get("type", str)
        _type = _type if isinstance(_type, str) else _type.__name__
        with contextlib.suppress(KeyError):
            func = self.env_typemap[_type]
            return func(self, var, default=default)
        return self.get(var, default)

    def export(self, *args, **kwargs):
        import os

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
            try:
                if v is None:
                    self.unset(k)
                    del os.environ[k]
                else:
                    self.set(k, v)
                    os.environ[k] = str(v)
            except KeyError:
                ...

    @classmethod
    def _true_values(cls, val):
        return (
            cls._BOOLEAN_TRUE_STRINGS if isinstance(val, str) else cls._BOOLEAN_TRUE_BYTES
        )

    @classmethod
    def is_true(cls, val):
        if val in (None, False, "", 0, "0"):
            return False
        if not isinstance(val, (str, bytes)):
            return bool(val)
        true_vals = cls._true_values(val)
        return bool(val and any(val.startswith(v) for v in true_vals))

    @classmethod
    def _int(cls, val):
        return (
            val if isinstance(val, int) else int(val) if val and str.isdigit(val) else 0
        )

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
        return self.get(var, None) is not None

    def __setitem__(self, var: str, value: Any):
        self.set(var, value)

    def __getitem__(self, var):
        if var not in self:
            raise self.exception(f"Key '{var}' not found")
        return self.get(var)

    def __delitem__(self, var):
        self.unset(var)

    def items(self):
        yield from self.env.items()

    def __iter__(self):
        return self.items()

    def check_var(self, var, default=None, raise_error=True):
        if not var:
            url = None
        else:
            url = self.get(var, default=default) if var else default
            if not url and raise_error:
                raise self._exception(f"Expected {var} is not set in environment")
        return "" if url is None else url


env = Env()
