"""Exception hierarchy for :mod:`rpgmv_decrypter`."""

from __future__ import annotations

__all__ = [
    "DecrypterError",
    "EmptyFileError",
    "InvalidFakeHeaderError",
    "InvalidKeyError",
    "KeyNotFoundError",
    "UnsupportedFormatError",
]


class DecrypterError(Exception):
    """Base class for every error raised by this package."""


class EmptyFileError(DecrypterError):
    """Raised when a file is empty or could not be read.

    Mirrors the reference implementation's ``exception.emptyFile``.
    """


class InvalidFakeHeaderError(DecrypterError):
    """Raised when an encrypted file does not start with the expected fake header.

    This means the file either is not encrypted at all or the game uses custom
    header values (``SIGNATURE``/``VER``/``REMAIN``/``_headerlength``).  Decrypt
    with ``ignore_fake_header=True`` after making sure the file really is
    encrypted.
    """


class InvalidKeyError(DecrypterError):
    """Raised when an en-/decryption key is missing or is not a hex string."""


class KeyNotFoundError(DecrypterError):
    """Raised when the encryption key could not be detected in the given file."""


class UnsupportedFormatError(DecrypterError):
    """Raised when a file extension cannot be mapped to a plain format."""
