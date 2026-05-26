#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Populate vault with secrets from .env files and generate .env file with non-secrets.
Input:
  A .env file containing all values, secrets or otherwise.
  A "template" file that contains the variables to be exported,
   sensitive/secret values must be prefixed with a pipe | character
Output:

"""

import argparse
import re
import sys
from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from envex.dot_env import load_env, substitute_env_vars
from envex.env_hvac import SecretsManager
from envex.paths import current_working_dir

SECRET_MARK = "|"
_SUBSTITUTION_PATTERN = re.compile(r"\$\{|\$[a-zA-Z_][a-zA-Z0-9_]*")


@dataclass(frozen=True)
class PublicTemplateValue:
    var: str
    val: str


@dataclass(frozen=True)
class SecretTemplateValue:
    var: str
    val: str


RenderedTemplateLine = str | PublicTemplateValue | SecretTemplateValue


class SecretsManagerError(RuntimeError):
    def __init__(self, message: str, exitcode: int):
        super().__init__(message)
        self.exitcode = exitcode


def _default_search_path(envfile: str | Path | None) -> list[str | Path]:
    cwd = current_working_dir()
    if cwd is not None:
        return [cwd]
    if envfile is not None and Path(envfile).is_absolute():
        return [Path(envfile)]
    error("current working directory is unavailable; skipping default dotenv search path")
    return []


# noinspection DuplicatedCode
def read_env(
    envfile: str | Path | None,
    search=None,
    parents=False,
    useenv=False,
    working_dirs=False,
):
    """Read the entire .env file"""
    if search is None:
        search_path = _default_search_path(envfile)
    else:
        search_path = set()
        for path in [p.split(",") for p in search]:
            for p in path:
                search_path.add(Path(p).resolve(strict=True))
        search_path = list(search_path)
    environ = None if useenv else {}
    return load_env(
        envfile,
        search_path=search_path,
        environ=environ,
        parents=parents,
        update=False,
        working_dirs=working_dirs,
    )


def subst(
    environ: MutableMapping[str, str],
    lines: Sequence[RenderedTemplateLine],
) -> list[RenderedTemplateLine]:
    """Post-process template values using dotenv-style variable substitution."""
    data: list[RenderedTemplateLine] = []

    def do_subst(value: str) -> str:
        if _SUBSTITUTION_PATTERN.search(value):
            value = substitute_env_vars(value, environ, preserve_missing=True)
        return value

    for line in lines:
        if isinstance(line, PublicTemplateValue):
            val = do_subst(line.val)
            environ[line.var] = val  # update the environment
            data.append(PublicTemplateValue(line.var, val))
        elif isinstance(line, SecretTemplateValue):
            val = do_subst(line.val)
            environ[line.var] = val  # update the environment
            data.append(SecretTemplateValue(line.var, val))
        else:
            data.append(line)

    return data


def parse_template(
    env: Mapping[str, str], template: str | Path, with_comments=False
) -> list[RenderedTemplateLine]:
    length = len(SECRET_MARK)
    lines: list[RenderedTemplateLine] = []
    with open(template, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                if with_comments:
                    lines.append(line)
            else:
                if line.startswith(SECRET_MARK):
                    line = line[length:]
                    value_type = SecretTemplateValue
                else:
                    value_type = PublicTemplateValue
                parts = line.split("=", maxsplit=1)
                if len(parts) == 1:
                    var = parts[0]
                    val = env.get(parts[0], "")
                else:
                    var, val = parts[0], parts[1]
                lines.append(value_type(var, val))
    return lines


def prepare_public_output_and_secrets(
    lines: Sequence[RenderedTemplateLine], empty: bool
) -> tuple[list[str], dict[str, str]]:
    """Format public output lines and extract secret values from rendered template lines."""
    output_lines: list[str] = []
    secrets: dict[str, str] = {}

    for line in lines:
        if isinstance(line, PublicTemplateValue):
            if not empty and not line.val:
                continue
            output_lines.append(f"{line.var}={line.val}")
        elif isinstance(line, SecretTemplateValue):
            if not empty and not line.val:
                continue
            secrets[line.var] = line.val
        else:
            output_lines.append(line)

    return output_lines, secrets


def output_result(public_lines: list[str], outputfile: str) -> None:
    def writelines(fp, name, lines):
        for public_line in lines:
            # Secret template values are excluded before this writer is called.
            # codeql[py/clear-text-storage-sensitive-data]
            fp.write(f"{public_line}\n")
        linecount = len(lines)
        print(
            f"{name}: {linecount} line{'' if linecount == 1 else 's'} written",
            file=sys.stderr,
        )

    if outputfile == "-":
        writelines(sys.stdout, "<stdout>", public_lines)
    else:
        with open(outputfile, "w+") as f:
            writelines(f, outputfile, public_lines)


def secrets_manager(**kwargs) -> SecretsManager:
    sm = SecretsManager(**kwargs)
    if not sm.client:
        raise SecretsManagerError("secrets manager not available", 1)
    elif sm.sealed:
        raise SecretsManagerError("secrets manager is sealed", 2)
    return sm


def create_or_update_secrets(secrets, key, cert, verbose):
    certpath = Path(cert).resolve().as_posix() if cert else None
    sm = secrets_manager(verify=certpath)
    sm.set_secrets(key, values=secrets)
    if verbose:
        print(
            f"{len(secrets)} secret{'' if len(secrets) == 1 else 's'} updated at "
            f"{sm.base_path}/{key}",
            file=sys.stderr,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="envsecrets", description=__doc__)

    scripts = Path(__file__).parent
    dotenv_default = ".env"
    template_default = scripts / "template.env"
    output_default = "docker.env"
    key_default = "app"

    parser.add_argument(
        "-e",
        "--environ",
        action="store_true",
        default=False,
        help="add OS environment to the list",
    )
    parser.add_argument(
        "-d",
        "--dotenv",
        action="store",
        default=dotenv_default,
        help=f"name of dot.env file (default={dotenv_default})",
    )
    parser.add_argument(
        "-s",
        "--search",
        action="store",
        nargs="?",
        help="search path(s) for env file (comma separated)",
    )
    parser.add_argument(
        "-p",
        "--parents",
        action="store_true",
        default=False,
        help="search parents until a dotenv file is found",
    )
    parser.add_argument(
        "-t",
        "--template",
        action="store",
        default=template_default,
        help=f'template file to use to use (default="{template_default}")',
    )
    parser.add_argument(
        "-c",
        "--comments",
        action="store_true",
        default=False,
        help="copy comments to output",
    )
    parser.add_argument(
        "-k",
        "--key",
        action="store",
        default=key_default,
        help=f'key for kv pairs stored in vault (default="{key_default}")',
    )
    parser.add_argument(
        "-E",
        "--empty",
        action="store_true",
        default=False,
        help="render or save empty values",
    )
    parser.add_argument(
        "-C",
        "--cert",
        action="store",
        default=None,
        help="path to Vault CA certificate chain file",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        help="verbose output",
    )
    parser.add_argument(
        "output",
        action="store",
        nargs="?",
        default=output_default,
        help=f'output to this file (default="{output_default}")',
    )
    return parser


def run(args: argparse.Namespace) -> None:
    try:
        search = args.search.split(",") if args.search else None
        env = read_env(
            args.dotenv, search=search, parents=args.parents, useenv=args.environ
        )
        data = parse_template(env, args.template, args.comments)
        rendered = subst(env, data)
        public_lines, secrets = prepare_public_output_and_secrets(rendered, args.empty)
        if secrets:
            create_or_update_secrets(secrets, args.key, args.cert, args.verbose)
        output_result(public_lines, args.output)
    except SecretsManagerError as exc:
        error(str(exc), exc.exitcode)


def main(argv: Sequence[str] | argparse.Namespace | None = None) -> None:
    args = (
        argv if isinstance(argv, argparse.Namespace) else build_parser().parse_args(argv)
    )
    run(args)


def error(message, exitcode=None):
    print(f"{'ERROR' if exitcode else 'WARNING'}: {message}", file=sys.stderr)
    if exitcode is not None:
        exit(exitcode)


if __name__ == "__main__":
    main()
