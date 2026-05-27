# -*- coding: utf-8 -*-
import errno
import os
import sys
import contextlib
import re
from collections.abc import Collection, Generator, Iterable, MutableMapping
from io import TextIOBase, BytesIO, BufferedReader
from pathlib import Path
from typing import Any

from .env_crypto import AUTH_MAGIC_BYTES, MAGIC_BYTES, decrypt_data, DecryptError
from .paths import current_working_dir

__all__ = (
    "load_env",
    "load_stream",
    "load_dotenv",  # alias
    "substitute_env_vars",
    "update_env",
    "unquote",
)


DEFAULT_ENVKEY = "DOTENV"
DEFAULT_DOTENV = ".env"
ENCRYPTED_EXT = ".enc"
DEFAULT_ENCODING = "utf-8"

# Precompiled regular expression patterns
_MODIFIER_PATTERN = re.compile(r":([-+])")
_VAR_BRACES_PATTERN = re.compile(r"\${([^{}]+)}")
_VAR_NO_BRACES_PATTERN = re.compile(r"\$([a-zA-Z_][a-zA-Z0-9_]*)")
_DOTENV_ASSIGNMENT_PREFIX_PATTERN = re.compile(r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=")
# Only keys that use the envex magic header plus "_" can be rescued as
# plaintext after decryption fails. Broader KEY= matching can be produced by
# random encrypted bytes and would hide wrong-password/corrupt-container errors.
_MAGIC_DOTENV_KEY_PREFIXES = (
    f"{AUTH_MAGIC_BYTES.decode('ascii')}_",
    f"{MAGIC_BYTES.decode('ascii')}_",
)
_PACKAGE_ROOT = Path(__file__).resolve().parent


def unquote(line, quotes="\"'"):
    if line and line[0] in quotes and line[-1] == line[0]:
        line = line[1:-1]
    return line


def update_env(env: MutableMapping[str, str], mapping: dict):
    for k, v in mapping.items():
        env[str(k)] = str(v)


def _copy_env_mapping(environ: MutableMapping[str, str]) -> MutableMapping[str, str]:
    copy = getattr(environ, "copy", None)
    if callable(copy):
        copied = copy()
        if isinstance(copied, MutableMapping):
            return copied
    return dict(environ)


def _set_env_value_if_needed(
    environ: MutableMapping[str, str],
    key: str,
    val: str | None,
    overwrite: bool = False,
) -> bool:
    """
    Set an environment value if needed.

    If val is None, environ is left unchanged.
    Returns True only when `environ` was mutated.
    """
    if key and val is not None and (overwrite or key not in environ):
        environ[key] = val
        return True
    return False


def _set_env_default_if_needed(
    environ: MutableMapping[str, str],
    key: str,
    val: str | None,
    overwrite: bool = False,
) -> bool:
    """Apply the default dotenv assignment command."""
    return _set_env_value_if_needed(environ, key, val, overwrite)


def _set_env_export_if_needed(
    environ: MutableMapping[str, str],
    key: str,
    val: str | None,
    overwrite: bool = False,
) -> bool:
    """Apply the export dotenv assignment command."""
    return _set_env_value_if_needed(environ, key, val, overwrite)


def _env_files(
    env_file: str, search_path: list[Path], parents: bool, decrypt: bool, errors: bool
) -> Generator[str, Any, None]:
    """expand env_file with the full search path, optionally parents as well"""

    def resolve_file(base_path: Path, name: str, _decrypt: bool) -> str | None:
        """Returns the path to the env file, prioritising the encrypted version if enabled"""

        def readable(path: str) -> bool:
            try:
                with open_env(path):
                    return True
            except OSError as exc:
                if exc.errno in {
                    errno.EACCES,
                    errno.ENOENT,
                    errno.ENOTDIR,
                    errno.EPERM,
                    errno.EISDIR,
                }:
                    return False
                raise

        if _decrypt:
            encrypted_path = os.path.join(base_path, name + ENCRYPTED_EXT)
            if readable(encrypted_path):
                return encrypted_path

        standard_path = os.path.join(base_path, name)
        return standard_path if readable(standard_path) else None

    searched = []
    seen = set()
    found = False

    def record_search(path: Path) -> None:
        if path not in seen:
            searched.append(path)
            seen.add(path)

    for path in search_path:
        try:
            path = path.resolve()
        except FileNotFoundError:
            record_search(path)
            continue
        if not path.is_dir():
            path = path.parent

        for sub_path in [path] + list(path.parents):
            record_search(sub_path)
            env_path = resolve_file(sub_path, env_file, decrypt)
            if env_path is not None:
                found = True
                yield env_path
                break
            elif not parents:
                break

    if errors and not found:
        raise FileNotFoundError(f"{env_file} in {[s.as_posix() for s in searched]}")


@contextlib.contextmanager
def open_env(path: str | Path) -> Generator[BufferedReader, Any, None]:
    """same as open, allow monkeypatch"""
    fp = open(path, "rb")
    try:
        yield fp
    finally:
        fp.close()


ENV_COMMANDS = {
    "export": _set_env_export_if_needed,
}


def _process_line(_lineno: int, string: str, errors: bool, _env_path: Path | None):
    """
    Process a single dotenv line.

    Returns a setter plus parsed key and value. Lines without a parsed key
    return ``None`` for the key, and callers must skip those before invoking
    the setter. Bare keys can return ``None`` for the value; setter helpers
    treat those as no-ops.
    """
    _func, _key, _val = _set_env_default_if_needed, None, None
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
                        f"unknown command at line {_lineno}",
                        file=sys.stderr,
                    )
    return _func, unquote(_key), unquote(_val)


