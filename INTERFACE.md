# API contract (frozen)

Everything below is implemented and verified in `rpgmv_decrypter/`. Treat it as
read-only: the CLI, the desktop GUI, the tests and the docs must all build on
exactly these names and signatures. If something is missing, report it rather
than editing the library.

## Constants / enums

```python
from rpgmv_decrypter import (
    DEFAULT_HEADER_LEN,      # 16
    DEFAULT_SIGNATURE,       # "5250474d56000000"
    DEFAULT_VERSION,         # "000301"
    DEFAULT_REMAIN,          # "0000000000"
    NORMAL_PNG_HEADER,       # bytes, 16 long: 89 50 4E 47 0D 0A 1A 0A 00 00 00 0D 49 48 44 52
    RpgMakerVersion,         # enum: RpgMakerVersion.MV / .MZ  (str values "MV"/"MZ", .label -> "RPG Maker MV")
    ENCRYPTED_EXTENSIONS,    # frozenset: rpgmvp rpgmvm rpgmvo png_ ogg_ m4a_
    DECRYPT_EXTENSIONS,      # == ENCRYPTED_EXTENSIONS
    ENCRYPT_EXTENSIONS,      # frozenset: png ogg m4a
    LZ_EXTENSIONS,           # frozenset: json txt js
)
```

## Extension helpers (`rpgmv_decrypter.filetypes`)

```python
split_name(path)                    -> (stem, ext_lower_no_dot)   # "" when no extension
is_encrypted_extension(ext)         -> bool     # accepts ".rpgmvp" or "rpgmvp"
is_encrypted_image(ext)             -> bool     # rpgmvp / png_ only
decrypt_extension(ext)              -> str | None   # "rpgmvp" -> "png"
encrypt_extension(ext, version=MV)  -> str | None   # "png" -> "rpgmvp" (MV) / "png_" (MZ)
media_type_for(ext)                 -> str          # MIME of the *plain* format
plain_extension_for(ext)            -> str | None
guess_version_for_extension(ext)    -> RpgMakerVersion
```

## `Decrypter` (`rpgmv_decrypter.decrypter`)

```python
Decrypter(
    encryption_key: str | None,          # hex; None allowed only for restore_png_*
    *,
    header_len: int = 16,
    signature: str = "5250474d56000000",
    version: str = "000301",
    remain: str = "0000000000",
    ignore_fake_header: bool = False,
    rpgmaker_version: RpgMakerVersion = RpgMakerVersion.MV,
)
```

Attributes: `.header_len .signature .version .remain .ignore_fake_header
.encryption_key .rpgmaker_version`, plus properties `.fake_header` (bytes),
`.normal_png_header` (bytes), `.encryption_code_array` (list[str] of 2-char chunks).

Methods:

```python
# bytes level
decrypt_bytes(data)                -> bytes      # strips fake header, XORs first block
encrypt_bytes(data)                -> bytes      # prepends fake header
restore_png_header_bytes(data)     -> bytes      # no key needed
verify_fake_header(data)           -> bool

# file level (returns the written pathlib.Path)
decrypt_file(src, dst=None)                     -> Path
encrypt_file(src, dst=None, *, version=None)    -> Path
restore_png_file(src, dst=None)                 -> Path

# streaming
decrypt_stream(src_fh, dst_fh) -> None
encrypt_stream(src_fh, dst_fh) -> None

# classmethods / statics
Decrypter.from_game_directory(path, **kwargs)                   -> Decrypter  # raises KeyNotFoundError when no key is found
Decrypter.for_version(key, version=MV, **kwargs)                -> Decrypter
Decrypter.get_normal_png_header(header_len=16)                  -> bytes      # capped at 16
Decrypter.get_key_from_png(data, header_len=16)                 -> str | None # capped at 16 key bytes
Decrypter.check_hex_chars(value)                                -> bool
Decrypter.helper_show_bits(value)                               -> str
```

Notes for UI code:
* `decrypt_file` / `encrypt_file` / `restore_png_file` default to writing **next
  to the source** with a converted extension (`hero.rpgmvp` -> `hero.png`).
