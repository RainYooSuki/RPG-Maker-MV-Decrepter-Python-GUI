"""RPG-Maker-MV & MZ file decrypter/encrypter.

A Python rewrite of Petschko's browser based "RPG-Maker-MV-Decrypter".

The package decodes and re-encodes the resource files that RPG Maker MV and MZ
produce when a project is built with "Encrypt game data" enabled:

===========================================  ==================  ==============
Encrypted extension                          Plain extension     Media type
===========================================  ==================  ==============
``.rpgmvp`` (MV) / ``.png_`` (MZ)            ``.png``            image/png
``.rpgmvo`` (MV) / ``.ogg_`` (MZ)            ``.ogg``            audio/ogg
``.rpgmvm`` (MV) / ``.m4a_`` (MZ)            ``.m4a``            audio/mp4
===========================================  ==================  ==============

The library itself only uses the Python standard library.  The desktop interface
(:mod:`rpgmv_decrypter.gui`) needs the optional ``[gui]`` extra (PySide6); the
command line interface (:mod:`rpgmv_decrypter.cli`) needs nothing extra.

Typical use::

    from rpgmv_decrypter import Decrypter, detect_key

    key = detect_key("MyGame/www/data/System.json").key
    Decrypter(key).decrypt_file("MyGame/www/img/pictures/hero.rpgmvp",
                                "hero.png")

See :mod:`rpgmv_decrypter.api` for the file-oriented convenience helpers.
"""

from .api import (
    DecryptOptions,
    DetectResult,
    RestoreResult,
    decrypt_paths,
    detect_key,
    encrypt_paths,
    restore_png_paths,
)
from .decrypter import (
    DEFAULT_HEADER_LEN,
    DEFAULT_REMAIN,
    DEFAULT_SIGNATURE,
    DEFAULT_VERSION,
    NORMAL_PNG_HEADER,
    Decrypter,
)
from .exceptions import (
    DecrypterError,
    EmptyFileError,
    InvalidFakeHeaderError,
    InvalidKeyError,
    KeyNotFoundError,
    UnsupportedFormatError,
)
from .filetypes import (
    DECRYPT_EXTENSIONS,
    ENCRYPT_EXTENSIONS,
    ENCRYPTED_EXTENSIONS,
    LZ_EXTENSIONS,
    RpgMakerVersion,
    decrypt_extension,
    encrypt_extension,
    is_encrypted_extension,
    is_encrypted_image,
    media_type_for,
)
from .key_detect import KeyDetector

__version__ = "1.0.0"

__all__ = [
    "DEFAULT_HEADER_LEN",
    "DEFAULT_REMAIN",
    "DEFAULT_SIGNATURE",
    "DEFAULT_VERSION",
    "DECRYPT_EXTENSIONS",
    "DecryptOptions",
    "Decrypter",
    "DecrypterError",
    "DetectResult",
    "ENCRYPTED_EXTENSIONS",
    "ENCRYPT_EXTENSIONS",
    "EmptyFileError",
    "InvalidFakeHeaderError",
    "InvalidKeyError",
    "KeyDetector",
    "KeyNotFoundError",
    "LZ_EXTENSIONS",
    "NORMAL_PNG_HEADER",
    "RestoreResult",
    "RpgMakerVersion",
    "UnsupportedFormatError",
    "__version__",
    "decrypt_extension",
    "decrypt_paths",
    "detect_key",
    "encrypt_extension",
    "encrypt_paths",
    "is_encrypted_extension",
    "is_encrypted_image",
    "media_type_for",
    "restore_png_paths",
]
