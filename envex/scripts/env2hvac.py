#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Import variables from a .env file to hashicorp vault.
"""

import logging
import os

import envex
from envex.env_hvac import SecretsManager
from envex.scripts.lib.log import fatal

logging.captureWarnings(True)


def expand(p: str):
    return os.path.expandvars(os.path.expanduser(p))


def _is_forbidden(exc: Exception) -> bool:
    return exc.__class__.__name__ == "Forbidden" and exc.__class__.__module__.startswith(
        "hvac."
    )


def _load_existing_secrets(sm: SecretsManager, path: str) -> None:
    try:
        sm.get_secrets(path)
    except Exception as exc:
        if not _is_forbidden(exc):
            raise
        logging.warning(
            "Cannot read existing Vault data; importing without preserving existing "
            "values"
        )


def _validate_input_files(files: list[str]) -> list[str]:
    expanded_files = []
    for filename in files:
        expanded = expand(filename)
        if not os.path.isfile(expanded):
            fatal(f"{expanded}: input file does not exist", exc_info=False, exitcode=1)
        try:
            with open(expanded, "rb"):
                pass
        except OSError as exc:
            fatal(
                f"{expanded}: input file is not readable: {exc.strerror}",
                exc_info=False,
                exitcode=1,
            )
        expanded_files.append(expanded)
    return expanded_files


def handler(
    files: list[str],
    url: str | None = None,
    token: str | None = None,
    cert: tuple[str, str] | None = None,
    verify: bool | str | None = None,
    unseal: str | None = None,
    namespace: str | None = None,
    environ: str | None = None,
):
    files = _validate_input_files(files)
    sm = SecretsManager(url=url, token=token, cert=cert, verify=verify)
    unsealed = False
    try:
        if unseal:
            sm.unseal(keys=unseal.split(","), root_token=token)
            unsealed = True

        client = sm.client
        if client is None:
            fatal("Can't connect or authenticate with Vault", exc_info=False, exitcode=1)

        if client.seal_status["sealed"]:
            fatal("Vault is currently sealed", exc_info=False, exitcode=4)

        path = sm.join(namespace, environ)
        _load_existing_secrets(sm, path)
        for filename in files:
            try:
                env = envex.Env(
                    readenv=True,
                    environ={},
                    env_file=filename,
                    update=False,
                    errors=False,
                )
                count = 0
                secrets = {}
                for k, v in env.items():
                    if k not in ("CWD", "PWD"):
                        if v is not None:
                            secrets[k] = v
                            count += 1
                if secrets:
                    sm.set_secrets(path, values=secrets)
                logging.info(
                    f"Added or updated {count} items from {filename} to '{path}'"
                )
            except IOError as e:
                logging.error(f"{filename}: {e.__class__.__name__}", exc_info=True)
    finally:
        # reseal the vault
        if unsealed:
            sm.seal()


def main():
    import argparse

    from envex.scripts.lib.decr_action import Decrement
    from envex.scripts.lib.log import config as log_config
    from envex.scripts.lib.log import log_get_level, log_set_level

    log_config()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-n",
        "--namespace",
        type=str,
        default="myapp",
        help="Namespace or application name",
    )
    parser.add_argument(
        "-e",
        "--environ",
        type=str,
        default=None,
        help="The code environment used to create or update variables",
    )
    parser.add_argument(
        "-a",
        "--address",
        type=str,
        default=None,
        help="The address/url of the hashicorp vault server",
    )
    parser.add_argument(
        "-t",
        "--token",
        type=str,
        default=None,
        help="The token used to authenticate to hashicorp vault",
    )
    parser.add_argument(
        "-u",
        "--unseal",
        default="",
        help="Unseal/reseal the vault with the provided comma-separated list of key",
    )
    parser.add_argument(
        "-c",
        "--cert",
        type=str,
        default=None,
        help="Client cert (if any)",
    )
    parser.add_argument(
        "-k",
        "--key",
        type=str,
        default=None,
        help="Client cert key (if any)",
    )
    verify_group = parser.add_mutually_exclusive_group(required=False)
    verify_group.add_argument(
        "-N",
        "--noverify",
        dest="verify",
        action="store_false",
        default=None,
        help="Disable server certificate verification",
    )
    verify_group.add_argument(
        "-C",
        "--cacert",
        dest="verify",
        default=None,
        help="Path to a custom CA certificate (do not use with -N)",
    )
    parser.add_argument(
        "files",
        nargs="+",
        help="Filename(s) from which to read variables.",
    )
    default_level = log_get_level()
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=default_level,
        dest="verbose",
        help="Verbose output (specify multiple times for more verbosity)",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action=Decrement,
        default=default_level,
        dest="verbose",
        help="Verbose output (specify multiple times for more verbosity)",
    )
    args = parser.parse_args()
    certs = (args.cert, args.key) if args.cert and args.key else None

    log_set_level(args.verbose)

    handler(
        args.files,
        url=args.address,
        token=args.token,
        cert=certs,
        verify=args.verify,
        unseal=args.unseal,
        namespace=args.namespace,
        environ=args.environ,
    )


if __name__ == "__main__":
    main()