* `restore_png_header_bytes(data)` == `NORMAL_PNG_HEADER + data[32:]`, which is
  **byte-exact** for a conformant PNG (its first 16 bytes are the constant PNG
  signature). For a non-standard first 16 bytes those bytes are overwritten.
* `encrypt_stream` and `decrypt_stream` raise `EmptyFileError` on empty input,
  like their bytes-level counterparts.
* Warnings to surface: an invalid key raises `InvalidKeyError`; a non-encrypted
  file raises `InvalidFakeHeaderError` (tell the user to enable
  "ignore fake header"); an empty file raises `EmptyFileError`.

## Key detection (`rpgmv_decrypter.key_detect`)

```python
detect_key(source, *, header_len=16) -> DetectResult
    # source: path (file, game dir, System.json, rpg_core.js, encrypted image)
    #         or raw bytes
require_key(source)                  -> str        # raises KeyNotFoundError

KeyDetector(header_len=16).from_bytes(data, filename="") -> DetectResult
KeyDetector(header_len=16).from_file(path)               -> DetectResult
KeyDetector.search_encryption_code(text, *, lz_string=False) -> str | None

find_data_directory(start) -> Path | None
find_system_file(start)    -> Path | None
DETECT_STRATEGIES  # ("encrypted-image", "json", "lzstring", "rpg-core", "rpg-core-lzstring")
```

`DetectResult` dataclass: `.key: str|None`, `.strategy: str|None`,
`.source: Path|None`, `.tried: list[str]`, `.detail: str`, `.found: bool`,
`.confirmed: bool`, `.description: str`, `str(result)` -> `"<key> (<how>)"` or
`"encryption key not found"`.

**`confirmed` must be honoured by any UI.** It is `False` when the key came from
unverified header values - i.e. the file does not provably start with the stock
16 byte fake header. The cipher has no key check, so such a key cannot be
validated and a wrong header length silently corrupts the first 16 bytes. In that
case `description` ends with
`", but the header values could not be verified - please confirm"` and `detail`
explains it; the key is still returned so the user can act on it. The CLI prints
the key alone on stdout and puts this warning on stderr; the desktop GUI fills
the key field and writes the same warning into its log pane.

Detection strategies are tried in this order: encrypted image header recovery,
plain JSON, LZ-String-compressed JSON, `rpg_core.js` scan, LZ-String-compressed
`rpg_core.js` scan. A project that obfuscates the key indirectly (assigned from a
variable) cannot be read statically; `result.detail` explains that case.

## Batch API (`rpgmv_decrypter.api`)

```python
DecryptOptions(
    header_len=16, signature=DEFAULT_SIGNATURE, version=DEFAULT_VERSION,
    remain=DEFAULT_REMAIN, ignore_fake_header=False,
    rpgmaker_version=RpgMakerVersion.MV, recursive=True,
)

decrypt_paths(inputs, key, output_directory=None, *, options=None) -> RestoreResult
encrypt_paths(inputs, key, output_directory=None, *, options=None) -> RestoreResult
restore_png_paths(inputs, output_directory=None, *, options=None) -> RestoreResult

expand_inputs(inputs, *, allowed_extensions, recursive=True) -> list[Path]
make_zip(outcomes, archive_name="RPG-Files.zip") -> bytes | None
    # archive_name is the FOLDER the members are stored in ("RPG-Files/hero.png");
    # pass None to store them at the archive root ("hero.png")
write_zip(outcomes, destination, *, archive_name=None) -> Path | None
    # archive_name defaults to the destination's stem
read_input_bytes(path) -> bytes
iter_zip_members(path, allowed_extensions) -> Iterator[(name, bytes)]
```

`inputs` accepts a mix of file and directory paths. Directories are walked
(recursively unless `recursive=False`) and filtered by the operation's
extensions; explicitly named files are always reported, with
`FileOutcome.skipped=True` and a `reason` when the extension does not fit.
One bad file never aborts a batch.

`FileOutcome` dataclass: `.source: Path`, `.destination: Path|None`, `.size: int`,
`.error: DecrypterError|None`, `.skipped: bool`, `.reason: str`,
`.ok: bool` (no error and not skipped), `.output_name: str`.

