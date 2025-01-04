"""
Block data encryption using
"""

import logging
import secrets
from io import BytesIO, TextIOBase

__all__ = ("encrypt_data", "decrypt_data", "EncryptError", "DecryptError")

from typing import Union

# Magic bytes to identify an encrypted files
MAGIC_BYTES = b"SECF"  # "Secure Encrypted File"
ITERATIONS = 1800000
AES_KEY_LENGTH = 32  # max bytes for AES256

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
        padding_length = data[-1]
        if padding_length < 1 or padding_length > AES.block_size:
            raise ValueError("Invalid padding length")
        if data[-padding_length:] != bytes([padding_length]) * padding_length:
            raise ValueError("Invalid padding bytes")
        return data[:-padding_length]

    def generate_key_from_password(
        password: str, salt: bytes = None
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

    def encrypt_data(
        input_stream: Union[BytesIO, TextIOBase], password: str, encoding: str = "utf-8"
    ) -> BytesIO:
        """
        Encrypt a file using AES-256 in CBC mode with a password-derived key
        """
        if not isinstance(input_stream, BytesIO):
            input_stream.seek(0)
            input_stream = BytesIO(input_stream.read().encode(encoding))
        first_bytes = input_stream.read(len(MAGIC_BYTES))
        if first_bytes == MAGIC_BYTES:
            logger.debug("Attempted to encrypt an already encrypted stream")
            raise EncryptError("This data is already encrypted")
        input_stream.seek(0)

        if not password:
            logger.debug("No or blank password provided")
            raise EncryptError("No or blank password provided")

        key, salt = generate_key_from_password(password)

        # Generate random IV
        iv = secrets.token_bytes(16)

        try:
            # Create cipher
            cipher = AES.new(key, AES.MODE_CBC, iv)

            # Pad and encrypt the data
            encrypted_data = cipher.encrypt(_pad(input_stream.getvalue()))
        except ValueError as exc:
            raise DecryptError(*exc.args) from exc

        logger.debug(f"Encryption successful ({len(encrypted_data)} + 36 bytes)")

        # Write magic bytes, salt, IV, and encrypted data
        return BytesIO(MAGIC_BYTES + salt + iv + encrypted_data)

    def decrypt_data(input_stream: BytesIO, password: str) -> BytesIO:
        """
        Decrypt data that was encrypted using encrypt_data()
        """
        # Read the magic bytes, salt, IV, and encrypted data
        magic = input_stream.read(len(MAGIC_BYTES))
        if magic != MAGIC_BYTES:
            logger.debug("Attempted to decrypt a non-encrypted stream")
            raise DecryptError("This data does not look to be encrypted")
        salt = input_stream.read(16)  # salt
        iv = input_stream.read(16)  # IV
        encrypted_data = input_stream.read()

        # Regenerate the key using the same password and salt
        key, _ = generate_key_from_password(password, salt)

        # Create cipher
        try:
            cipher = AES.new(key, AES.MODE_CBC, iv)
            padded_decrypted_data = cipher.decrypt(encrypted_data)
            # Decrypt and unpad the data
            decrypted_data = _unpad(padded_decrypted_data)
        except ValueError as e:
            raise DecryptError("Incorrect password or invalid data") from e
        logger.debug(f"Decryption successful ({len(decrypted_data)} bytes)")
        return BytesIO(decrypted_data)


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
