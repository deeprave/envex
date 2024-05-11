#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Seal or [-u] unseal a vault
"""
import logging
import os
import textwrap

import hvac

description = """\
Seal or [-u] unseal a vault
Uses environment variables:
  VAULT_ADDR - vault server url
  VAULT_CACERT - optional path to CA public certificate
  VAULT_TOKEN  - vault token with sufficient privilege
  VAULT_UNSEAL_KEYS <value,value,vault> - keys to unseal (if unsealing)
"""


def expand(path: str):
    return os.path.expandvars(os.path.expanduser(path))


def trim_indent(text):
    lines = text.splitlines()
    if len(lines) > 0:
        leading_spaces = len(lines[0]) - len(lines[0].lstrip())
        trimmed_lines = [line[leading_spaces:] for line in lines]
        return "\n".join(trimmed_lines)
    return text


def main():
    import argparse

    class CustomFormatter(argparse.RawDescriptionHelpFormatter):
        def _split_lines(self, text, width):
            return textwrap.wrap(text, width=250)

    parser = argparse.ArgumentParser(description=description, formatter_class=CustomFormatter)
    parser.add_argument(
        "-a",
        "--address",
        default=os.getenv("VAULT_ADDR"),
        help="Override vault url/address",
    )
    parser.add_argument(
        "-t",
        "--token",
        default=os.getenv("VAULT_TOKEN"),
        help="Override token for vault access",
    )
    parser.add_argument(
        "-C",
        "--cacert",
        default=os.getenv("VAULT_CACERT"),
        help="Override path to CA cert key",
    )
    parser.add_argument(
        "-k",
        "--keys",
        default=os.getenv("VAULT_UNSEAL_KEYS"),
        help="Comma separated list of unseal keys",
    )
    action_group = parser.add_mutually_exclusive_group(required=False)
    action_group.add_argument("-s", "--seal", action="store_true", default=False, help="Seal the vault")
    action_group.add_argument("-u", "--unseal", action="store_true", default=False, help="Unseal the vault")

    args = parser.parse_args()

    client = hvac.Client(url=args.address, token=args.token, verify=expand(args.cacert) or False)

    try:
        if args.seal:
            response = client.sys.seal()
            if response.status_code >= 300:
                response.raise_for_status()

        if args.unseal:
            keys = args.keys.split(",")
            if len(keys) < int(client.seal_status.get("t")):
                raise ValueError(f'Require at least {client.seal_status.get("t")} keys')

            client.sys.submit_unseal_keys(keys=keys)

        status = client.seal_status
        print(
            trim_indent(
                f"Vault Status: {'Sealed' if status['sealed'] == 'true' else 'Unsealed'} "
                f"type={status['type']} shares={status['t']}/{status['n']}"
            )
        )

    except Exception as e:
        logging.error(f"{e.__class__.__name__}: {e}")


if __name__ == "__main__":
    main()
