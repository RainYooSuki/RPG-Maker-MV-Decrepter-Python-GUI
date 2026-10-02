"""The XOR cipher used by RPG Maker MV/MZ resource encryption.

The reference implementation is ``scripts/Decrypter.js``.  The algorithm is
simple and worth stating explicitly:

* The first ``header_len`` (16) bytes of the plain file are XOR-ed with the
  encryption key.
* A 16 byte "fake header" is prepended.  It is built by parsing the hex strings
  ``SIGNATURE`` + ``VER`` + ``REMAIN`` two characters at a time.
* Everything after byte ``header_len`` is stored untouched.

Both formats use the same 16 byte header, which is why only the key's first 16
bytes ever matter.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import BinaryIO, Final

from .exceptions import (
    EmptyFileError,
    InvalidFakeHeaderError,
    InvalidKeyError,
)
from .filetypes import RpgMakerVersion

__all__ = [
    "DEFAULT_HEADER_LEN",
    "DEFAULT_REMAIN",
    "DEFAULT_SIGNATURE",
    "DEFAULT_VERSION",
    "NORMAL_PNG_HEADER",
    "Decrypter",
]

#: ``Decrypter._headerlength`` in the reference implementation.
DEFAULT_HEADER_LEN: Final[int] = 16
#: ``Decrypter.SIGNATURE``.
DEFAULT_SIGNATURE: Final[str] = "5250474d56000000"
#: ``Decrypter.VER``.
DEFAULT_VERSION: Final[str] = "000301"
#: ``Decrypter.REMAIN``.
DEFAULT_REMAIN: Final[str] = "0000000000"

#: ``Decrypter.pngHeaderBytes`` - start of every valid PNG file.
NORMAL_PNG_HEADER: Final[bytes] = bytes(
    [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52]
)

_HEX_DIGITS: Final[frozenset[str]] = frozenset("0123456789abcdefABCDEF")


def _is_hex(value: str) -> bool:
    """``Decrypter.checkHexChars`` - non-empty and only hex digits."""
    return bool(value) and all(character in _HEX_DIGITS for character in value)


def _byte_to_hex(value: int) -> str:
    """``Decrypter.byteToHex``."""
    return f"{value & 0xFF:02x}"


class Decrypter:
    """Encrypts/decrypts RPG Maker MV and MZ resource files.

    :param encryption_key: hex string; only the first ``header_len * 2``
        characters are used.  ``None`` is allowed for
        :meth:`restore_png_header`, which does not need a key.
    :param header_len: header length in bytes (default 16)
    :param signature: fake header signature (default ``5250474d56000000``)
    :param version: fake header version (default ``000301``)
    :param remain: fake header remainder (default ``0000000000``)
    :param ignore_fake_header: skip header verification while decrypting
    :raises InvalidKeyError: if ``encryption_key`` is not a usable hex string
    """

    def __init__(
        self,
        encryption_key: str | None,
        *,
        header_len: int = DEFAULT_HEADER_LEN,
        signature: str = DEFAULT_SIGNATURE,
        version: str = DEFAULT_VERSION,
        remain: str = DEFAULT_REMAIN,
        ignore_fake_header: bool = False,
        rpgmaker_version: RpgMakerVersion = RpgMakerVersion.MV,
    ) -> None:
        self.header_len = self._validate_header_len(header_len)
        self.signature = self._validate_hex_fragment(signature, "signature")
        self.version = self._validate_hex_fragment(version, "version")
        self.remain = self._validate_hex_fragment(remain, "remain")
        self.ignore_fake_header = ignore_fake_header
        self.rpgmaker_version = rpgmaker_version

        if encryption_key is None or encryption_key == "":
            self.encryption_key: str | None = None
            self._key_bytes: bytes = b""
        else:
            if not _is_hex(encryption_key):
                raise InvalidKeyError(
                    "the encryption key may only contain hex characters (0-9, a-f, A-F)"
                )
            if len(encryption_key) % 2 != 0:
                raise InvalidKeyError(
                    "the encryption key must have an even number of hex characters "
                    f"(got {len(encryption_key)}); each byte needs two characters"
                )
            self.encryption_key = encryption_key
            try:
                self._key_bytes = bytes.fromhex(encryption_key)
            except ValueError as exc:  # pragma: no cover - guarded by the checks above
                raise InvalidKeyError(f"the encryption key is not valid hex: {exc}") from exc

    # ------------------------------------------------------------------
    # construction helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_header_len(header_len: int) -> int:
        try:
            value = int(header_len)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"header_len must be an integer, got {header_len!r}") from exc
        if value <= 0:
            raise ValueError("header_len must be a positive number")
        return value

    @staticmethod
    def _validate_hex_fragment(value: str, label: str) -> str:
        if not _is_hex(value):
            raise ValueError(f"{label} may only contain hex characters, got {value!r}")
        return value

    @classmethod
    def from_game_directory(
        cls, game_directory: str | os.PathLike[str], **kwargs
    ) -> "Decrypter":
        """Detect the key of an extracted game and return a ready decrypter.

        :param game_directory: project root, its ``www`` folder or its ``data``
            folder (MV: ``<game>/www/data/System.json``,
            MZ: ``<game>/data/System.json``)
        :raises KeyNotFoundError: when no key could be detected (the returned
            decrypter is always usable, so it never silently has no key)
        """
        from .exceptions import KeyNotFoundError  # local import to avoid a cycle
        from .key_detect import detect_key  # local import to avoid a cycle

        result = detect_key(game_directory)
        if not result.found:
            raise KeyNotFoundError(
                f"could not detect an encryption key in {game_directory} "
                f"({result.detail}); pass the key with Decrypter(key) instead"
            )
        return cls(result.key, **kwargs)

    @classmethod
    def for_version(
        cls, encryption_key: str, version: RpgMakerVersion = RpgMakerVersion.MV, **kwargs
    ) -> "Decrypter":
        """Build a decrypter bound to an engine version.

        The version does not change the cipher (MV and MZ use the same one); it
        only selects the extension naming used for default output paths.
        """
        instance = cls(encryption_key, rpgmaker_version=version, **kwargs)
        return instance

    # ------------------------------------------------------------------
    # header handling
    # ------------------------------------------------------------------
    @property
    def fake_header(self) -> bytes:
        """The fake header (``Decrypter.buildFakeHeader``).

        The reference parses ``SIGNATURE + VER + REMAIN`` two characters at a
        time and calls ``parseInt('0x' + chunk, 16)`` for ``header_len`` bytes.
        Once past the end of the 16 byte structure the chunk is empty, which JS
        turns into ``NaN`` -> the byte becomes 0, so a longer header is the
        16 byte structure followed by zero bytes.
        """
        structure = self.signature + self.version + self.remain
        header = bytearray(self.header_len)
        for index in range(self.header_len):
            chunk = structure[index * 2 : index * 2 + 2]
            if not chunk:
                break  # remaining bytes stay 0, matching parseInt("0x") -> NaN
            header[index] = int(chunk, 16) & 0xFF
        return bytes(header)

    @property
    def normal_png_header(self) -> bytes:
        """Start of a valid PNG file, capped at ``header_len`` bytes."""
        return NORMAL_PNG_HEADER[: self.header_len]

    @property
    def encryption_code_array(self) -> list[str]:
        """``Decrypter.splitEncryptionCode`` - the key in 2-char chunks."""
        if not self.encryption_key:
            return []
        return [self.encryption_key[i : i + 2] for i in range(0, len(self.encryption_key), 2)]

    def verify_fake_header(self, data: bytes | bytearray) -> bool:
        """``Decrypter.verifyFakeHeader`` - does ``data`` start with the header?"""
        header = self.fake_header
        if len(data) < self.header_len:
            return False
        return bytes(data[: self.header_len]) == header

    def _xor_prefix(self, buffer: bytearray) -> None:
        """XOR the first ``header_len`` bytes of ``buffer`` in place."""
        key = self._key_bytes
        limit = min(self.header_len, len(buffer), len(key))
        if limit == 0:
            return
        for index in range(limit):
            buffer[index] ^= key[index]

    def _require_key(self) -> bytes:
        if not self._key_bytes:
            raise InvalidKeyError(
                "no encryption key set; pass the key to Decrypter() or use "
                "Decrypter.from_game_directory()"
            )
        if len(self._key_bytes) < self.header_len:
            raise InvalidKeyError(
                f"the encryption key is too short: {len(self._key_bytes)} bytes "
                f"available but the header needs {self.header_len}"
            )
        return self._key_bytes

    # ------------------------------------------------------------------
    # byte level operations
    # ------------------------------------------------------------------
    def decrypt_bytes(self, data: bytes | bytearray | None) -> bytes:
        """Decrypt an encrypted file's bytes (fake header removed).

        :raises EmptyFileError: when ``data`` is ``None`` or empty
        :raises InvalidFakeHeaderError: when verification is on and fails
        :raises InvalidKeyError: when no usable key is set
        """
        if not data:
            raise EmptyFileError("file is empty, or can't be read")
        self._require_key()

        buffer = bytearray(data)
        if not self.ignore_fake_header and not self.verify_fake_header(buffer):
            raise InvalidFakeHeaderError(
                "the fake header doesn't match the expected header; make sure the "
                "file is encrypted, or decrypt with ignore_fake_header=True"
            )

        payload = bytearray(buffer[self.header_len :])
        self._xor_prefix(payload)
        return bytes(payload)

    def encrypt_bytes(self, data: bytes | bytearray | None) -> bytes:
        """Encrypt plain bytes, prepending the fake header.

        :raises EmptyFileError: when ``data`` is ``None`` or empty
        :raises InvalidKeyError: when no usable key is set
        """
        if not data:
            raise EmptyFileError("file is empty, or can't be read")
        self._require_key()

        payload = bytearray(data)
        self._xor_prefix(payload)
        result = self.fake_header + bytes(payload)

        # The reference implementation re-verifies the header it just built.
        if not self.verify_fake_header(result):  # pragma: no cover - defensive
            raise InvalidFakeHeaderError(
                "the generated fake header does not match; please report this bug"
            )
        return result

    def restore_png_header_bytes(self, data: bytes | bytearray | None) -> bytes:
        """Restore a PNG's real header without knowing the key.

        Drops the fake header *and* the XOR-ed first block, then prepends the
        standard PNG header.  Only bytes from ``2 * len(normal_png_header)``
        survive; the information in the XOR-ed block is unrecoverable without
        the key.

        ``normal_png_header`` is capped at 16 bytes, so for a non-standard
        ``header_len`` the reference caches that capped value and slices with
        it.  That behaviour is reproduced deliberately: RPG Maker only ever uses
        ``header_len`` 16, and no real game has a longer key-bearing PNG header
        to recover.

        :raises EmptyFileError: when ``data`` is ``None`` or empty
        """
        if not data:
            raise EmptyFileError("file is empty, or can't be read")

        header = self.normal_png_header
        header_len = len(header)  # may be shorter than self.header_len
        payload = bytes(data)[header_len * 2 :]
        return header + payload

    # ------------------------------------------------------------------
    # file level operations
    # ------------------------------------------------------------------
    def decrypt_file(
        self, source: str | os.PathLike[str], destination: str | os.PathLike[str] | None = None
    ) -> Path:
        """Decrypt ``source`` and write the plain file.

        :param destination: target path; when ``None`` the source's extension is
            converted (``hero.rpgmvp`` -> ``hero.png``) next to the source
        :returns: the written path
        """
        source_path = Path(source)
        target = Path(destination) if destination is not None else default_output_path(source_path, decrypt=True)

        data = _read_file(source_path)
        plain = self.decrypt_bytes(data)
        _write_file(target, plain)
        return target

    def encrypt_file(
        self,
        source: str | os.PathLike[str],
        destination: str | os.PathLike[str] | None = None,
        *,
        version: RpgMakerVersion | None = None,
    ) -> Path:
        """Encrypt ``source`` and write the encrypted file.

        :param version: engine whose extension naming should be used; defaults
            to :attr:`rpgmaker_version`
        :returns: the written path
        """
        source_path = Path(source)
        chosen_version = version if version is not None else self.rpgmaker_version
        target = (
            Path(destination)
            if destination is not None
            else default_output_path(source_path, decrypt=False, version=chosen_version)
        )

        data = _read_file(source_path)
        encrypted = self.encrypt_bytes(data)
        _write_file(target, encrypted)
        return target

    def restore_png_file(
        self, source: str | os.PathLike[str], destination: str | os.PathLike[str] | None = None
    ) -> Path:
        """Restore an encrypted image without a key (see :meth:`restore_png_header_bytes`)."""
        source_path = Path(source)
        target = Path(destination) if destination is not None else default_output_path(source_path, decrypt=True)

        data = _read_file(source_path)
        restored = self.restore_png_header_bytes(data)
        _write_file(target, restored)
        return target

    # ------------------------------------------------------------------
    # streaming variants (avoid holding whole audio files in memory)
    # ------------------------------------------------------------------
    def decrypt_stream(self, source: BinaryIO, destination: BinaryIO) -> None:
        """Streaming :meth:`decrypt_bytes`."""
        self._require_key()
        header = source.read(self.header_len)
        if not header:
            raise EmptyFileError("file is empty, or can't be read")
        if not self.ignore_fake_header and not self.verify_fake_header(header):
            raise InvalidFakeHeaderError(
                "the fake header doesn't match the expected header; make sure the "
                "file is encrypted, or decrypt with ignore_fake_header=True"
            )

        block = bytearray(source.read(self.header_len))
        self._xor_prefix(block)
        destination.write(block)
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            destination.write(chunk)

    def encrypt_stream(self, source: BinaryIO, destination: BinaryIO) -> None:
        """Streaming :meth:`encrypt_bytes`.

        :raises EmptyFileError: when ``source`` yields no bytes, matching
            :meth:`encrypt_bytes` (a bare fake header is not a valid file)
        :raises InvalidKeyError: when no usable key is set
        """
        self._require_key()
        block = bytearray(source.read(self.header_len))
        if not block:
            raise EmptyFileError("file is empty, or can't be read")
        self._xor_prefix(block)
        destination.write(self.fake_header)
        destination.write(block)
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            destination.write(chunk)

    # ------------------------------------------------------------------
    # static helpers (mirrors of the reference's static methods)
    # ------------------------------------------------------------------
    @staticmethod
    def get_normal_png_header(header_len: int = DEFAULT_HEADER_LEN) -> bytes:
        """``Decrypter.getNormalPNGHeader`` - capped at 16 bytes."""
        return NORMAL_PNG_HEADER[:header_len]

    @staticmethod
    def get_key_from_png(data: bytes | bytearray | None, header_len: int = DEFAULT_HEADER_LEN) -> str | None:
        """``Decrypter.getKeyFromPNG`` - recover the key from an encrypted PNG.

        An encrypted PNG stores ``normal_header XOR key`` right after the fake
        header, so XOR-ing those bytes with the real PNG header reveals the key.

        The real PNG header has only 16 bytes, so the recovered key is capped at
        ``min(header_len, 16)`` bytes - ``getNormalPNGHeader`` caps the reference
        string in exactly the same way.  The reference would produce ``NaN`` for
        the extra bytes; returning the recoverable prefix is the useful
        behaviour, and a key shorter than ``header_len`` cannot be used for
        en/decryption anyway.

        :returns: the key as a hex string, or ``None`` when the file is too short
        """
        if not data:
            return None
        if header_len <= 0 or len(data) < header_len * 2:
            return None

        recovered = min(header_len, len(NORMAL_PNG_HEADER))
        return "".join(
            _byte_to_hex(NORMAL_PNG_HEADER[index] ^ data[header_len + index])
            for index in range(recovered)
        )

    @staticmethod
    def check_hex_chars(value: str) -> bool:
        """``Decrypter.checkHexChars``."""
        return _is_hex(value)

    @staticmethod
    def helper_show_bits(value: int) -> str:
        """``Decrypter.helperShowBits`` - 8 character binary representation."""
        if value is None:
            value = 0
        if not 0 <= value <= 255:
            raise ValueError(f"invalid byte value ({value})")
        return f"{value:08b}"


def _read_file(path: Path) -> bytes:
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        raise
    if not data:
        raise EmptyFileError(f"file is empty: {path}")
    return data


def _write_file(path: Path, data: bytes) -> None:
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def default_output_path(
    source: Path,
    *,
    decrypt: bool,
    version: RpgMakerVersion = RpgMakerVersion.MV,
) -> Path:
    """Derive the output path next to ``source`` by converting its extension.

    Unknown extensions are kept as-is; callers that need collision protection
    should pass an explicit destination.
    """
    from .filetypes import decrypt_extension, encrypt_extension, split_name

    stem, extension = split_name(source)
    if decrypt:
        new_extension = decrypt_extension(extension)
    else:
        new_extension = encrypt_extension(extension, version)

    if new_extension is None:
        return source
    return source.with_name(f"{stem}.{new_extension}")