def _process_stream(
    stream: BytesIO,
    environ,
    overwrite,
    errors,
    encoding=DEFAULT_ENCODING,
    env_path=None,
):
    """
    Process dotenv lines and return keys whose values were mutated.
    """
    dotenv_mutated_keys: set[str] = set()
    for lineno, line in enumerate(stream.readlines(), start=1):
        line = line.decode(encoding).strip()
        if line and line[0] != "#":
            func, key, val = _process_line(lineno, line, errors, env_path)
            if func is not None and key is not None:
                # Setter helpers no-op for None values and return True only
                # when environ actually changed.
                if func(environ, key, val, overwrite=overwrite):
                    dotenv_mutated_keys.add(key)
    return dotenv_mutated_keys


def _process_env(
    env_file: str,
    search_path: list[Path],
    environ: MutableMapping[str, str],
    overwrite: bool,
    parents: bool,
    errors: bool,
    working_dirs: bool,
    decrypt: bool,
    password: str | None = None,
    encoding: str = DEFAULT_ENCODING,
) -> tuple[MutableMapping[str, str], set[str]]:
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
    dotenv_mutated_keys: set[str] = set()
    for env_path in _env_files(env_file, search_path, parents, decrypt, errors):
        env_path = Path(env_path).resolve()
        try:
            with open_env(env_path) as f:
                # insert PWD as the container of the env file
                if working_dirs:
                    environ["PWD"] = str(env_path.parent)
                data = f.read()
                if isinstance(data, str):
                    data = data.encode(encoding)
                stream_mutated_keys = _load_stream(
                    BytesIO(data),
                    environ,
                    overwrite,
                    errors,
                    decrypt,
                    password,
                    encoding,
                    env_path,
                )
                dotenv_mutated_keys.update(stream_mutated_keys)
            files_found = True
        except FileNotFoundError:
            files_not_found.append(env_path)
    if errors and not files_found and files_not_found:
        raise FileNotFoundError(
            f"{env_file} as {[s.as_posix() for s in files_not_found]}"
        )
    return environ, dotenv_mutated_keys


def _process_var_reference(
    var_name: str, environ: MutableMapping[str, str], preserve_missing: bool = False
) -> str:
    """Resolve a variable reference, optionally preserving missing references."""
    if preserve_missing and var_name not in environ:
        return f"${var_name}"
    return environ.get(var_name, "")


def _process_shell_var(
    match_obj, environ: MutableMapping[str, str], preserve_missing: bool = False
) -> str:
    """
    Process shell-like variable substitution patterns:
    ${VAR} - Standard variable substitution
    ${VAR:-default} - Use default if VAR is not set
    ${VAR:+value} - Use value only if VAR is set
    """
    # Extract the full match and the variable name
    var_name = match_obj.group(1)

    # Check for modifiers
    if ":" in var_name:
        # Handle ${VAR:-default} or ${VAR:+value} patterns
        parts = _MODIFIER_PATTERN.split(var_name, maxsplit=1)
        if len(parts) == 3:
            var_name, modifier, value = parts

            # Process any nested variable references in the value
            value = _process_nested_vars(value, environ, preserve_missing)

            var_value = _process_var_reference(var_name, environ)
            if modifier == "-" and not var_value or modifier == "+" and var_value:
                # Use default value if variable is not set
                return value
            elif modifier == "-":
                # Variable is set, use its value
                return var_value
            else:  # modifier == "+" and not var_value
                # Variable is not set, return empty string
                return ""

    # Standard variable substitution
    if preserve_missing and var_name not in environ:
        return match_obj.group(0)
    return _process_var_reference(var_name, environ)


