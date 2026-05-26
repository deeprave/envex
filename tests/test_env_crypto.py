# tests/test_env_crypto.py

import builtins
import importlib.util
from io import BytesIO, StringIO
from pathlib import Path

import pytest
import envex.env_crypto as env_crypto
from envex.env_crypto import encrypt_data, decrypt_data, EncryptError, DecryptError


@pytest.fixture
def password():
    return "#pretEnD_stR0ng_pAs$woRd"


def test_encrypt_data_success(password):
    input_data = BytesIO(b"test data")
    result = encrypt_data(input_data, password)
    assert isinstance(result, BytesIO)
    assert result.getvalue() != b"test data"  # Ensure data is encrypted
    assert result.getvalue().startswith(env_crypto.AUTH_MAGIC_BYTES)


def test_encrypt_decrypt_unicode_(password):
    test_string = "\u00a9 test data \u06a2"
    input_data = StringIO(test_string)
    result = encrypt_data(input_data, password, "utf-8")
    assert isinstance(result, BytesIO)
    assert result.getvalue() != test_string
    result = decrypt_data(result, password)
    assert isinstance(result, BytesIO)
    assert result.getvalue().decode("utf-8") == test_string


def test_encrypt_data_no_password():
    input_data = BytesIO(b"test data")
    password = ""
    with pytest.raises(EncryptError):
        encrypt_data(input_data, password)


def test_encrypt_data_already_encrypted(password):
    input_data = BytesIO(b"Some Test data data")
    input_enc = encrypt_data(input_data, password)
    with pytest.raises(EncryptError):
        encrypt_data(input_enc, password)


def test_encrypt_data_value_error_raises_encrypt_error(password, monkeypatch):
    class BrokenCipher:
        def encrypt_and_digest(self, _data):
            raise ValueError("cipher failed")

    monkeypatch.setattr(env_crypto.AES, "new", lambda *args, **kwargs: BrokenCipher())
    with pytest.raises(EncryptError) as e:
        encrypt_data(BytesIO(b"test data"), password)
    assert str(e.value) == "Encryption failed"


def test_crypto_import_fallback_raises_clear_errors(monkeypatch):
    real_import = builtins.__import__

    def blocked_crypto_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name.startswith("Crypto"):
            raise ImportError("blocked crypto import")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", blocked_crypto_import)
    module_path = Path(env_crypto.__file__)
    spec = importlib.util.spec_from_file_location(
        "env_crypto_without_crypto", module_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    with pytest.raises(module.EncryptError, match="Encryption not supported"):
        module.encrypt_data(BytesIO(b"test data"), "password", encoding="utf-8")
    with pytest.raises(module.DecryptError, match="Decryption not supported"):
        module.decrypt_data(BytesIO(b"test data"), "password")


def test_encrypt_empty_data():
    input_data = BytesIO(b"")
    password = "strongpassword123"
    result = encrypt_data(input_data, password)
    assert isinstance(result, BytesIO)
    assert len(result.getvalue()) > 0


def test_encrypt_large_data(password):
    input_data = BytesIO(b"a" * 10**6)
    result = encrypt_data(input_data, password)
    assert isinstance(result, BytesIO)
    assert result.getvalue() != b"a" * 10**6
    assert input_data.getvalue() == decrypt_data(result, password).getvalue()


def test_valid_decryption(password):
    encrypted_stream = encrypt_data(BytesIO(b"VALID_ENCRYPTED_DATA"), password)
    result = decrypt_data(encrypted_stream, password)
    assert isinstance(result, BytesIO)
    assert result.getvalue() == b"VALID_ENCRYPTED_DATA"


def test_tampered_ciphertext_fails_authentication(password):
    encrypted_data = bytearray(
        encrypt_data(BytesIO(b"VALID_ENCRYPTED_DATA"), password).getvalue()
    )
    encrypted_data[-1] ^= 1
    with pytest.raises(DecryptError) as e:
        decrypt_data(BytesIO(encrypted_data), password)
    assert str(e.value) == "Incorrect password or invalid data"


def test_invalid_magic_bytes(password):
    encrypted_stream_with_invalid_magic_bytes = BytesIO(b"DATA_WITH_INVALID_MAGIC_BYTES")

    with pytest.raises(DecryptError) as e:
        decrypt_data(encrypted_stream_with_invalid_magic_bytes, password)
    assert "does not look to be encrypted" in str(e.value)


def test_truncated_authenticated_stream_raises_decrypt_error(password):
    encrypted_stream = BytesIO(env_crypto.AUTH_MAGIC_BYTES + b"too-short")

    with pytest.raises(DecryptError) as e:
        decrypt_data(encrypted_stream, password)
    assert "invalid data" in str(e.value)


def test_invalid_password(password):
    data = b"VALID_ENCRYPTED_DATA"
    encrypted_data = encrypt_data(BytesIO(data), password)

    with pytest.raises(DecryptError) as e:
        decrypt_data(encrypted_data, "wrong_password")
    assert "Incorrect password or invalid data" in str(e.value)


def legacy_encrypt_data(data: bytes, password: str) -> BytesIO:
    salt = b"salt_for_tests_1"
    iv = b"iv_for_tests__01"
    key, _ = env_crypto.generate_key_from_password(password, salt)
    cipher = env_crypto.AES.new(key, env_crypto.AES.MODE_CBC, iv)
    return BytesIO(
        env_crypto.MAGIC_BYTES + salt + iv + cipher.encrypt(env_crypto._pad(data))
    )


def test_legacy_cbc_decryption_remains_supported(password):
    encrypted_data = legacy_encrypt_data(b"LEGACY_ENCRYPTED_DATA", password)
    result = decrypt_data(encrypted_data, password, allow_legacy=True)
    assert result.getvalue() == b"LEGACY_ENCRYPTED_DATA"


def test_legacy_cbc_decryption_requires_opt_in(password):
    encrypted_data = legacy_encrypt_data(b"LEGACY_ENCRYPTED_DATA", password)
    with pytest.raises(DecryptError) as e:
        decrypt_data(encrypted_data, password)
    assert str(e.value) == "Legacy AES-CBC data requires explicit legacy decryption"


def test_downgraded_gcm_header_does_not_fall_back_to_legacy(password):
    encrypted_data = bytearray(encrypt_data(BytesIO(b"test"), password).getvalue())
    encrypted_data[: len(env_crypto.AUTH_MAGIC_BYTES)] = env_crypto.MAGIC_BYTES
    with pytest.raises(DecryptError) as e:
        decrypt_data(BytesIO(encrypted_data), password)
    assert str(e.value) == "Legacy AES-CBC data requires explicit legacy decryption"


def test_legacy_cbc_padding_failures_are_generic(password):
    encrypted_data = bytearray(
        legacy_encrypt_data(b"LEGACY_ENCRYPTED_DATA", password).getvalue()
    )
    encrypted_data[-1] ^= 1
    with pytest.raises(DecryptError) as e:
        decrypt_data(BytesIO(encrypted_data), password, allow_legacy=True)
    assert str(e.value) == "Incorrect password or invalid data"


def test_empty_stream(password):
    empty_stream = BytesIO()
    with pytest.raises(DecryptError):
        decrypt_data(empty_stream, password)
