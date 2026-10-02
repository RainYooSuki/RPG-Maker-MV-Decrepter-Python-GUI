"""Encryption key detection.

Port of ``Decrypter.detectEncryptionCode`` / ``Decrypter.searchEncryptionCode``
from the reference implementation.  The following strategies are tried, in the
same order the reference uses:

1. **Encrypted image** (``.rpgmvp`` / ``.png_``) - the key is recovered by
   XOR-ing the second header block with the real PNG header.  This is the most
   reliable source, so it wins whenever the file is an encrypted image.
2. **Plain JSON** - ``System.json`` etc.  store the key in
   ``{"encryptionKey": "..."}``; the file is parsed as a JSON stream of objects.
3. **LZ-String compressed JSON** - obfuscated projects ship ``System.json`` as
   an LZ-String Base64 blob instead of plain JSON.
4. **``rpg_core.js`` scan** - search for ``this._encryptionKey = "..."``.  The
   file is also retried as an LZ-String blob, like the reference does.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import lzstring
from .decrypter import (
    DEFAULT_HEADER_LEN,
    DEFAULT_REMAIN,
    DEFAULT_SIGNATURE,
    DEFAULT_VERSION,
    NORMAL_PNG_HEADER,
    Decrypter,
)
from .exceptions import DecrypterError, EmptyFileError, KeyNotFoundError
from .filetypes import is_encrypted_image

__all__ = [
    "CORE_FILE_CANDIDATES",
    "DETECT_STRATEGIES",
    "SYSTEM_FILE_CANDIDATES",
    "DetectResult",
    "KeyDetector",
    "detect_key",
    "find_data_directory",
    "find_system_file",
    "require_key",
]

#: The default fake header, i.e. the RFC-style magic of an encrypted RPG Maker
#: resource file (``SIGNATURE`` parsed two hex characters at a time).
DEFAULT_FAKE_HEADER: bytes = bytes.fromhex(DEFAULT_SIGNATURE)

#: Where ``System.json`` lives, relative to a game's root (MV then MZ layout).
SYSTEM_FILE_CANDIDATES: tuple[str, ...] = (
    "www/data/System.json",
    "data/System.json",
    "www/data/System.json.txt",
    "System.json",
)

#: Where ``rpg_core.js`` lives, relative to a game's root.
CORE_FILE_CANDIDATES: tuple[str, ...] = (
    "www/js/rpg_core.js",
    "js/rpg_core.js",
)

#: Strategy identifiers, in the order they are attempted.
DETECT_STRATEGIES: tuple[str, ...] = (
    "encrypted-image",
    "json",
    "lzstring",
    "rpg-core",
    "rpg-core-lzstring",
)

_STRATEGY_DESCRIPTIONS = {
    "encrypted-image": "recovered from the encrypted image header",
    "json": "read from the plain JSON file",
    "lzstring": "read from LZ-String compressed JSON",
    "rpg-core": "scanned from rpg_core.js",
    "rpg-core-lzstring": "scanned from LZ-String compressed rpg_core.js",
}

#: ``searchEncryptionCode`` regex for the RPG Maker core script.
#: The reference uses ``/^(.*)this\._encryptionKey ?= ?"(.*)"(.*);(.*)?$/``.
_ENCRYPTION_KEY_LINE = re.compile(r'^(.*)this\._encryptionKey ?= ?"(.*)"(.*);(.*)?$')
_ENCRYPTION_KEY_ANY = re.compile(r'this\._encryptionKey ?= ?"([^"]*)"')
#: Assignment of a non-literal value, e.g. ``this._encryptionKey = someVar;``
_ENCRYPTION_KEY_INDIRECT = re.compile(r"this\._encryptionKey\s*=\s*([^;\"']+)")


@dataclass
class DetectResult:
    """Outcome of a key detection run."""

    key: str | None
    strategy: str | None
    source: Path | None
    tried: list[str] = field(default_factory=list)
    detail: str = ""
    #: ``False`` when the key came from a *guessed* header length (anonymous
    #: bytes, no encrypted-image filename, no standard fake header).  Such a key
    #: cannot be validated - the cipher has no key check - so a UI should show
    #: the candidate and ask the user to confirm rather than trusting it.
    confirmed: bool = True

    @property
    def found(self) -> bool:
        return self.key is not None

    @property
    def description(self) -> str:
        if self.strategy is None:
            return "not found"
        base = _STRATEGY_DESCRIPTIONS.get(self.strategy, self.strategy)
        if self.found and not self.confirmed:
            return f"{base}, but the header values could not be verified - please confirm"
        return base

    def __str__(self) -> str:  # pragma: no cover - convenience
        if self.found:
            return f"{self.key} ({self.description})"
        return "encryption key not found"


class KeyDetector:
    """Detects encryption keys in a single file.

    :param header_len: header length used when recovering a key from an
        encrypted image (default 16)
    """

    def __init__(self, header_len: int = DEFAULT_HEADER_LEN) -> None:
        self.header_len = header_len

    # ------------------------------------------------------------------
    def from_bytes(self, data: bytes | bytearray | None, filename: str = "") -> DetectResult:
        """Run every applicable strategy against ``data``.

        :param filename: used as a hint; an encrypted image extension enables
            the header-recovery strategy.  With no filename the file's own fake
            header decides, so a key recovered from anonymous bytes is only
            reported as ``confirmed=False`` unless that header matched.
        """
        tried: list[str] = []
        if not data:
            return DetectResult(None, None, None, tried, "file is empty")

        # 1) encrypted image -> recover the key from the header block
        named_encrypted_image = is_encrypted_image(Path(filename).suffix)
        guessed = False
        if named_encrypted_image:
            recover = True
        elif not filename:
            recover = self._looks_like_encrypted_image(data)
        else:
            recover = False

        if recover:
            tried.append("encrypted-image")
            key = Decrypter.get_key_from_png(data, self.header_len)
            if key:
                detail = ""
                # `has_standard_fake_header` is length-aware, so a file whose
                # header matches only the stock 16 bytes will NOT be trusted when
                # the caller assumed a different header_len.
                guessed = not self.has_standard_fake_header(data)
                if guessed:
                    detail = (
                        f"this file does not start with the standard "
                        f"header_len={self.header_len} fake header, so those header "
                        "values were assumed; verify the key before using it"
                    )
                return DetectResult(key, "encrypted-image", None, tried, detail, not guessed)

        text = self._decode_text(data)

        # 2) plain JSON
        tried.append("json")
        key = self._key_from_json(text)
        if key:
            return DetectResult(key, "json", None, tried, "")

        # 3) LZ-String compressed JSON
        tried.append("lzstring")
        decompressed = lzstring.decompress_from_base64(text)
        if decompressed:
            key = self._key_from_json(decompressed)
            if key:
                return DetectResult(key, "lzstring", None, tried, "")

        # 4) rpg_core.js scan (and its LZ-String variant)
        tried.append("rpg-core")
        key = self.search_encryption_code(text)
        if key:
            return DetectResult(key, "rpg-core", None, tried, "")

        tried.append("rpg-core-lzstring")
        if decompressed:
            key = self.search_encryption_code(decompressed)
            if key:
                return DetectResult(key, "rpg-core-lzstring", None, tried, "")

        detail = self._not_found_detail(text, decompressed)
        return DetectResult(None, None, None, tried, detail)

    def from_file(self, path: str | os.PathLike[str]) -> DetectResult:
        """Run every applicable strategy against a file on disk.

        :raises EmptyFileError: when the path is not a file or the file is empty
        """
        file_path = Path(path)
        if not file_path.is_file():
            raise EmptyFileError(f"not a file: {file_path}")
        data = file_path.read_bytes()
        if not data:
            raise EmptyFileError(f"file is empty: {file_path}")
        result = self.from_bytes(data, file_path.name)
        if result.source is None:
            result.source = file_path
        return result

    def try_file(self, path: str | os.PathLike[str]) -> DetectResult | None:
        """Like :meth:`from_file` but never raises for an unusable candidate.

        Directory scans use this so that one empty, unreadable or otherwise
        broken file cannot abort the search for a key that another file in the
        same project can still provide.

        :returns: the result, or ``None`` when the file could not be read
        """
        try:
            return self.from_file(path)
        except (DecrypterError, OSError, ValueError):
            return None

    # ------------------------------------------------------------------
    # strategies
    # ------------------------------------------------------------------
    @staticmethod
    def _decode_text(data: bytes | bytearray) -> str:
        """Decode bytes to text the way the browser's TextDecoder does."""
        raw = bytes(data)
        for encoding in ("utf-8-sig", "utf-16"):
            try:
                return raw.decode(encoding)
            except (UnicodeDecodeError, UnicodeError):
                continue
        return raw.decode("utf-8", errors="replace")

    def has_standard_fake_header(self, data: bytes | bytearray) -> bool:
        """True when ``data`` provably starts with the stock fake header.

        "Provable" means ``header_len`` is the stock 16 **and** the first 16
        bytes equal the header built from the default signature/version/remain.
        Both halves matter:

        * Comparing only the 8 byte ``SIGNATURE`` prefix would let a guessed
          header length look standard - a game with a different
          ``_headerlength`` shares that prefix.
        * A shorter assumed ``header_len`` cannot be confirmed either, because
          the remaining bytes would still have to be XOR-ed with the key to
          match; the stock header is exactly 16 bytes, so anything else is an
          assumption and stays "unconfirmed" for the caller to double-check.

        ``header_len`` above 16 is likewise never "standard": the stock structure
        is zero-padded from byte 16 on, so a 16 byte and a 32 byte header match
        the same bytes and the length cannot be pinned down.
        """
        header_len = self.header_len
        if header_len != DEFAULT_HEADER_LEN or len(data) < DEFAULT_HEADER_LEN:
            return False
        expected = Decrypter(
            None,
            header_len=DEFAULT_HEADER_LEN,
            signature=DEFAULT_SIGNATURE,
            version=DEFAULT_VERSION,
            remain=DEFAULT_REMAIN,
        ).fake_header
        return bytes(data[:DEFAULT_HEADER_LEN]) == expected

    @staticmethod
    def _png_chunk_length_ok(field: bytes | bytearray) -> bool:
        """True when ``field`` is a plausible PNG chunk length (4-8 digits)."""
        if len(field) < 4:
            return False
        value = int.from_bytes(bytes(field[:4]), "big")
        return 0 < value <= 0x7FFFFFFF

    def _looks_like_encrypted_image(self, data: bytes | bytearray) -> bool:
        """Heuristic for extension-less input (e.g. drag-and-drop payloads).

        A real PNG begins with its 8 byte signature followed by its ``IHDR``
        chunk descriptor (a 4 byte length plus the ASCII tag ``IHDR``) at
        offset 8.  Encryption XORs only the first ``header_len`` bytes, so:

        * a **plain** PNG still has its descriptor at offset 8 + 4 = 12 and is
          rejected;
        * a **standard** encrypted file starts with the fake header;
        * a **custom-header** encrypted file keeps the descriptor at
          ``12 + header_len`` (the bytes below ``header_len`` are XOR-ed, and for
          any useful key they can no longer read as the fixed signature tail,
          so this cannot be confused with a plain file).

        ``header_len`` is taken from the instance, so the heuristic agrees with
        the block that :meth:`_recover_key_from_image` actually reads.
        """
        header_len = self.header_len
        if len(data) < header_len * 2:
            return False
        if self.has_standard_fake_header(data):
            return True

        offset = 12 + header_len
        if bytes(data[offset : offset + 4]) != b"IHDR":
            return False
        if not self._png_chunk_length_ok(data[offset - 4 : offset]):
            return False
        # Guard the pathological case where the XOR key is zero for the
        # signature tail: then [8:16] still reads as the plain signature.
        return bytes(data[8:16]) != NORMAL_PNG_HEADER[8:16]

    @staticmethod
    def _key_from_json(text: str) -> str | None:
        """``Decrypter.detectEncryptionCode``'s ``JSON.parse('[' + text + ']')``.

        The reference wraps the content in an array because ``System.json`` is a
        single bare object followed by a newline, which is not valid JSON on its
        own in strict parsers.
        """
        if not text or not text.strip():
            return None

        candidates = [text]
        stripped = text.strip()
        if not (stripped.startswith("[") or stripped.startswith("{")):
            # Bare object body, as written by RPG Maker: wrap it like the
            # reference does.  Trailing commas are legal in JS but not in JSON.
            candidates.insert(0, "[" + stripped.rstrip().rstrip(",") + "]")

        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except (json.JSONDecodeError, ValueError):
                continue
            key = KeyDetector._extract_key_from_json(parsed)
            if key:
                return key
        return None

    @staticmethod
    def _extract_key_from_json(value: object) -> str | None:
        """Depth-first search for a non-empty ``encryptionKey`` string."""
        if isinstance(value, dict):
            key = value.get("encryptionKey")
            if isinstance(key, str) and key:
                return key
            for nested in value.values():
                found = KeyDetector._extract_key_from_json(nested)
                if found:
                    return found
        elif isinstance(value, list):
            for nested in value:
                found = KeyDetector._extract_key_from_json(nested)
                if found:
                    return found
        return None

    @staticmethod
    def search_encryption_code(text: str, *, lz_string: bool = False) -> str | None:
        """``Decrypter.searchEncryptionCode`` - scan for ``this._encryptionKey``.

        :param lz_string: decompress ``text`` as LZ-String Base64 first
        """
        if lz_string:
            decompressed = lzstring.decompress_from_base64(text)
            if not decompressed:
                return None
            text = decompressed

        if not text:
            return None

        for line in text.split("\n"):
            cleaned = line.strip().replace("\r", "").replace("\n", "").replace("\t", "")
            match = _ENCRYPTION_KEY_LINE.match(cleaned)
            if match:
                key = match.group(2)
                return key or None

        # Fallback for slightly different formatting (e.g. single quotes or a
        # different assignment target).  The reference gives up here; being a
        # little more forgiving costs nothing and helps real projects.
        match = _ENCRYPTION_KEY_ANY.search(text)
        if match:
            return match.group(1) or None
        return None

    @staticmethod
    def _not_found_detail(text: str, decompressed: str | None) -> str:
        """Explain *why* nothing was found - mirrors the reference's help text."""
        stripped = text.lstrip()
        if not stripped:
            return "the file is empty"

        if _ENCRYPTION_KEY_INDIRECT.search(text) or (
            decompressed and _ENCRYPTION_KEY_INDIRECT.search(decompressed)
        ):
            return (
                "the encryption key in this file is not stored as a plain string "
                "(it is assigned indirectly or obfuscated), so it cannot be read "
                "statically"
            )
        if stripped[0] in "[{":
            return "the file is JSON but contains no 'encryptionKey' entry"
        if decompressed is None:
            return (
                "the file is neither JSON, LZ-String compressed JSON, nor a core "
                "script containing this._encryptionKey"
            )
        return "no encryption key was found in the file or in its LZ-String payload"


