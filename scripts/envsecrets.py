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
from pathlib import Path
from string import Template
from typing import Union

from envex.dot_env import load_env
from envex.env_hvac import SecretsManager

SECRET_MARK = "|"


# noinspection DuplicatedCode
def read_env(
    envfile: Union[str, Path, None],
    search=None,
    parents=False,
    useenv=False,
    working_dirs=False,
):
    """Read the entire .env file"""
    if search is None:
        search_path = [Path.cwd()]
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


def cache_regex(rx: str) -> re.Pattern:
    if not hasattr(cache_regex, "cache"):
        cache_regex.cache = {}
    cache = cache_regex.cache
    if rx not in cache:
        cache[rx] = re.compile(rx)
    return cache[rx]


def env_match(var, regexlist, is_value=False):
    if regexlist:
        for regex in regexlist:
            if is_value and var == regex or not is_value and cache_regex(regex).match(var):
                break
        else:
            return False
    return True


def subst(environ, lines) -> list:
    """post-process the variables using ${substitutions}"""
    data = []

    def do_subst(value: str) -> str:
        if all(v in value for v in ("${", "}")):  # looks like template
            # ignore anything that doesn't resolve, don't throw an exception.
            value = Template(value).safe_substitute(environ)
        return value

    for line in lines:
        if isinstance(line, tuple):
            var, val, secret = line[0], do_subst(line[1]), line[2]
            environ[var] = val  # update the environment
            data.append((var, val, secret))
        else:
            data.append(line)

    return data


def parse_template(env, template, with_comments=False):
    length = len(SECRET_MARK)
    lines = []
    with open(template, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                if with_comments:
                    lines.append(line)
            else:
                secret = False
                if line.startswith(SECRET_MARK):
                    line = line[length:]
                    secret = True
                parts = line.split("=", maxsplit=1)
                if len(parts) == 1:
                    var = parts[0]
                    val = env.get(parts[0], "")
                else:
                    var, val = parts[0], parts[1]
                lines.append((var, val, secret))
    return lines


def output_result(lines: list, outputfile: str, empty: bool) -> dict:
    secrets = {}

    def writelines(fp, name, _lines):
        linecount = 0
        for line in _lines:
            if isinstance(line, tuple):
                var, val, secret = line[0], line[1], line[2]
                if val or empty:
                    if secret:
                        secrets[var] = val
                        continue
                    out = f"{var}={val}"
                else:
                    continue
            else:
                out = line
            print(out, file=fp)
            linecount += 1
        print(
            f"{name}: {linecount} line{'' if linecount == 1 else 's'} written",
            file=sys.stderr,
        )

    if outputfile == "-":
        writelines(sys.stdout, "<stdout>", lines)
    else:
        with open(outputfile, "w+") as f:
            writelines(f, outputfile, lines)

    return secrets


def secrets_manager(**kwargs) -> SecretsManager:
    sm = SecretsManager(**kwargs)
    if not sm.client:
        error("secrets manager not available")
    elif sm.sealed:
        error("secrets manager is sealed", 2)
    return sm


def create_or_update_secrets(secrets, key, cert, verbose):
    certpath = Path(cert).resolve().as_posix() if cert else None
    sm = secrets_manager(verify=certpath)
    sm.set_secrets(key, values=secrets)
    if verbose:
        import json

        data = sm.get_secrets(key) or secrets
        print(f"{sm.base_path}/{key}:")
        for s in json.dumps(data, indent=4).splitlines():
            print(f"    {s}")


def main(args):
    search = args.search.split(",") if args.search else None
    env = read_env(args.dotenv, search=search, parents=args.parents, useenv=args.environ)
    data = parse_template(env, args.template, args.comments)
    rendered = subst(env, data)
    if secrets := output_result(rendered, args.output, args.empty):
        create_or_update_secrets(secrets, args.key, args.cert, args.verbose)


def error(message, exitcode=None):
    print(f"{'ERROR' if exitcode else 'WARNING'}: {message}", file=sys.stderr)
    if exitcode is not None:
        exit(exitcode)


if __name__ == "__main__":
    prog = Path(sys.argv[0]).resolve(strict=True)
    parser = argparse.ArgumentParser(prog=prog.name, description=__doc__)

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
        default=output_default,
        help=f'output to this file (default="{output_default}")',
    )

    argv = parser.parse_args()
    # print(argv)

    main(argv)
