# -*- coding: utf-8 -*-
import contextlib
import os
from pathlib import Path
from string import Template
from typing import Union, List, MutableMapping

__all__ = (
    'load_env',
    'load_dotenv',      # alias
    'unquote',
)

DEFAULT_ENVKEY = 'DOTENV'
DEFAULT_DOTENV = '.env'


def unquote(line, quotes='"\''):
    if line and line[0] in quotes and line[-1] == line[0]:
        line = line[1:-1]
    return line


def _env_files(env_file: str, search_path: List[Path], parents: bool, errors: bool) -> List[str]:
    """ expand env_file with full search path, optionally parents as well """

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
    fp = None
    try:
        fp = open(path, 'r')
        yield fp
    finally:
        if fp:
            fp.close()


def _process_env(env_file: str, search_path: List[Path], environ: MutableMapping[str, str], overwrite: bool,
                 parents: bool, errors: bool) -> MutableMapping[str, str]:
    """ search for any env_files in given dir list and populate environ dict
    :param env_file: base environment file name to use
    :param search_path: list of one or more paths to search
    :param environ:  environment to update
    :param overwrite:
    :param parents:
    """

    def process_line(string):
        """ process a single line """
        parts = string.split('=', 1)
        if len(parts) == 2:
            key, val = parts
            if overwrite or key not in environ:
                environ[key] = unquote(val)

    for env_path in _env_files(env_file, search_path, parents, errors):
        # insert PWD as container of env file
        env_path = Path(env_path).resolve()
        environ['PWD'] = str(env_path.parent)
        try:
            with open_env(env_path) as f:
                for line in f.readlines():
                    line = line.strip()
                    if line and line[0] != '#':
                        process_line(line)
        except FileNotFoundError:
            if errors:
                raise
    return environ


def _post_process(environ: MutableMapping[str, str]) -> MutableMapping[str, str]:
    """ post-process the variables using ${substitutions} """
    for env_key, env_val in environ.items():
        if all(v in env_val for v in ('${', '}')):  # looks like template
            # ignore anything that does not resolve, don't throw an exception!
            val = Template(env_val).safe_substitute(environ)
            if val != env_val:  # don't update unless we need to
                environ[env_key] = val
    return environ


def _update_os_env(environ: MutableMapping[str, str]) -> MutableMapping[str, str]:
    """ back-populate changed variables to the environment """
    for env_key, env_val in environ.items():
        if env_val != os.environ.get(env_key):
            os.environ[env_key] = env_val
    return os.environ


def load_env(env_file: str = None, search_path: Union[None, Union[List[str], List[Path]], str] = None,
             overwrite: bool = False, parents: bool = False, update: bool = True, errors: bool = False,
             environ: MutableMapping[str, str] = None) -> MutableMapping[str, str]:
    """
    Loads one or more .env files with optional nesting, updating os.environ
    :param env_file: name of the environment file (.env or $ENV default)
    :param search_path: single or list of directories in order of precedence - str, bytes or Path
    :param overwrite: whether to overwrite existing values
    :param parents: whether to search upwards until a file is found
    :param update: option to update os.environ, default=True
    :param environ: environment mapping to process
    :returns the new environment
    """
    if environ is None:
        environ = os.environ
    if not env_file:
        env_file = environ.get(DEFAULT_ENVKEY, DEFAULT_DOTENV)

    # insert this as a useful default
    environ['CWD'] = str(Path.cwd().resolve(strict=True))

    # determine where to search
    if search_path is None:
        import inspect
        frame = inspect.stack()[1]
        search_path = ['.', frame.filename]
    elif isinstance(search_path, (str, bytes, Path)):
        search_path = [search_path]
    # convert to array of Path for use internally
    search_path = [Path(p) for p in search_path]
    # if overwriting, traverse path in reverse order so first .env files have priority
    if overwrite:
        search_path.reverse()

    # slurp up the environment files found and
    # post process values for template variables
    environ = _post_process(_process_env(env_file, search_path, environ.copy(), overwrite, parents, errors))
    # optionally update the actual environment
    return _update_os_env(environ) if update else environ


load_dotenv = load_env
