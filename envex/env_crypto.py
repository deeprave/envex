"""
Block data encryption using authenticated AES-256-GCM.
"""

import io
import logging
import re
import secrets
from io import BytesIO, TextIOBase

# Magic bytes to identify encrypted files. The legacy prefix is retained so
# existing AES-CBC files can still be detected and decrypted.
MAGIC_BYTES = b"SECF"  # "Secure Encrypted File"
AUTH_MAGIC_BYTES = b"SECG"
if len(MAGIC_BYTES) != len(AUTH_MAGIC_BYTES):
    raise RuntimeError("Encrypted file magic headers must have equal lengths")
ITERATIONS = 1800000
AES_KEY_LENGTH = 32  # max bytes for AES256
SALT_LENGTH = 16
LEGACY_IV_LENGTH = 16
GCM_NONCE_LENGTH = 12
GCM_TAG_LENGTH = 16
AUTH_CONTAINER_MIN_REMAINDER_LENGTH = SALT_LENGTH + GCM_NONCE_LENGTH + GCM_TAG_LENGTH
LEGACY_CONTAINER_REMAINDER_HEADER_LENGTH = SALT_LENGTH + LEGACY_IV_LENGTH
DECRYPT_ERROR_MESSAGE = "Incorrect password or invalid data"
AUTH_MAGIC_PREFIX = AUTH_MAGIC_BYTES.decode("ascii")
MAGIC_PREFIX = MAGIC_BYTES.decode("ascii")
TEXT_PROBE_BYTES = 1024
# Only direct KEY= lines can collide with the magic bytes at offset 0. Dotenv
# forms such as "export KEY=..." do not need special handling here.
_DOTENV_ASSIGNMENT_PREFIX_PATTERN = re.compile(r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=")

logger = logging.getLogger(__file__)

__all__ = ("encrypt_data", "decrypt_data", "EncryptError", "DecryptError")


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

    def _read_stream(input_stream: BytesIO | TextIOBase, encoding: str) -> BytesIO:
        if not isinstance(input_stream, BytesIO):
            try:
                input_stream.seek(0)
            except io.UnsupportedOperation:
                logger.warning(
                    "Input stream does not support seek(0); only bytes from the "
                    "current position will be processed"
                )
            data = input_stream.read()
            data = data.encode(encoding) if isinstance(data, str) else data
            input_stream = BytesIO(data)
        return input_stream

    def _read_exact(input_stream: BytesIO, size: int) -> bytes:
        data = input_stream.read(size)
        if len(data) != size:
            raise DecryptError(DECRYPT_ERROR_MESSAGE)
        return data

    def _read_magic(input_stream: BytesIO) -> bytes:
        return input_stream.read(len(MAGIC_BYTES))

    def _remaining_length(input_stream: BytesIO) -> int:
        """Return remaining bytes for streams normalized to seekable BytesIO."""
        assert isinstance(input_stream, BytesIO)
        start_pos = input_stream.tell()
        return len(input_stream.getbuffer()) - start_pos

    def _has_envex_container_structure(input_stream: BytesIO) -> bool:
        stream_pos = input_stream.tell()
        try:
            input_stream.seek(0)
            header = _read_magic(input_stream)
            remaining_length = _remaining_length(input_stream)
        finally:
            input_stream.seek(stream_pos)

        if header == AUTH_MAGIC_BYTES:
            return remaining_length >= AUTH_CONTAINER_MIN_REMAINDER_LENGTH
        if header == MAGIC_BYTES:
            if remaining_length < LEGACY_CONTAINER_REMAINDER_HEADER_LENGTH:
                return False
            encrypted_length = remaining_length - LEGACY_CONTAINER_REMAINDER_HEADER_LENGTH
            return encrypted_length > 0 and encrypted_length % AES.block_size == 0
        return False

    def _looks_like_magic_prefix_dotenv_assignment(
        input_stream: BytesIO, encoding: str
    ) -> bool:
        stream_pos = input_stream.tell()
        try:
            input_stream.seek(0)
            text = input_stream.read(TEXT_PROBE_BYTES).decode(encoding)
        except UnicodeDecodeError:
            return False
        finally:
            input_stream.seek(stream_pos)
        newline_index = text.find("\n")
        line = text if newline_index == -1 else text[:newline_index]
        match = _DOTENV_ASSIGNMENT_PREFIX_PATTERN.match(line)
        if match is None:
            return False
        key = match.group(1)
        return key.startswith(f"{AUTH_MAGIC_PREFIX}_") or key.startswith(
            f"{MAGIC_PREFIX}_"
        )

    def _is_already_encrypted(input_stream: BytesIO, encoding: str) -> bool:
        # The stream has already been normalized by _read_stream(), so the
        # helper checks below can safely probe from offset 0 and restore position.
        # Plaintext dotenv keys such as SECG_KEY can look like a container
        # header. Treat them as plaintext only after a bounded prefix decodes
        # as text; real containers normally contain binary salt/nonce/tag data.
        if _looks_like_magic_prefix_dotenv_assignment(input_stream, encoding):
            return False
        # For all other cases, rely on envex container structure.
        return _has_envex_container_structure(input_stream)

    def encrypt_data(
        input_stream: BytesIO | TextIOBase, password: str, encoding: str = "utf-8"
    ) -> BytesIO:
        """
        Encrypt a file using AES-256-GCM with a password-derived key.
        """
        input_stream = _read_stream(input_stream, encoding)
        if not password:
            logger.debug("No or blank password provided")
            raise EncryptError("No or blank password provided")
        if _is_already_encrypted(input_stream, encoding):
            logger.debug("Attempted to encrypt an already encrypted stream")
            raise EncryptError("This data is already encrypted")
        input_stream.seek(0)

        key, salt = generate_key_from_password(password)

        nonce = secrets.token_bytes(GCM_NONCE_LENGTH)

        try:
            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
            encrypted_data, tag = cipher.encrypt_and_digest(input_stream.getvalue())
        except ValueError as exc:
            raise EncryptError("Encryption failed") from exc

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

    def _decrypt_legacy_cbc(input_stream: BytesIO, password: str) -> BytesIO:
        salt = _read_exact(input_stream, SALT_LENGTH)
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

    def decrypt_data(
        input_stream: BytesIO, password: str, *, allow_legacy: bool = False
    ) -> BytesIO:
        """
        Decrypt data that was encrypted using encrypt_data()
        """
        header = _read_magic(input_stream)
        if header == AUTH_MAGIC_BYTES:
            return _decrypt_gcm(input_stream, password)
        if header != MAGIC_BYTES:
            logger.debug("Attempted to decrypt a non-encrypted stream")
            raise DecryptError("This data does not look to be encrypted")
        if not allow_legacy:
            raise DecryptError("Legacy AES-CBC data requires explicit legacy decryption")
        return _decrypt_legacy_cbc(input_stream, password)


except ImportError:
    logger.warning("Crypto module not found, encryption and decryption are not available")
    logger.debug("Crypto import failure", exc_info=True)

    def encrypt_data(
        _input_stream: BytesIO | TextIOBase,
        _password: str,
        encoding: str = "utf-8",
    ) -> BytesIO:
        raise EncryptError("Encryption not supported")

    def decrypt_data(
        _input_stream: BytesIO, _password: str, *, allow_legacy: bool = False
    ) -> BytesIO:
        raise DecryptError("Decryption not supported")
