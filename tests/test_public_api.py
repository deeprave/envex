# -*- coding: utf-8 -*-
from io import BytesIO

import envex
from envex.env_crypto import decrypt_data, encrypt_data, DecryptError, EncryptError
from envex.env_hvac import SecretsManager


def test_public_exports_include_core_helpers():
    assert {
        "load_env",
        "load_dotenv",
        "Env",
        "env",
        "encrypt_data",
        "decrypt_data",
        "EncryptError",
        "DecryptError",
        "SecretsManager",
    } <= set(envex.__all__)


def test_public_exports_reference_core_helpers():
    assert envex.encrypt_data is encrypt_data
    assert envex.decrypt_data is decrypt_data
    assert envex.EncryptError is EncryptError
    assert envex.DecryptError is DecryptError
    assert envex.SecretsManager is SecretsManager


def test_public_crypto_exports_round_trip():
    password = "public-api-test-password"
    encrypted = envex.encrypt_data(BytesIO(b"PUBLIC_API=ok\n"), password)

    assert envex.decrypt_data(encrypted, password).getvalue() == b"PUBLIC_API=ok\n"