# ----------------------------------------------------------------------
# convenience helpers
# ----------------------------------------------------------------------
def find_data_directory(start: str | os.PathLike[str]) -> Path | None:
    """Locate the ``data`` folder of a game from almost any starting point.

    Accepts the game root, its ``www`` folder, its ``data`` folder, a file
    inside any of those, or ``System.json`` itself.
    """
    path = Path(start)
    if path.is_file():
        path = path.parent

    candidates = [
        path,
        path / "www",
        path / "www" / "data",
        path / "data",
        path.parent,
        path.parent / "data",
    ]
    for candidate in candidates:
        if (candidate / "System.json").is_file():
            return candidate
    return None


def find_system_file(start: str | os.PathLike[str]) -> Path | None:
    """Find ``System.json`` for a game root / ``www`` / ``data`` folder."""
    path = Path(start)
    if path.is_file():
        if path.name.lower() == "system.json":
            return path
        path = path.parent

    data_directory = find_data_directory(path)
    if data_directory is not None:
        system_file = data_directory / "System.json"
        if system_file.is_file():
            return system_file

    for relative in SYSTEM_FILE_CANDIDATES:
        candidate = path / relative
        if candidate.is_file():
            return candidate
    return None


def detect_key(source: str | os.PathLike[str] | bytes | bytearray,
               *,
               header_len: int = DEFAULT_HEADER_LEN) -> DetectResult:
    """Detect the encryption key of a game, file or byte blob.

    :param source: a path to ``System.json``, any file inside a game, a game
        directory, an encrypted image - or raw bytes
    :returns: a :class:`DetectResult`; check :attr:`DetectResult.found`
    :raises EmptyFileError: when ``source`` is a path that does not exist or is
        empty
    """
    detector = KeyDetector(header_len)

    if isinstance(source, (bytes, bytearray)):
        return detector.from_bytes(source)

    path = Path(source)
    if not path.exists():
        raise EmptyFileError(f"path does not exist: {path}")

    if path.is_dir():
        return _detect_in_directory(detector, path)
    return detector.from_file(path)


