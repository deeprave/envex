# tests/test_env_crypto.py

import builtins
import importlib.util
from io import BytesIO, StringIO, UnsupportedOperation
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


def test_encrypt_data_accepts_non_seekable_text_stream(password):
    class NonSeekableTextStream:
        def __init__(self, value):
            self._stream = StringIO(value)

        def seek(self, *_args):
            raise UnsupportedOperation("not seekable")

        def read(self):
            return self._stream.read()

    encrypted = encrypt_data(NonSeekableTextStream("VALUE=ok\n"), password)

    assert decrypt_data(encrypted, password).getvalue() == b"VALUE=ok\n"


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


def test_encrypt_data_rejects_already_encrypted_input_from_current_position(password):
    input_enc = encrypt_data(BytesIO(b"Some Test data data"), password)
    input_enc.seek(1)

    with pytest.raises(EncryptError):
        encrypt_data(input_enc, password)

    assert input_enc.tell() == 1


def test_encrypt_data_rejects_assignment_looking_authenticated_output(
    password, monkeypatch
):
    def token_bytes(size):
        if size == env_crypto.SALT_LENGTH:
            return b"=\n" + b"s" * (size - 2)
        if size == env_crypto.GCM_NONCE_LENGTH:
            return b"n" * size
        return b"x" * size

    monkeypatch.setattr(env_crypto.secrets, "token_bytes", token_bytes)
    encrypted = encrypt_data(BytesIO(b"Some Test data data"), password)

    assert encrypted.getvalue().startswith(b"SECG=\n")
    with pytest.raises(EncryptError):
        encrypt_data(encrypted, password)


def test_encrypt_data_rejects_assignment_looking_output_with_wrong_password(
    password, monkeypatch
):
    def token_bytes(size):
        if size == env_crypto.SALT_LENGTH:
            return b"_KEY=value\n" + b"s" * (size - 11)
        if size == env_crypto.GCM_NONCE_LENGTH:
            return b"n" * size
        return b"x" * size

    monkeypatch.setattr(env_crypto.secrets, "token_bytes", token_bytes)
    encrypted = encrypt_data(BytesIO(b"Some Test data data"), password)

    assert encrypted.getvalue().startswith(b"SECG_KEY=value\n")
    with pytest.raises(EncryptError):
        encrypt_data(encrypted, "wrong-password")


@pytest.mark.parametrize(
    "line_prefix,key",
    [
        ("", "SECG_KEY"),
        ("", "SECF_KEY"),
        ("  ", "SECG_KEY"),
    ],
)
def test_encrypt_data_accepts_plaintext_dotenv_magic_prefix_keys(
    password, line_prefix, key
):
    # This length makes both magic prefixes structurally plausible containers.
    input_data = f"{line_prefix}{key}={'x' * 42}\n".encode()
    encrypted = encrypt_data(BytesIO(input_data), password)

    assert decrypt_data(encrypted, password).getvalue() == input_data


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


def test_encrypt_data_rejects_legacy_encrypted_input(password):
    encrypted_data = legacy_encrypt_data(b"LEGACY_ENCRYPTED_DATA", password)

    with pytest.raises(EncryptError):
        encrypt_data(encrypted_data, password)


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
