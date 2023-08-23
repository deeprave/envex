# -*- coding: utf-8 -*-
import contextlib
import os
import sys
from pathlib import Path
from string import Template
from typing import List, MutableMapping, Union

__all__ = (
    "load_env",
    "load_dotenv",  # alias
    "unquote",
)

DEFAULT_ENVKEY = "DOTENV"
DEFAULT_DOTENV = ".env"


def unquote(line, quotes="\"'"):
    if line and line[0] in quotes and line[-1] == line[0]:
        line = line[1:-1]
    return line


def _env_default(environ: MutableMapping[str, str], key: str, val: str, overwrite: bool = False):
    if key and val:
        if overwrite or key not in environ:
            environ[key] = val


def _env_export(environ: MutableMapping[str, str], key: str, val: str, overwrite: bool = False):
    if key and val:
        if overwrite or key not in environ:
            environ[key] = val
            os.environ[key] = val


def _env_files(env_file: str, search_path: List[Path], parents: bool, errors: bool) -> List[str]:
    """expand env_file with the full search path, optionally parents as well"""

    searched = []
    for path in search_path:
        path = path.resolve()
        if not path.is_dir():
            path = path.parent
        searched.append(path)
        paths = [path] + list(path.parents)
        # search a path and parents
        for sub_path in paths:
            # stop at first found, or ...
            # fail fast unless searching parents
            env_path = os.path.join(sub_path, env_file)
            if os.access(env_path, os.R_OK):
                yield env_path
            elif not parents:
                break
    if errors:
        raise FileNotFoundError(f"{env_file} in {[s.as_posix() for s in searched]}")
    else:
        yield env_file


@contextlib.contextmanager
def open_env(path: Union[str, Path]):
    """same as open, allow monkeypatch"""
    fp = open(path, "r")
    try:
        yield fp
    finally:
        fp.close()


ENV_COMMANDS = {
    "export": _env_export,
}


def _process_env(
    env_file: str,
    search_path: List[Path],
    environ: MutableMapping[str, str],
    overwrite: bool,
    parents: bool,
    errors: bool,
    working_dirs: bool,
) -> MutableMapping[str, str]:
    """
    search for any env_files in the given dir list and populate environ dict

    :param env_file: base environment file name to use
    :param search_path: one or more paths to search
    :param environ: environment to update
    :param overwrite: whether to overwrite existing values
    :param parents: whether to search upwards until a file is found
    :param errors: whether to raise FileNotFoundError if the env_file is not found
    :param working_dirs: whether to add the env file's directory
    """

    def process_line(_env_path: Path, _lineno: int, string: str):
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
                        print(
                            f"unknown command {command} {_env_path.as_posix()}({_lineno})",
                            file=sys.stderr,
                        )
        return _func, unquote(_key), unquote(_val)

    for env_path in _env_files(env_file, search_path, parents, errors):
        # insert PWD as container of env file
        env_path = Path(env_path).resolve()
        if working_dirs:
            environ["PWD"] = str(env_path.parent)
        try:
            with open_env(env_path) as f:
                lineno = 0
                for line in f.readlines():
                    line = line.strip()
                    lineno += 1
                    if line and line[0] != "#":
                        func, key, val = process_line(env_path, lineno, line)
                        if func is not None:
                            func(environ, key, val, overwrite=overwrite)
        except FileNotFoundError:
            if errors:
                raise
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
) -> MutableMapping[str, str]:
    """
    Loads one or more .env files with optional nesting, updating os.environ
    :param env_file: name of the environment file (.env or $ENV default)
    :param search_path: single or list of directories in order of precedence - str, bytes or Path
    :param overwrite: whether to overwrite existing values
    :param parents: whether to search upwards until a file is found
    :param update: option to update os.environ, default=True
    :param errors: whether to raise FileNotFoundError if env_file not found
    :param working_dirs: whether to add the env file's directory
    :param environ: environment mapping to process
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
        )
    )
    # optionally update the actual environment
    return _update_os_env(environ) if update else environ


load_dotenv = load_env