def _detect_in_directory(detector: KeyDetector, directory: Path) -> DetectResult:
    """Detect a key using the conventional files of an extracted game.

    Candidates that cannot be read (empty, locked, binary junk) are skipped so
    that one broken file never hides a key another file can provide.
    """
    tried: list[str] = []

    system_file = find_system_file(directory)
    if system_file is not None:
        tried.append(str(system_file))
        result = detector.try_file(system_file)
        if result is not None and result.found:
            return result

    for relative in CORE_FILE_CANDIDATES:
        core_file = directory / relative
        if not core_file.is_file() and (directory / "www").is_dir():
            core_file = directory / "www" / relative
        if core_file.is_file():
            tried.append(str(core_file))
            result = detector.try_file(core_file)
            if result is not None and result.found:
                return result

    # Last resort: any encrypted image in the project carries the key.
    for pattern in ("**/*.rpgmvp", "**/*.png_"):
        for image in sorted(directory.glob(pattern)):
            tried.append(str(image))
            result = detector.try_file(image)
            if result is not None and result.found:
                return result

    return DetectResult(
        None,
        None,
        None,
        tried,
        "no System.json, rpg_core.js or encrypted image containing a key was "
        f"found under {directory}",
    )


def require_key(source: str | os.PathLike[str] | bytes | bytearray) -> str:
    """Like :func:`detect_key` but raises instead of returning "not found"."""
    result = detect_key(source)
    if not result.found:
        raise KeyNotFoundError(
            f"could not detect an encryption key ({result.detail}); "
            "pass the key manually"
        )
    assert result.key is not None
    return result.key
