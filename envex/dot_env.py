# -*- coding: utf-8 -*-
import os
import sys
import contextlib
from io import TextIOBase, BytesIO
from pathlib import Path
from string import Template
from typing import Dict, List, MutableMapping, Union, Optional, ContextManager, BinaryIO

from .env_crypto import decrypt_data, DecryptError

__all__ = (
    "load_env",
    "load_stream",
    "load_dotenv",  # alias
    "update_env",
    "unquote",
)


DEFAULT_ENVKEY = "DOTENV"
DEFAULT_DOTENV = ".env"
ENCRYPTED_EXT = ".enc"
DEFAULT_ENCODING = "utf-8"


def unquote(line, quotes="\"'"):
    if line and line[0] in quotes and line[-1] == line[0]:
        line = line[1:-1]
    return line


def update_env(env: MutableMapping[str, str], mapping: Dict):
    for k, v in mapping.items():
        env[str(k)] = str(v)


def _env_default(
    environ: MutableMapping[str, str], key: str, val: str, overwrite: bool = False
):
    if key and val and (overwrite or key not in environ):
        environ[key] = val


def _env_export(
    environ: MutableMapping[str, str], key: str, val: str, overwrite: bool = False
):
    if key and val and (overwrite or key not in environ):
        environ[key] = val
        os.environ[key] = val


def _env_files(
    env_file: str, search_path: List[Path], parents: bool, decrypt: bool, errors: bool
) -> List[str]:
    """expand env_file with the full search path, optionally parents as well"""

    def resolve_file(base_path: Path, name: str, _decrypt: bool) -> Optional[str]:
        """Returns the path to the env file, prioritising the encrypted version if enabled"""
        if _decrypt:
            encrypted_path = os.path.join(base_path, name + ENCRYPTED_EXT)
            if os.access(encrypted_path, os.R_OK):
                return encrypted_path

        standard_path = os.path.join(base_path, name)
        return standard_path if os.access(standard_path, os.R_OK) else None

    searched = []
    for path in search_path:
        path = path.resolve()
        if not path.is_dir():
            path = path.parent
        searched.append(path)

        for sub_path in [path] + list(path.parents):
            if env_path := resolve_file(sub_path, env_file, decrypt):
                yield env_path
                break
            elif not parents:
                break

    if errors:
        raise FileNotFoundError(f"{env_file} in {[s.as_posix() for s in searched]}")
    else:
        yield env_file


@contextlib.contextmanager
def open_env(path: Union[str, Path]) -> ContextManager[BinaryIO]:
    """same as open, allow monkeypatch"""
    fp = open(path, "rb")
    try:
        yield fp
    finally:
        fp.close()


ENV_COMMANDS = {
    "export": _env_export,
}


def _process_line(_lineno: int, string: str, errors: bool, _env_path: Path | None):
    """process a single line"""
    _func, _key, _val = _env_default, None, None
    parts = string.split("=", 1)
    if len(parts) == 2:
        _key, _val = parts
    elif len(parts) == 1:
        _key = parts[0]
    if _key:
        words = _key.split(maxsplit=1)
        if len(words) > 1:
            command, _key = words
            try:
                _func = ENV_COMMANDS[command]
            except KeyError:
                if errors:
                    path = _env_path.as_posix() if _env_path else "stream"
                    print(
                        f"unknown command {command} {path}({_lineno})",
                        file=sys.stderr,
                    )
    return _func, unquote(_key), unquote(_val)


def _process_stream(
    stream: BytesIO, environ, overwrite, errors, encoding=DEFAULT_ENCODING, env_path=None
):
    for lineno, line in enumerate(stream.readlines(), start=1):
        line = line.decode(encoding).strip()
        if line and line[0] != "#":
            func, key, val = _process_line(lineno, line, errors, env_path)
            if func is not None:
                func(environ, key, val, overwrite=overwrite)


