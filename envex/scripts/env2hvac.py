#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Import variables from a .env file to hashicorp vault.
"""

import logging
import os

import envex
from envex.env_hvac import SecretsManager

logging.captureWarnings(True)


def expand(p: str):
    return os.path.expandvars(os.path.expanduser(p))


def handler(
    files: list[str],
    url: str = None,
    token: str = None,
    cert: tuple = None,
    verify: bool | str = True,
    unseal: str = None,
    namespace: str = None,
    environ: str = None,
):
    sm = SecretsManager(url=url, token=token, cert=cert, verify=verify)
    if unseal:
        sm.unseal(keys=unseal.split(","), root_token=token)

    if sm.client is None:
        # noinspection PyArgumentList
        logging.fatal(
            "Can't connect or authenticate with Vault", exc_info=False, exitcode=1
        )

    if sm.client.seal_status["sealed"]:
        # noinspection PyArgumentList
        logging.fatal("Vault is currently sealed", exc_info=False, exitcode=4)

    try:
        path = sm.join(namespace, environ)
        for filename in files:
            filename = expand(filename)
            try:
                env = envex.Env(
                    readenv=True,
                    environ={},
                    env_file=filename,
                    update=False,
                    errors=False,
                    # pass these on in case we need them for completion
                    url=url,
                    token=token,
                    cert=cert,
                    verify=verify,
                    base_path=path,
                )
                count = 0
                secrets = {}
                for k, v in env.items():
                    if k not in ("CWD", "PWD"):
                        key = sm.join(path, k)
                        if v is not None:
                            secrets[key] = v
                            count += 1
                logging.info(
                    f"Added or updated {count} items from {filename} to '{path}'"
                )
            except IOError as e:
                logging.error(f"{filename}: {e.__class__.__name__}", exc_info=True)
    finally:
        # reseal the vault
        if unseal:
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
    parser.add_argument(
        "-N",
        "--noverify",
        dest="verify",
        action="store_false",
        default=True,
        help="Disable server certificate verification",
    )
    parser.add_argument(
        "-C",
        "--cacert",
        dest="verify",
        default=True,
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
