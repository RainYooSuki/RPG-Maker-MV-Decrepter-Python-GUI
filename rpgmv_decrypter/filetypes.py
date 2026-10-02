"""File extension / media type handling for RPG Maker MV and MZ.

Ported from the reference implementation's ``RPGFile`` class.  RPG Maker MV and
MZ use different encrypted extensions for the same plain formats, so every
mapping needs to know which engine a file belongs to.
"""

from __future__ import annotations

import enum
from pathlib import Path

__all__ = [
    "DECRYPT_EXTENSIONS",
    "ENCRYPTED_EXTENSIONS",
    "ENCRYPT_EXTENSIONS",
    "LZ_EXTENSIONS",
    "RpgMakerVersion",
    "decrypt_extension",
    "encrypt_extension",
    "guess_version_for_extension",
    "is_encrypted_extension",
    "is_encrypted_image",
    "media_type_for",
    "plain_extension_for",
    "split_name",
]

PNG_EXTENSIONS = frozenset({"png", "rpgmvp", "png_"})
OGG_EXTENSIONS = frozenset({"ogg", "rpgmvo", "ogg_"})
M4A_EXTENSIONS = frozenset({"m4a", "rpgmvm", "m4a_"})

#: Extensions of encrypted resources (reference: ``RPGFile.isEncryptedExt``).
ENCRYPTED_EXTENSIONS = frozenset({"rpgmvp", "rpgmvm", "rpgmvo", "png_", "ogg_", "m4a_"})

#: Extensions this tool can decrypt.
DECRYPT_EXTENSIONS = ENCRYPTED_EXTENSIONS

#: Extensions this tool can encrypt.
ENCRYPT_EXTENSIONS = frozenset({"png", "ogg", "m4a"})

#: Extensions whose content may be LZ-String compressed.
LZ_EXTENSIONS = frozenset({"json", "txt", "js"})

#: Plain extension -> (MV encrypted, MZ encrypted).
_ENCRYPT_MAP: dict[str, tuple[str, str]] = {
    "png": ("rpgmvp", "png_"),
    "ogg": ("rpgmvo", "ogg_"),
    "m4a": ("rpgmvm", "m4a_"),
}

#: Encrypted extension -> plain extension.
_DECRYPT_MAP: dict[str, str] = {
    "rpgmvp": "png",
    "png_": "png",
    "rpgmvo": "ogg",
    "ogg_": "ogg",
    "rpgmvm": "m4a",
    "m4a_": "m4a",
}


class RpgMakerVersion(enum.Enum):
    """Which RPG Maker generation produced (or should consume) a file."""

    MV = "MV"
    MZ = "MZ"

    @property
    def label(self) -> str:
        return f"RPG Maker {self.value}"


def split_name(full_name: str | Path) -> tuple[str, str]:
    """Split ``full_name`` into ``(stem, extension)``.

    Mimics ``RPGFile.splitFileName``: a leading dot does not start an extension
    and a trailing dot is not an extension either.  The returned extension is
    lower-case without the dot, or ``""`` when there is none.
    """
    name = Path(full_name).name
    point_pos = name.rfind(".")
    if point_pos < 1 or point_pos + 1 == len(name):
        return name, ""
    return name[:point_pos], name[point_pos + 1 :].lower()


def is_encrypted_extension(extension: str) -> bool:
    """True when ``extension`` (with or without leading dot) is encrypted."""
    return extension.lstrip(".").lower() in ENCRYPTED_EXTENSIONS


def is_encrypted_image(extension: str) -> bool:
    """True for ``.rpgmvp`` / ``.png_``; only images support key-less restore."""
    return extension.lstrip(".").lower() in {"rpgmvp", "png_"}


def guess_version_for_extension(extension: str) -> RpgMakerVersion:
    """Infer the engine from an encrypted extension (MV default)."""
    return RpgMakerVersion.MZ if extension.lstrip(".").lower().endswith("_") else RpgMakerVersion.MV


def decrypt_extension(extension: str) -> str | None:
    """``rpgmvp`` -> ``png``.  ``None`` when the extension is unknown."""
    return _DECRYPT_MAP.get(extension.lstrip(".").lower())


def encrypt_extension(
    extension: str, version: RpgMakerVersion = RpgMakerVersion.MV
) -> str | None:
    """``png`` -> ``rpgmvp`` (MV) or ``png_`` (MZ).  ``None`` when unknown."""
    pair = _ENCRYPT_MAP.get(extension.lstrip(".").lower())
    if pair is None:
        return None
    return pair[1] if version is RpgMakerVersion.MZ else pair[0]


def media_type_for(extension: str) -> str:
    """Best-effort MIME type; empty string when unknown.

    Mirrors ``RPGFile.getMimeType``, which reports the MIME type of the *plain*
    format for both plain and encrypted extensions.
    """
    ext = extension.lstrip(".").lower()
    if ext in PNG_EXTENSIONS:
        return "image/png"
    if ext in M4A_EXTENSIONS:
        return "audio/mp4"
    if ext in OGG_EXTENSIONS:
        return "audio/ogg"
    return ""


def plain_extension_for(extension: str) -> str | None:
    """Return the plain extension for a plain *or* encrypted extension."""
    ext = extension.lstrip(".").lower()
    if ext in _DECRYPT_MAP:
        return _DECRYPT_MAP[ext]
    if ext in _ENCRYPT_MAP:
        return ext
    return None