def _process_env(
    env_file: str,
    search_path: List[Path],
    environ: MutableMapping[str, str],
    overwrite: bool,
    parents: bool,
    errors: bool,
    working_dirs: bool,
    decrypt: bool,
    password: Optional[str] = None,
    encoding: str = DEFAULT_ENCODING,
) -> MutableMapping[str, str]:
    """
    search for any env_files in the given dir list and populate environ dict

    :param env_file: base environment file name to use
    :param search_path: one or more paths to search
    :param environ: environment to update
    :param overwrite: whether to overwrite existing values
    :param parents: whether to search upwards until a file is found
    :param decrypt: whether to attempt decryption
    :param errors: whether to raise FileNotFoundError if the env_file is not found
    :param working_dirs: whether to add the env file's directory
    :param encoding: text encoding
    """
    files_not_found = []
    files_found = False
    for env_path in _env_files(env_file, search_path, parents, decrypt, errors):
        # insert PWD as container of the env file
        env_path = Path(env_path).resolve()
        if working_dirs:
            environ["PWD"] = str(env_path.parent)
        try:
            with open_env(env_path) as f:
                data = f.read()
                if isinstance(data, str):
                    data = data.encode(encoding)
                load_stream(
                    BytesIO(data),
                    environ,
                    overwrite,
                    errors,
                    decrypt,
                    password,
                    encoding,
                    env_path,
                )
            files_found = True
        except FileNotFoundError:
            files_not_found.append(env_path)
    if errors and not files_found and files_not_found:
        raise FileNotFoundError(
            f"{env_file} as {[s.as_posix() for s in files_not_found]}"
        )
    return environ


def _post_process(environ: MutableMapping[str, str]) -> MutableMapping[str, str]:
    """post-process the variables using ${substitutions}"""
    for env_key, env_val in environ.items():
        if all(v in env_val for v in ("${", "}")):  # looks like template
            # ignore anything that does not resolve, don't throw an exception!
            # todo: handle colon separators similar to shell handling..
            #  e.g. PATH=${VALUE:+$VALUE:}some_value
            #  ${VALUE:-default}, ${VALUE:=default}
            val = Template(env_val).safe_substitute(environ)
            if val != env_val:  # don't update unless we need to
                environ[env_key] = val
    return environ


def _update_os_env(environ: MutableMapping[str, str]) -> MutableMapping[str, str]:
    """back-populate changed variables to the environment"""
    for env_key, env_val in environ.items():
        if env_val != os.environ.get(env_key):
            os.environ[env_key] = env_val
    return os.environ


def load_env(
    env_file: str = None,
    search_path: Union[None, Union[List[str], List[Path]], str] = None,
    environ: MutableMapping[str, str] = None,
    overwrite: bool = False,
    parents: bool = False,
    update: bool = True,
    errors: bool = False,
    working_dirs: bool = True,
    decrypt: bool = False,
    password: str = None,
    encoding: Optional[str] = DEFAULT_ENCODING,
) -> MutableMapping[str, str]:
    """
    Loads one or more .env files with optional nesting, updating os.environ
    :param env_file: name of the environment file (.env or $ENV default)
    :param search_path: single or list of directories in order of precedence - str, bytes or Path
    :param environ: environment mapping to process
    :param overwrite: whether to overwrite existing values
    :param parents: whether to search upwards until a file is found
    :param update: option to update os.environ, default=True
    :param errors: whether to raise FileNotFoundError if env_file not found
    :param working_dirs: whether to add the env file's directory
    :param decrypt: whether to support encrypted .env.enc
    :param password: decryption password
    :param encoding: text encoding (default utf-8)
    :returns the new environment
    """
    if environ is None:
        environ = os.environ
    if not env_file:
        env_file = environ.get(DEFAULT_ENVKEY, DEFAULT_DOTENV)

    # insert this as a useful default
    if working_dirs:
        environ["CWD"] = Path.cwd().resolve(strict=True).as_posix()

    # determine where to search
    if search_path is None:
        import inspect

        frame = inspect.stack()[1]
        search_path = [".", frame.filename]
    elif isinstance(search_path, Path):
        search_path = [search_path]
    elif isinstance(search_path, (str, bytes)):
        search_path = search_path.split(os.pathsep)
    # convert to the array of Path for use internally
    search_path = [Path(p) for p in search_path]
    # if overwriting, traverse the path in reverse order so first .env files have priority
    if overwrite:
        search_path.reverse()

    # slurp up the environment files found and
    # post-process values for template variables
    environ = _post_process(
        _process_env(
            env_file,
            search_path,
            environ.copy(),
            overwrite,
            parents,
            errors,
            working_dirs,
            decrypt,
            password,
            encoding,
        )
    )
    # optionally update the actual environment
    return _update_os_env(environ) if update else environ


def load_stream(
    stream: Union[BytesIO, TextIOBase],
    environ: MutableMapping[str, str] = None,
    overwrite: bool = False,
    errors: bool = False,
    decrypt: bool = False,
    password: Optional[str] = None,
    encoding: Optional[str] = DEFAULT_ENCODING,
    env_path: Optional[Path] = None,
):
    if isinstance(stream, TextIOBase):
        stream.seek(0)
        stream = BytesIO(stream.read().encode(encoding))
    elif password and decrypt:
        with contextlib.suppress(DecryptError):
            stream = decrypt_data(stream, password)
    _process_stream(stream, environ, overwrite, errors, encoding, env_path)


load_dotenv = load_env
