#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Import variables from a .env file to hashicorp vault.
"""
import logging
import os

import hvac

import envex

logging.captureWarnings(True)


def main(
    files: list[str],
    url: str = None,
    token: str = None,
    cert: tuple = None,
    verify: bool | str = True,
    unseal: str = None,
    namespace: str = None,
    environ: str = None,
):
    client = hvac.Client(url=url, token=token, cert=cert, verify=verify)
    try:
        if unseal:
            client.sys.submit_unseal_keys(keys=unseal.split(","))
        if not client.is_authenticated():
            # noinspection PyArgumentList
            logging.fatal("Can't connect or authenticate with Vault", exitcode=1)
            return
    except hvac.v1.exceptions.VaultDown as e:
        # sealed?
        if client.seal_status["sealed"]:
            # noinspection PyArgumentList
            logging.fatal("Vault is currently sealed", exitcode=4)
        # noinspection PyArgumentList
        logging.fatal(f"Unknown exception connecting with Vault: {e}", exitcode=1)

    def expand(p: str):
        return os.path.expandvars(os.path.expanduser(p))

    try:
        path = f"{namespace}/{environ}" if environ else "{namespace}"
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
                items = {k: v for k, v in env.items() if k not in ("CWD", "PWD")}
                client.secrets.kv.v2.create_or_update_secret(
                    path=path,
                    secret=items,
                    cas=None,
                    mount_point="secret",
                )
                logging.info(f"Added or updated {len(items)} items from {filename} to '{path}'")
                # comma_nl = ",\n    "
                # print(f"[\n{comma_nl.join(items.keys())}\n]\n")
            except IOError as e:
                logging.error(f"{filename}: {e.__class__.__name__} - {e}")
    finally:
        # reseal the vault
        if unseal:
            client.sys.seal()


if __name__ == "__main__":
    import argparse

    from scripts.lib.decr_action import Decrement
    from scripts.lib.log import config as log_config
    from scripts.lib.log import log_get_level, log_set_level

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

    main(
        args.files,
        url=args.address,
        token=args.token,
        cert=certs,
        verify=args.verify,
        unseal=args.unseal,
        namespace=args.namespace,
        environ=args.environ,
    )
