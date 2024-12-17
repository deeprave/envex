# tests/test_env_crypto.py

from io import BytesIO, StringIO

import pytest
from envex.env_crypto import encrypt_data, decrypt_data, EncryptError, DecryptError


@pytest.fixture
def password():
    # Provide a test password fixture
    return "#pretEnD_stR0ng_pAs$woRd"


@pytest.fixture
def incorrect_password():
    # Provide an incorrect test password
    return "wrong_password"


@pytest.fixture
def encrypted_stream_with_invalid_magic_bytes():
    # Mock BytesIO stream with invalid magic bytes
    return BytesIO(b"DATA_WITH_INVALID_MAGIC_BYTES")


@pytest.mark.unit
def test_encrypt_data_success(password):
    input_data = BytesIO(b"test data")
    result = encrypt_data(input_data, password)
    assert isinstance(result, BytesIO)
    assert result.getvalue() != b"test data"  # Ensure data is encrypted


@pytest.mark.unit
def test_encrypt_decrypt_unicode_(password):
    test_string = "\u00a9 test data \u06a2"
    input_data = StringIO(test_string)
    result = encrypt_data(input_data, password, "utf-8")
    assert isinstance(result, BytesIO)
    assert result.getvalue() != test_string
    result = decrypt_data(result, password)
    assert isinstance(result, BytesIO)
    assert result.getvalue().decode("utf-8") == test_string


@pytest.mark.unit
def test_encrypt_data_no_password():
    input_data = BytesIO(b"test data")
    password = ""
    with pytest.raises(EncryptError):
        encrypt_data(input_data, password)


@pytest.mark.unit
def test_encrypt_data_already_encrypted(password):
    input_data = BytesIO(b"Some Test data data")
    input_enc = encrypt_data(input_data, password)
    with pytest.raises(EncryptError):
        encrypt_data(input_enc, password)


@pytest.mark.unit
def test_encrypt_empty_data():
    input_data = BytesIO(b"")
    password = "strongpassword123"
    result = encrypt_data(input_data, password)
    assert isinstance(result, BytesIO)
    assert len(result.getvalue()) > 0  # Ensure outputs exist even for empty input


def test_encrypt_large_data(password):
    input_data = BytesIO(b"a" * 10**6)  # 1MB of data
    result = encrypt_data(input_data, password)
    assert isinstance(result, BytesIO)
    assert result.getvalue() != b"a" * 10**6  # Ensure data is encrypted
    assert input_data.getvalue() == decrypt_data(result, password).getvalue()


@pytest.mark.unit
def test_valid_decryption(password):
    encrypted_stream = encrypt_data(BytesIO(b"VALID_ENCRYPTED_DATA"), password)
    result = decrypt_data(encrypted_stream, password)
    assert isinstance(result, BytesIO)
    assert result.getvalue() == b"VALID_ENCRYPTED_DATA"


@pytest.mark.unit
def test_invalid_magic_bytes(encrypted_stream_with_invalid_magic_bytes, password):
    # Ensure decryption fails on invalid magic bytes
    with pytest.raises(DecryptError) as e:
        decrypt_data(encrypted_stream_with_invalid_magic_bytes, password)
    assert "does not look to be encrypted" in str(e.value)


@pytest.mark.unit
def test_invalid_password(incorrect_password, password):
    data = b"VALID_ENCRYPTED_DATA"
    encrypted_data = encrypt_data(BytesIO(data), password)
    # Ensure decryption fails with an incorrect password
    with pytest.raises(DecryptError) as e:
        decrypt_data(encrypted_data, incorrect_password)
    assert "Incorrect password or invalid data" in str(e.value)


@pytest.mark.unit
def test_empty_stream(password):
    # Test with an empty BytesIO stream
    empty_stream = BytesIO()
    with pytest.raises(DecryptError):
        decrypt_data(empty_stream, password)
