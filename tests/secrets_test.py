#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os

from envex.lib.hvac_env import SecretsManager


def store_secrets(sm: SecretsManager, path: str, data: dict | str):
    if isinstance(data, dict):
        for k, v in data.items():
            store_secrets(sm, sm.join(path, k), v)
    else:
        sm.set_secret(path, data)


def clean_secrets(sm: SecretsManager, path: str):
    # this auto-deletes all subitems as well
    for secret in sm.list_secrets(path):
        sm.delete_secret(sm.join(path, secret))
    sm.delete_secret(path)


def list_secrets(sm: SecretsManager, path: str):
    print(f"Listing secrets in {path}")
    found = False
    for secret in sm.list_secrets(path):
        value = sm.get_secret(sm.join(path, secret))
        print(f"  {secret}={value}")
        found = True
    if not found:
        print("  No secrets found")


def main():
    sm = SecretsManager(verify=os.getenv("VAULT_CACERT"), base_path="test", engine="kv")
    clean_secrets(sm, "database")

    list_secrets(sm, "database")

    data = {"username": "hellothere", "password": "thisissecret"}
    store_secrets(sm, "database", data)

    list_secrets(sm, "database")

    clean_secrets(sm, "database")

    list_secrets(sm, "database")


if __name__ == "__main__":
    main()
