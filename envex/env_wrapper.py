# -*- coding: utf-8 -*-
"""
Wrapper around os.environ
"""
import re
from typing import Any, MutableMapping
from urllib.parse import urlparse, urlunparse, parse_qs, unquote_plus
from .dot_env import load_env, unquote


class Env:
    """
    Wrapper around os.environ with .env enhancement` and django support
    """
    _BOOLEAN_TRUE_STRINGS = ('T', 't', '1', 'on', 'ok', 'Y', 'y', 'en')
    _BOOLEAN_TRUE_BYTES = (s.encode('utf-8') for s in _BOOLEAN_TRUE_STRINGS)
    _EXCEPTION_CLS = KeyError

    @staticmethod
    def os_env():
        import os
        return os.environ

    def __init__(self, *args, environ: MutableMapping[str, str] = None, exception=None, readenv=False, **kwargs):
        self.__typemap = {
            str: self.get,
            int: self.int,
            bool: self.bool,
            float: self.float,
            list: self.list,
        }
        self._env = environ or self.os_env()
        self._env.update(args)
        if readenv:
            self.read_env(**kwargs)
        else:
            self._env.update(kwargs)
        self.exception = exception or self._EXCEPTION_CLS

    def read_env(self, **kwargs):
        """
        :param kwargs: see load_env
            env_file: str
            search_path: Union[None, Union[List[str], List[Path]], str]
            overwrite: bool
            parents: bool
            update: bool
        :   MutableMapping[str, str]
        """
        kwargs.setdefault('environ', self._env)
        self._env = load_env(**kwargs)

    @property
    def exception(self):
        return self._exception

    @exception.setter
    def exception(self, exc):
        if not issubclass(exc, Exception):
            raise ValueError(f'arg {exc} is not an exception class')
        self._exception = exc

    @property
    def env(self):
        return self._env

    def get(self, var, default=None):
        return self.env.get(var, default)

    def __call__(self, var, default=None, type=str):
        if default is not None and not self.is_set(var):
            self.set(var, default)
        try:
            return self.__typemap[type](var, default=default)
        except KeyError:
            pass
        return self.get(var, default)

    def pop(self, var, default=None):
        val = self.get(var, default)
        self.unset(var)
        return val

    def set(self, var, value=None):
        self.env[var] = str(value) if value is not None else value

    def setdefault(self, var, value):
        return self.env.setdefault(var, str(value) if value is not None else value)

    def unset(self, var):
        if var in self.env:
            del self._env[var]

    def is_set(self, var):
        return var in self

    def is_all_set(self, *_vars):
        return all(v in self for v in _vars)

    def is_any_set(self, *_vars):
        return any(v in self for v in _vars)

    def int(self, var, default=None) -> int:
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

    def export(self, *args, **kwargs):
        for arg in args:
            if not isinstance(arg, (dict,)):
                raise TypeError('export() requires either dictionaries or keyword=value pairs')
            self.export(**arg)
        for k, v in kwargs.items():
            if v is None:
                self.unset(k)
            else:
                self.set(k, v)

    @classmethod
    def _true_values(cls, val):
        return cls._BOOLEAN_TRUE_STRINGS if isinstance(val, str) else cls._BOOLEAN_TRUE_BYTES

    @classmethod
    def is_true(cls, val):
        if val in (None, False, '', 0, '0'):
            return False
        if not isinstance(val, (str, bytes)):
            return bool(val)
        true_vals = cls._true_values(val)
        return True if val and any([val.startswith(v) for v in true_vals]) else False

    @classmethod
    def _int(cls, val):
        return val if isinstance(val, int) else int(val) if val and str.isdigit(val) else 0

    @classmethod
    def _float(cls, val):
        return val if isinstance(val, float) else float(val) if val else 0

    @classmethod
    def _list(cls, val):
        return [] if val is None else [unquote(part) for part in re.split(r'\s*,\s*', str(val))]

    def __contains__(self, var):
        return str(var) in self.env

    def __setitem__(self, var: str, value: Any):
        self.set(var, value)

    def __getitem__(self, var):
        if var not in self:
            raise self.exception(f"Key '{var}' not found")
        return self.get(var)

    def __delitem__(self, var):
        self.unset(var)

    def items(self):
        for var, val in self.env.items():
            yield var, val

    def __iter__(self):
        return self.items()

    def check_var(self, var, default=None, raise_error=True):
        if not var:
            url = None
        else:
            url = self.get(var, default=default) if var else default
            if not url and raise_error:
                raise self.exception(f'Expected {var} is not set in environment')
        return '' if url is None else url

env = Env()