MAX_RECURSION_DEPTH = 12


def _substitute_vars(
    value: str, environ: MutableMapping[str, str], preserve_missing: bool = False
) -> str:
    value = _VAR_BRACES_PATTERN.sub(
        lambda m: _process_shell_var(m, environ, preserve_missing), value
    )
    value = _VAR_NO_BRACES_PATTERN.sub(
        lambda m: _process_var_reference(m.group(1), environ, preserve_missing), value
    )
    return value


def _process_nested_vars(
    value: str, environ: MutableMapping[str, str], preserve_missing: bool = False
) -> str:
    for _ in range(MAX_RECURSION_DEPTH):
        new_value = _substitute_vars(value, environ, preserve_missing)
        if new_value == value:
            break
        value = new_value
    return value


def substitute_env_vars(
    value: str,
    environ: MutableMapping[str, str],
    *,
    preserve_missing: bool = False,
) -> str:
    """Resolve dotenv-style variable references in a string."""
    return _process_nested_vars(value, environ, preserve_missing)


def _post_process(
    environ: MutableMapping[str, str], keys: Collection[str] | None = None
) -> MutableMapping[str, str]:
    """
    Post-process the variables using shell-like variable substitution:
    - ${VAR} - Standard variable substitution
    - ${VAR:-default} - Use default if VAR is not set
    - ${VAR:+value} - Use value only if VAR is set
    - $VAR - Variable substitution without braces

    If keys are provided, they must be a collection of strings. They are used
    only as a membership filter for values to update; processing still follows a
    snapshot of environ's insertion order. Filtered values may still resolve
    references against any key in environ, including unfiltered inherited keys.
    """
    items = list(environ.items())
    if keys is not None:
        items = [(key, val) for key, val in items if key in keys]
    for key, val in items:
        if "$" in val:  # Potential variable reference!
            new_val = _process_nested_vars(val, environ)
            if new_val != val:
                environ[key] = new_val
    return environ


def _update_os_env(environ: MutableMapping[str, str]) -> MutableMapping[str, str]:
    """back-populate changed variables to the environment"""
    for env_key, env_val in environ.items():
        if env_val != os.environ.get(env_key):
            os.environ[env_key] = env_val
    return os.environ


def _is_envex_frame(filename: str) -> bool:
    try:
        return Path(filename).resolve().is_relative_to(_PACKAGE_ROOT)
    except (OSError, RuntimeError, ValueError):
        return False


def _default_search_path() -> list[str]:
    import inspect

    frame = inspect.currentframe()
    try:
        frame = frame.f_back if frame else None
        while frame:
            filename = frame.f_code.co_filename
            if (
                filename
                and not filename.startswith("<")
                and not _is_envex_frame(filename)
            ):
                return [".", filename]
            frame = frame.f_back
        return ["."]
    finally:
        del frame


def _decode_filesystem_path(path: bytes) -> str:
    fs_encoding = sys.getfilesystemencoding() or "utf-8"
    return path.decode(fs_encoding, errors="surrogateescape")


