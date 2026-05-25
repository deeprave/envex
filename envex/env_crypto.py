"""
Block data encryption using authenticated AES-256-GCM.
"""

import logging
import secrets
from io import BytesIO, TextIOBase

__all__ = ("encrypt_data", "decrypt_data", "EncryptError", "DecryptError")

from typing import Union

# Magic bytes to identify encrypted files. The legacy prefix is retained so
# existing AES-CBC files can still be detected and decrypted.
MAGIC_BYTES = b"SECF"  # "Secure Encrypted File"
AUTH_MAGIC_BYTES = b"SECG"
ITERATIONS = 1800000
AES_KEY_LENGTH = 32  # max bytes for AES256
SALT_LENGTH = 16
LEGACY_IV_LENGTH = 16
GCM_NONCE_LENGTH = 12
GCM_TAG_LENGTH = 16
DECRYPT_ERROR_MESSAGE = "Incorrect password or invalid data"

logger = logging.getLogger(__file__)


class DecryptError(ValueError):
    pass


class EncryptError(ValueError):
    pass


try:
    from Crypto.Cipher import AES
    from Crypto.Hash import SHA256
    from Crypto.Protocol.KDF import PBKDF2

    def _pad(data: bytes) -> bytes:
        """
        Pad data to be a multiple of 16 bytes (AES block size)
        """
        padding_length = 16 - (len(data) % 16)
        padding = bytes([padding_length] * padding_length)
        return data + padding

    def _unpad(data: bytes) -> bytes:
        """
        Check and remove PKCS7 padding
        """
        padding_length = data[-1] if data else 0
        if padding_length < 1 or padding_length > AES.block_size:
            raise ValueError("Invalid padding")
        if data[-padding_length:] != bytes([padding_length]) * padding_length:
            raise ValueError("Invalid padding")
        return data[:-padding_length]

    def generate_key_from_password(
        password: str, salt: bytes | None = None
    ) -> tuple[bytes, bytes]:
        """
        Generate an AES key from a password using PBKDF2
        Returns the key and salt used
        """
        if salt is None:
            salt = secrets.token_bytes(16)

        key = PBKDF2(
            password,
            salt,
            dkLen=AES_KEY_LENGTH,  # AES-256 key size
            count=ITERATIONS,  # High iteration count for security
            hmac_hash_module=SHA256,
        )
        return key, salt

    def _read_stream(input_stream: Union[BytesIO, TextIOBase], encoding: str) -> BytesIO:
        if not isinstance(input_stream, BytesIO):
            input_stream.seek(0)
            data = input_stream.read()
            data = data.encode(encoding) if isinstance(data, str) else data
            input_stream = BytesIO(data)
        return input_stream

    def _read_exact(input_stream: BytesIO, size: int) -> bytes:
        data = input_stream.read(size)
        if len(data) != size:
            raise DecryptError(DECRYPT_ERROR_MESSAGE)
        return data

    def encrypt_data(
        input_stream: Union[BytesIO, TextIOBase], password: str, encoding: str = "utf-8"
    ) -> BytesIO:
        """
        Encrypt a file using AES-256-GCM with a password-derived key.
        """
        input_stream = _read_stream(input_stream, encoding)
        first_bytes = input_stream.read(max(len(MAGIC_BYTES), len(AUTH_MAGIC_BYTES)))
        if first_bytes in (MAGIC_BYTES, AUTH_MAGIC_BYTES):
            logger.debug("Attempted to encrypt an already encrypted stream")
            raise EncryptError("This data is already encrypted")
        input_stream.seek(0)

        if not password:
            logger.debug("No or blank password provided")
            raise EncryptError("No or blank password provided")

        key, salt = generate_key_from_password(password)

        nonce = secrets.token_bytes(GCM_NONCE_LENGTH)

        try:
            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
            encrypted_data, tag = cipher.encrypt_and_digest(input_stream.getvalue())
        except ValueError as exc:
            raise DecryptError(*exc.args) from exc

        logger.debug(
            f"Encryption successful ({len(encrypted_data)} + "
            f"{len(AUTH_MAGIC_BYTES) + SALT_LENGTH + GCM_NONCE_LENGTH + GCM_TAG_LENGTH} bytes)"
        )

        return BytesIO(AUTH_MAGIC_BYTES + salt + nonce + tag + encrypted_data)

    def _decrypt_gcm(input_stream: BytesIO, password: str) -> BytesIO:
        salt = _read_exact(input_stream, SALT_LENGTH)
        nonce = _read_exact(input_stream, GCM_NONCE_LENGTH)
        tag = _read_exact(input_stream, GCM_TAG_LENGTH)
        encrypted_data = input_stream.read()
        key, _ = generate_key_from_password(password, salt)
        try:
            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
            decrypted_data = cipher.decrypt_and_verify(encrypted_data, tag)
        except ValueError as exc:
            raise DecryptError(DECRYPT_ERROR_MESSAGE) from exc
        logger.debug(f"Decryption successful ({len(decrypted_data)} bytes)")
        return BytesIO(decrypted_data)

    def _decrypt_legacy_cbc(
        input_stream: BytesIO, password: str, salt_prefix: bytes
    ) -> BytesIO:
        salt = salt_prefix + _read_exact(input_stream, SALT_LENGTH - len(salt_prefix))
        iv = _read_exact(input_stream, LEGACY_IV_LENGTH)
        encrypted_data = input_stream.read()
        key, _ = generate_key_from_password(password, salt)
        try:
            cipher = AES.new(key, AES.MODE_CBC, iv)
            decrypted_data = _unpad(cipher.decrypt(encrypted_data))
        except ValueError as exc:
            raise DecryptError(DECRYPT_ERROR_MESSAGE) from exc
        logger.debug(f"Legacy decryption successful ({len(decrypted_data)} bytes)")
        return BytesIO(decrypted_data)

    def decrypt_data(input_stream: BytesIO, password: str) -> BytesIO:
        """
        Decrypt data that was encrypted using encrypt_data()
        """
        header = input_stream.read(len(AUTH_MAGIC_BYTES))
        if header == AUTH_MAGIC_BYTES:
            return _decrypt_gcm(input_stream, password)
        if not header.startswith(MAGIC_BYTES):
            logger.debug("Attempted to decrypt a non-encrypted stream")
            raise DecryptError("This data does not look to be encrypted")
        return _decrypt_legacy_cbc(input_stream, password, header[len(MAGIC_BYTES) :])


except ImportError as e:
    once = False
    if not once:
        once = True
        logger.warning("Crypto module not found, encryption not available")
        logger.exception(e)

    def encrypt_data(_input_stream: BytesIO, _password: str) -> BytesIO:
        raise EncryptError("Encryption not supported")

    def decrypt_data(_input_stream: BytesIO, _password: str) -> BytesIO:
        raise DecryptError("Decryption not supported")