`RestoreResult` dataclass: `.outcomes: list[FileOutcome]`, `.key: str|None`,
`.key_source: str`, `.succeeded`, `.failed`, `.skipped` (lists),
`.total_bytes: int`, `.summary() -> str` e.g. `"3 processed, 1 skipped, 1 failed"`.

## Exceptions (`rpgmv_decrypter.exceptions`)

```
DecrypterError                  # base
├── EmptyFileError
├── InvalidFakeHeaderError
├── InvalidKeyError
├── KeyNotFoundError
└── UnsupportedFormatError
```

## Desktop GUI (`rpgmv_decrypter.gui`)

`python -m rpgmv_decrypter.gui [--lang {zh,en}]` opens the PySide6 window;
`--lang` is its only option and `zh` is the default. The window itself is
presentation only — everything testable lives next to it:

* `rpgmv_decrypter.ui_logic` — plain Python, no Qt and no third-party imports:
  * validation: `validate_key(key, header_len) -> (key | None, error)`,
    `parse_header_len(value)`, `rpgmaker_version(value)`,
    `verify_fake_header_from_choice(value)`,
    `build_options(...) -> (DecryptOptions | None, error)`
  * inputs and staging: `uploaded_paths(items)`, `expand_directories(paths, *,
    recursive=True)`, `stage_files(paths, *, job=...) -> StageResult`,
    `new_job_directory()`
  * folders: `OUTPUT_ROOT` / `output_root()` (override with
    `RPGMV_GUI_OUTPUTDIR`), `STAGE_ROOT` (override with `RPGMV_GUI_WORKDIR`),
    `pick_run_directory(now=None, root=None)` -> `<root>/<YYYY-MM-DD_HHMMSS>/`,
    `setup_logging_paths(run_directory)` -> `<run>/_logs`,
    `looks_like_output_root(path)`, `ARCHIVE_FOLDER_NAME` (`"_zip"`)
  * running: `BatchRequest`, `BatchRunner(progress).run(request) -> RunResult`,
    `ProgressReport(on_start=…, on_progress=…, on_finish=…, should_stop=…)`,
    `StageResult`, `RunResult`
  * formatting: `format_size(size)` (`1536` -> `"1.5 KiB"`)
* `rpgmv_decrypter.i18n` — the `TEXT` table (every key has a `zh` and an `en`
  entry), `tr(text_key, lang=DEFAULT_LANGUAGE, **values)`, `LANGUAGES`,
  `DEFAULT_LANGUAGE = "zh"`. An unknown key raises `KeyError` instead of
  showing a raw identifier in the window.
* `rpgmv_decrypter.gui_theme` — the design tokens (Liquid Glass palette, spacing,
  radii, type scale, glass fill) and `apply_windows_backdrop(widget, *, dark=True)`,
  which asks DWM for the Windows 11 Acrylic backdrop and returns a short status
  (`"acrylic"`, `"dark-mode-only"`, `"unsupported build"`,
  `"unsupported platform"`, `"unavailable"`). Only `"acrylic"` means the OS
  blurs the desktop behind the window; every other value is a no-op, and the
  window's own painted dark backdrop then carries the look. The specular rim and
  inner glow that make a panel read as glass are painted by
  `rpgmv_decrypter.gui.paint_glass_edges`, because Qt cannot vary one border's
  colour along its length.

## Conventions for UI layers

* Usable extensions for **decrypt**: `.rpgmvp .rpgmvm .rpgmvo .png_ .ogg_ .m4a_`
* Usable extensions for **encrypt**: `.png .ogg .m4a`
* Usable extensions for **restore** (no key): `.rpgmvp .png_`
* Key input is a hex string; empty or non-hex must be rejected client-side with a
  clear message before calling the library.
* Never claim success for a `FileOutcome` with `.ok == False`; show `.reason` or
  `str(.error)`.
* The GUI must not require network access and must run from the project venv; it
  needs PySide6 (`pip install -e ".[gui]"`) and nothing else.