def load_env(
    env_file: str | Path | None = None,
    search_path: str | bytes | Path | Iterable[str | bytes | Path] | None = None,
    environ: MutableMapping[str, str] | None = None,
    overwrite: bool = False,
    parents: bool = False,
    update: bool = True,
    errors: bool = False,
    working_dirs: bool = True,
    decrypt: bool = False,
    password: str | None = None,
    encoding: str = DEFAULT_ENCODING,
) -> MutableMapping[str, str]:
    """
    Loads one or more .env files with optional nesting, updating os.environ
    :param env_file: name of the environment file (.env or $ENV default)
    :param search_path: single or list of directories in order of precedence - str, bytes or Path
    :param environ: environment mapping to process
    :param overwrite: whether to overwrite existing values
    :param parents: whether to search upwards until a file is found
    :param update: update os.environ, default=True
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
    env_file = str(env_file)
    environ = _copy_env_mapping(environ)

    # insert this as a useful default
    if working_dirs:
        cwd = current_working_dir()
        if cwd is not None:
            environ["CWD"] = cwd

    # determine where to search
    if search_path is None:
        search_paths = _default_search_path()
    elif isinstance(search_path, Path):
        search_paths = [search_path]
    elif isinstance(search_path, bytes):
        search_paths = _decode_filesystem_path(search_path).split(os.pathsep)
    elif isinstance(search_path, str):
        search_paths = search_path.split(os.pathsep)
    else:
        search_paths = search_path
    # convert to the array of Path for use internally
    resolved_search_path = [
        Path(_decode_filesystem_path(p) if isinstance(p, bytes) else p)
        for p in search_paths
    ]
    # if overwriting, traverse the path in reverse order so the first .env files have priority
    if overwrite:
        resolved_search_path.reverse()

    # Track only keys changed by dotenv input so substitution cannot rewrite
    # unrelated inherited environment values.
    environ, dotenv_mutated_keys = _process_env(
        env_file,
        resolved_search_path,
        environ,
        overwrite,
        parents,
        errors,
        working_dirs,
        decrypt,
        password,
        encoding,
    )
    environ = _post_process(
        environ,
        dotenv_mutated_keys,
    )
    # optionally update the actual environment
    return _update_os_env(environ) if update else environ


def load_stream(
    stream: BytesIO | TextIOBase,
    environ: MutableMapping[str, str] | None = None,
    overwrite: bool = False,
    errors: bool = False,
    decrypt: bool = False,
    password: str | None = None,
    encoding: str = DEFAULT_ENCODING,
    env_path: Path | None = None,
):
    _load_stream(
        stream,
        environ,
        overwrite,
        errors,
        decrypt,
        password,
        encoding,
        env_path,
    )


def _load_stream(
    stream: BytesIO | TextIOBase,
    environ: MutableMapping[str, str] | None = None,
    overwrite: bool = False,
    errors: bool = False,
    decrypt: bool = False,
    password: str | None = None,
    encoding: str = DEFAULT_ENCODING,
    env_path: Path | None = None,
) -> set[str]:
    if environ is None:
        environ = os.environ
    if isinstance(stream, TextIOBase):
        stream.seek(0)
        stream = BytesIO(stream.read().encode(encoding))
    elif password and decrypt:
        stream_pos = stream.tell()
        header = stream.read(len(MAGIC_BYTES))
        stream.seek(stream_pos)
        encrypted_header = header in (MAGIC_BYTES, AUTH_MAGIC_BYTES)
        try:
            stream = decrypt_data(stream, password)
        except DecryptError:
            stream.seek(stream_pos)
            if encrypted_header and (
                _is_encrypted_env_path(env_path)
                or not _looks_like_magic_header_plaintext_dotenv(stream, encoding)
            ):
                raise
    return _process_stream(stream, environ, overwrite, errors, encoding, env_path)


def _is_encrypted_env_path(env_path: Path | None) -> bool:
    return env_path is not None and env_path.name.endswith(ENCRYPTED_EXT)


def _first_dotenv_assignment_key(stream: BytesIO, encoding: str) -> str | None:
    stream_pos = stream.tell()
    try:
        while line := stream.readline():
            line = line.decode(encoding).strip()
            if not line or line.startswith("#"):
                continue
            match = _DOTENV_ASSIGNMENT_PREFIX_PATTERN.match(line)
            return match.group(1) if match is not None else None
    except UnicodeDecodeError:
        return None
    finally:
        stream.seek(stream_pos)
    return None


def _looks_like_plaintext_dotenv(stream: BytesIO, encoding: str) -> bool:
    return _first_dotenv_assignment_key(stream, encoding) is not None


def _is_magic_header_dotenv_key(key: str) -> bool:
    return key.startswith(_MAGIC_DOTENV_KEY_PREFIXES)


def _looks_like_magic_header_plaintext_dotenv(stream: BytesIO, encoding: str) -> bool:
    # This stricter rescue only applies when the stream begins with envex magic
    # bytes and the first real dotenv key follows the documented collision
    # convention, such as SECG_KEY=....
    key = _first_dotenv_assignment_key(stream, encoding)
    return key is not None and _is_magic_header_dotenv_key(key)


load_dotenv = load_env
