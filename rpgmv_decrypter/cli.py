"""Command line interface for :mod:`rpgmv_decrypter`.

Usage::

    python -m rpgmv_decrypter decrypt --auto-key "MyGame" -o decrypted
    python -m rpgmv_decrypter detect-key "MyGame/www/data/System.json"
    python -m rpgmv_decrypter info "MyGame/www/img/pictures/hero.rpgmvp"

``rpgmv_decrypter/cli.py`` may also be executed directly
(``python rpgmv_decrypter/cli.py ...``).

Exit codes: ``0`` every processed file succeeded, ``1`` at least one file
failed, ``2`` usage or argument error (bad or missing key, unknown path, bad
option values).
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path
from typing import Sequence

if __package__ in (None, ""):  # pragma: no cover - `python rpgmv_decrypter/cli.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rpgmv_decrypter import __version__
from rpgmv_decrypter.api import (
    DecryptOptions,
    FileOutcome,
    RestoreResult,
    decrypt_paths,
    detect_key,
    encrypt_paths,
    expand_inputs,
    restore_png_paths,
    write_zip,
    archive_path_for,
)
from rpgmv_decrypter.decrypter import (
    DEFAULT_HEADER_LEN,
    DEFAULT_REMAIN,
    DEFAULT_SIGNATURE,
    DEFAULT_VERSION,
    Decrypter,
)
from rpgmv_decrypter.exceptions import DecrypterError
from rpgmv_decrypter.filetypes import (
    DECRYPT_EXTENSIONS,
    ENCRYPT_EXTENSIONS,
    ENCRYPTED_EXTENSIONS,
    LZ_EXTENSIONS,
    RpgMakerVersion,
    decrypt_extension,
    encrypt_extension,
    guess_version_for_extension,
    media_type_for,
    split_name,
)

__all__ = ["build_parser", "main"]

PROG = "rpgmv-decrypter"

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2

#: Extensions ``info`` looks at when it walks a directory.  Explicitly named
#: files are always inspected, whatever their extension.
INFO_EXTENSIONS: frozenset[str] = ENCRYPTED_EXTENSIONS | ENCRYPT_EXTENSIONS | LZ_EXTENSIONS

#: Extensions whose content can carry an encryption key: encrypted *images*
#: (the key is recoverable from the second header block) and data files.
KEY_CANDIDATE_EXTENSIONS: frozenset[str] = frozenset({"rpgmvp", "png_"}) | LZ_EXTENSIONS

_MEDIA_KINDS = {"png": "image", "ogg": "audio", "m4a": "audio"}

_EXAMPLE_KEY = "1a2b3c4d5e6f708192a3b4c5d6e7f809"

_EPILOG = f"""\
exit codes:
  0  every processed file succeeded (skipped files do not fail the run)
  1  at least one file failed
  2  usage or argument error (bad or missing key, unknown path, bad options)

options may be written before or after the subcommand.

examples:
  python -m rpgmv_decrypter decrypt -k {_EXAMPLE_KEY} MyGame/www/img
  python -m rpgmv_decrypter decrypt --auto-key MyGame -o decrypted --zip decrypted.zip
  python -m rpgmv_decrypter encrypt -k {_EXAMPLE_KEY} hero.png --rpg-maker MZ
  python -m rpgmv_decrypter restore MyGame/www/img/pictures -o restored
  python -m rpgmv_decrypter detect-key MyGame/www/data/System.json
  python -m rpgmv_decrypter info MyGame/www/img/pictures/hero.rpgmvp

--version prints the package version; inside a subcommand --version sets the
fake header version (--header-len/--signature/--version/--remain).
"""


# ----------------------------------------------------------------------
# small helpers
# ----------------------------------------------------------------------
def _format_size(size: int) -> str:
    """Human readable size using B/KiB/MiB/GiB."""
    value = float(max(int(size), 0))
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GiB"  # pragma: no cover - the loop always returns


def _one_line(text: str) -> str:
    """Collapse whitespace so a message stays on a single line."""
    return " ".join(str(text).split())


def _extension_list(extensions: frozenset[str]) -> str:
    return "/".join(f".{extension}" for extension in sorted(extensions))


def _describe_extension(extension: str) -> str:
    """A human readable description of an extension for ``info``."""
    if not extension:
        return "none"
    if extension in ENCRYPTED_EXTENSIONS:
        plain = decrypt_extension(extension) or "?"
        version = guess_version_for_extension(extension).value
        kind = _MEDIA_KINDS.get(plain, "file")
        return f".{extension} -> plain .{plain} (encrypted {kind}, RPG Maker {version})"
    if extension in ENCRYPT_EXTENSIONS:
        mv = encrypt_extension(extension, RpgMakerVersion.MV)
        mz = encrypt_extension(extension, RpgMakerVersion.MZ)
        return (
            f".{extension} (plain {_MEDIA_KINDS.get(extension, 'file')}; "
            f"encrypts to .{mv} for MV or .{mz} for MZ)"
        )
    if extension in LZ_EXTENSIONS:
        return f".{extension} (data file that may contain the encryption key)"
    mime = media_type_for(extension)
    if mime:
        return f".{extension} ({mime}; not supported for en-/decryption)"
    return f".{extension} (unsupported by this tool)"


def _configure_streams() -> None:
    """Never crash while printing a path the console cannot encode."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(errors="backslashreplace")
        except Exception:  # pragma: no cover - exotic stream objects
            pass


def _usage_error(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return EXIT_USAGE


def _exit_code_from_system_exit(exc: SystemExit) -> int:
    """``main()`` returns the exit code instead of letting argparse raise."""
    code = exc.code
    if code is None:
        return EXIT_OK
    if isinstance(code, int):
        return code
    print(code, file=sys.stderr)
    return EXIT_USAGE


# ----------------------------------------------------------------------
# parser
# ----------------------------------------------------------------------
def _rpg_maker_type(value: str) -> str:
    return value.upper()


def _make_common_parent(*, with_header_version: bool) -> argparse.ArgumentParser:
    """Options shared by every subcommand.

    Defaults use :data:`argparse.SUPPRESS` so a value given *before* the
    subcommand is not overwritten by the subcommand's own defaults.
    """
    parent = argparse.ArgumentParser(add_help=False)

    verbosity = parent.add_mutually_exclusive_group()
    verbosity.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        default=argparse.SUPPRESS,
        help="only print the summary on stdout (per-file problems still go to stderr)",
    )
    verbosity.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=argparse.SUPPRESS,
        help="print one line per file plus the resolved settings",
    )

    header = parent.add_argument_group("header options")
    header.add_argument(
        "--header-len",
        type=int,
        default=argparse.SUPPRESS,
        metavar="N",
        help=f"header length in bytes (default: {DEFAULT_HEADER_LEN})",
    )
    header.add_argument(
        "--signature",
        default=argparse.SUPPRESS,
        metavar="HEX",
        help=f"fake header signature as hex (default: {DEFAULT_SIGNATURE})",
    )
    if with_header_version:
        header.add_argument(
            "--version",
            dest="header_version",
            default=argparse.SUPPRESS,
            metavar="HEX",
            help=f"fake header version as hex (default: {DEFAULT_VERSION})",
        )
    header.add_argument(
        "--remain",
        default=argparse.SUPPRESS,
        metavar="HEX",
        help=f"fake header remainder as hex (default: {DEFAULT_REMAIN})",
    )

    recursion = parent.add_mutually_exclusive_group()
    recursion.add_argument(
        "--recursive",
        dest="recursive",
        action="store_true",
        default=argparse.SUPPRESS,
        help="walk directories recursively (default)",
    )
    recursion.add_argument(
        "--no-recursive",
        dest="recursive",
        action="store_false",
        default=argparse.SUPPRESS,
        help="only look at the files directly inside a directory",
    )
    return parent


def _add_paths(parser: argparse.ArgumentParser, help_text: str) -> None:
    parser.add_argument("paths", nargs="+", metavar="PATH", help=help_text)


def _add_key_options(parser: argparse.ArgumentParser, *, note: str = "") -> None:
    group = parser.add_argument_group("key options")
    exclusive = group.add_mutually_exclusive_group()
    help_suffix = f" ({note})" if note else ""
    exclusive.add_argument(
        "-k",
        "--key",
        metavar="HEX",
        help="hex encryption key; only the first header-len bytes are used" + help_suffix,
    )
    exclusive.add_argument(
        "--key-file",
        metavar="PATH",
        help="read the key from the first line of PATH" + help_suffix,
    )
    exclusive.add_argument(
        "--auto-key",
        action="store_true",
        help="detect the key from the inputs (a game directory, System.json, "
        "rpg_core.js or an encrypted image)" + help_suffix,
    )


def _add_output_options(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("output options")
    group.add_argument(
        "-o",
        "--output-dir",
        metavar="DIR",
        help="write the results into DIR (created when missing); "
        "default: next to each input file",
    )
    group.add_argument(
        "--zip",
        dest="zip_path",
        nargs="?",
        const="",
        metavar="PATH",
        help="also write a ZIP archive containing every successful output; "
        "omit PATH to put it in <output>/_zip/<folder>.zip",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser (``build_parser()[...]`` never touches the disk)."""
    root_common = _make_common_parent(with_header_version=False)
    sub_common = _make_common_parent(with_header_version=True)

    parser = argparse.ArgumentParser(
        prog=PROG,
        description=(
            "Decrypt, encrypt and inspect RPG Maker MV/MZ resource files "
            "(.rpgmvp/.png_, .rpgmvo/.ogg_, .rpgmvm/.m4a_)."
        ),
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[root_common],
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"{PROG} {__version__}",
        help="print the package version and exit",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)

    # ---- decrypt ------------------------------------------------------
    decrypt = subparsers.add_parser(
        "decrypt",
        parents=[sub_common],
        help="decrypt encrypted resource files",
        description=f"Decrypt encrypted resources ({_extension_list(DECRYPT_EXTENSIONS)}).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "A key is required: use -k/--key, --key-file or --auto-key.\n"
            "Files whose fake header does not match are reported as failures; "
            "--ignore-fake-header\nforces decryption anyway."
        ),
    )
    _add_paths(decrypt, "encrypted files and/or directories to walk")
    _add_key_options(decrypt)
    _add_output_options(decrypt)
    decrypt.add_argument(
        "--ignore-fake-header",
        action="store_true",
        help="decrypt even when the fake header does not match the expected one",
    )
    decrypt.add_argument(
        "--rpg-maker",
        type=_rpg_maker_type,
        choices=("MV", "MZ"),
        default="MV",
        help="engine whose extension naming is used (default: MV)",
    )
    decrypt.set_defaults(handler=_cmd_decrypt)

    # ---- encrypt ------------------------------------------------------
    encrypt = subparsers.add_parser(
        "encrypt",
        parents=[sub_common],
        help="(re-)encrypt plain resource files",
        description=f"(Re-)encrypt plain resources ({_extension_list(ENCRYPT_EXTENSIONS)}).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "The output extension follows --rpg-maker: .png -> .rpgmvp (MV) or .png_ (MZ).\n"
            "A key is required: use -k/--key, --key-file or --auto-key."
        ),
    )
    _add_paths(encrypt, "plain files and/or directories to walk")
    _add_key_options(encrypt)
    _add_output_options(encrypt)
    encrypt.add_argument(
        "--rpg-maker",
        type=_rpg_maker_type,
        choices=("MV", "MZ"),
        default="MV",
        help="engine whose encrypted extension is produced (default: MV)",
    )
    encrypt.add_argument(
        "--ignore-fake-header",
        action="store_true",
        help="accepted for consistency; it has no effect while encrypting",
    )
    encrypt.set_defaults(handler=_cmd_encrypt)

    # ---- restore ------------------------------------------------------
    restore = subparsers.add_parser(
        "restore",
        parents=[sub_common],
        help="restore encrypted images without a key",
        description=(
            "Restore the real PNG header of .rpgmvp/.png_ images without an "
            "encryption key.\nThe first header-len bytes of the image are "
            "unrecoverable without the key, so they are\nreplaced by the "
            "standard PNG header."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="No key is needed; a key passed with -k/--key-file/--auto-key is ignored.",
    )
    _add_paths(restore, "encrypted images (.rpgmvp/.png_) and/or directories")
    _add_key_options(restore, note="accepted for consistency; restore needs no key")
    _add_output_options(restore)
    restore.set_defaults(handler=_cmd_restore)

    # ---- detect-key ---------------------------------------------------
    detect = subparsers.add_parser(
        "detect-key",
        parents=[sub_common],
        help="detect the encryption key of a file or game directory",
        description=(
            "Detect the encryption key of a System.json, an rpg_core.js, an "
            "encrypted image or a whole game directory.\nThe key is printed "
            "alone on stdout so it can be piped; the explanation goes to stderr."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Detection order: encrypted image header, plain JSON, LZ-String JSON,\n"
            "rpg_core.js scan, LZ-String compressed rpg_core.js scan."
        ),
    )
    _add_paths(detect, "files (System.json, rpg_core.js, an encrypted image) or game directories")
    _add_key_options(
        detect, note="accepted for consistency; detect-key always detects the key"
    )
    detect.set_defaults(handler=_cmd_detect_key)

    # ---- info ---------------------------------------------------------
    info = subparsers.add_parser(
        "info",
        parents=[sub_common],
        help="show what the given files are (read-only)",
        description=(
            "Print a read-only summary of the given files: the detected "
            "extension, whether the fake\nheader matches, and the detected "
            "encryption key (if the file can carry one).\nNo file is ever "
            "written."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Directories are walked and filtered to resource and data files.",
    )
    _add_paths(info, "files and/or directories to inspect")
    _add_key_options(
        info, note="optional; a supplied key is only shown in the report"
    )
    info.set_defaults(handler=_cmd_info)

    return parser


# ----------------------------------------------------------------------
# option resolution
# ----------------------------------------------------------------------
def _validate_header_options(args: argparse.Namespace) -> str | None:
    """Check header options before the library sees them; ``None`` when valid."""
    header_len = getattr(args, "header_len", DEFAULT_HEADER_LEN)
    if header_len <= 0:
        return f"--header-len must be a positive number, got {header_len}"

    fragments = (
        ("--signature", getattr(args, "signature", DEFAULT_SIGNATURE)),
        ("--version", getattr(args, "header_version", DEFAULT_VERSION)),
        ("--remain", getattr(args, "remain", DEFAULT_REMAIN)),
    )
    for option, value in fragments:
        if not Decrypter.check_hex_chars(str(value)):
            return (
                f"{option} may only contain hex characters (0-9, a-f, A-F), "
                f"got {value!r}"
            )

    structure = "".join(str(value) for _option, value in fragments)
    needed = header_len * 2
    if len(structure) < needed:
        return (
            f"--header-len {header_len} needs at least {needed} hex characters "
            f"in --signature/--version/--remain, but only {len(structure)} were given"
        )
    return None


def _validate_key(key: str, header_len: int) -> str | None:
    """Check a key the way the library will use it; ``None`` when valid."""
    if not key:
        return "the encryption key is empty; pass a hex string with -k/--key"
    if not Decrypter.check_hex_chars(key):
        return (
            "the encryption key may only contain hex characters (0-9, a-f, A-F), "
            f"got {key!r}"
        )
    if len(key) % 2:
        return f"the encryption key must have an even number of hex characters, got {len(key)}"
    needed = header_len * 2
    if len(key) < needed:
        return (
            f"the encryption key is too short: {len(key)} hex characters given "
            f"but {needed} are needed for a {header_len}-byte header"
        )
    return None


def _build_options(args: argparse.Namespace) -> DecryptOptions:
    return DecryptOptions(
        header_len=getattr(args, "header_len", DEFAULT_HEADER_LEN),
        signature=getattr(args, "signature", DEFAULT_SIGNATURE),
        version=getattr(args, "header_version", DEFAULT_VERSION),
        remain=getattr(args, "remain", DEFAULT_REMAIN),
        ignore_fake_header=bool(getattr(args, "ignore_fake_header", False)),
        rpgmaker_version=RpgMakerVersion[getattr(args, "rpg_maker", "MV")],
        recursive=bool(getattr(args, "recursive", True)),
    )


def _check_input_paths(paths: Sequence[str]) -> str | None:
    missing = [str(path) for path in paths if not Path(path).exists()]
    if missing:
        return "path does not exist: " + ", ".join(missing)
    return None


def _key_option_given(args: argparse.Namespace) -> bool:
    return bool(
        getattr(args, "key", None)
        or getattr(args, "key_file", None)
        or getattr(args, "auto_key", False)
    )


def _detect_key_from_inputs(paths: Sequence[str], header_len: int) -> tuple[str | None, str]:
    """Run :func:`detect_key` over every input; returns ``(key, description)``.

    Detection is best effort: *no* input is required to carry a key, so a
    failing file is skipped.  Every exception is reported as a description
    instead of escaping, so a broken file can never crash the CLI.
    """
    detail = ""
    for raw in paths:
        try:
            result = detect_key(raw, header_len=header_len)
        except (DecrypterError, OSError) as exc:
            detail = _one_line(str(exc))
            continue
        except Exception as exc:  # noqa: BLE001 - detection must never crash the CLI
            detail = f"detection failed: {type(exc).__name__}: {_one_line(str(exc))}"
            continue
        if result.found and result.key:
            source = result.source or Path(raw)
            return result.key, f"detected in {source} ({result.description})"
        detail = _one_line(result.detail)
    return None, detail or "no input contains a detectable encryption key"


def _resolve_key(
    args: argparse.Namespace, paths: Sequence[str], options: DecryptOptions
) -> tuple[str | None, str, str | None]:
    """Return ``(key, description, error_message)`` for -k/--key-file/--auto-key."""
    key: str | None = None
    source = ""

    given = getattr(args, "key", None)
    key_file = getattr(args, "key_file", None)

    if given:
        key = str(given).strip()
        source = "given on the command line"
    elif key_file:
        try:
            text = Path(key_file).read_text(encoding="utf-8-sig", errors="replace")
        except OSError as exc:
            return None, "", f"cannot read the key file {key_file}: {exc}"
        lines = text.splitlines()
        first = lines[0].strip() if lines else ""
        if not first:
            return None, "", f"the key file {key_file} does not contain a key on its first line"
        key = first
        source = f"read from {key_file}"
    elif getattr(args, "auto_key", False):
        detected, detail = _detect_key_from_inputs(paths, options.header_len)
        if not detected:
            return (
                None,
                "",
                f"could not detect an encryption key ({detail}); pass --key HEX instead",
            )
        key = detected
        source = detail
    else:
        return None, "", "no encryption key given; use -k/--key, --key-file or --auto-key"

    error = _validate_key(key, options.header_len)
    if error:
        return None, "", error
    return key, source, None


def _warn_ignored_key(args: argparse.Namespace, why: str) -> None:
    if _key_option_given(args):
        print(f"note: {why}; the key option is ignored", file=sys.stderr)


# ----------------------------------------------------------------------
# reporting
# ----------------------------------------------------------------------
def _print_outcome(outcome: FileOutcome, *, verbose: bool, stream) -> None:
    if outcome.error is not None:
        print(f"FAIL {outcome.source.name}: {_one_line(str(outcome.error))}", file=stream)
    elif outcome.skipped:
        print(f"SKIP {outcome.source.name}: {_one_line(outcome.reason)}", file=stream)
    else:
        source = str(outcome.source) if verbose else outcome.source.name
        destination = str(outcome.destination) if verbose else outcome.output_name
        print(
            f"OK  {source} -> {destination} ({_format_size(outcome.size)})",
            file=stream,
        )


def _write_zip_archive(
    zip_path: str,
    result: RestoreResult,
    *,
    quiet: bool,
    output_directory: str | None = None,
) -> str | None:
    """Write the ZIP of all successful outputs; returns an error message or ``None``.

    ``zip_path`` may be empty, meaning "derive a sensible path": the archive then
    goes to ``<output>/_zip/<output>.zip``, keeping it out of the results folder
    itself.  ``output_directory`` is the ``-o`` value when one was given, which is
    what makes that derivation correct for relative paths.
    """
    if not zip_path:
        # The API returns destinations relative to the given output directory, so
        # resolve first - otherwise a relative ``-o out`` would place the archive
        # next to the current directory instead of next to ``out``.
        if output_directory:
            base = Path(output_directory)
        else:
            destinations = [
                outcome.destination
                for outcome in result.succeeded
                if outcome.destination is not None
            ]
            if not destinations:
                print("warning: nothing to archive", file=sys.stderr)
                return None
            base = Path(destinations[0]).parent
        zip_path = str(archive_path_for(base))
        archive_name = base.name
    else:
        archive_name = None

    try:
        written = write_zip(result.outcomes, zip_path, archive_name=archive_name)
        if written is None:
            print(
                f"warning: nothing to archive: no output was written to {zip_path}",
                file=sys.stderr,
            )
            return None
        size = written.stat().st_size
    except OSError as exc:
        return f"could not write the ZIP archive {zip_path}: {exc}"

    if not quiet:
        count = len(result.succeeded)
        print(f"ZIP  {written} ({count} file{'s' if count != 1 else ''}, {_format_size(size)})")
    return None


def _report_batch(
    result: RestoreResult,
    *,
    quiet: bool,
    verbose: bool,
    zip_path: str | None,
    output_directory: str | None = None,
) -> int:
    """Print the per-file report, the optional ZIP line and the summary."""
    exit_code = EXIT_OK

    for outcome in result.outcomes:
        if quiet and outcome.ok:
            continue
        _print_outcome(outcome, verbose=verbose, stream=sys.stderr if quiet else sys.stdout)

    # ``zip_path`` is ``None`` when the user did not ask for an archive and ""
    # when they asked for one without naming a path, so test for None explicitly.
    if zip_path is not None:
        error = _write_zip_archive(
            zip_path,
            result,
            quiet=quiet,
            output_directory=output_directory,
        )
        if error:
            print(f"error: {error}", file=sys.stderr)
            exit_code = EXIT_FAILURE

    print(result.summary())

    if result.failed:
        exit_code = EXIT_FAILURE
    if not result.succeeded and not result.failed:
        print(
            "warning: no supported files were processed; check the paths and extensions",
            file=sys.stderr,
        )
    return exit_code


def _print_settings(
    options: DecryptOptions, args: argparse.Namespace, *, key: str | None, key_note: str
) -> None:
    print(f"header len   : {options.header_len}")
    print(f"signature    : {options.signature}")
    print(f"version      : {options.version}")
    print(f"remain       : {options.remain}")
    print(f"rpg maker    : {options.rpgmaker_version.value}")
    print(f"recursive    : {'yes' if options.recursive else 'no'}")
    output_dir = getattr(args, "output_dir", None)
    print(f"output dir   : {output_dir if output_dir else '(next to each input)'}")
    if key:
        print(f"key          : {key} ({key_note})")


# ----------------------------------------------------------------------
# subcommand handlers
# ----------------------------------------------------------------------
def _run_batch(args: argparse.Namespace, *, mode: str) -> int:
    quiet = bool(getattr(args, "quiet", False))
    verbose = bool(getattr(args, "verbose", False))
    paths = list(args.paths)

    error = _validate_header_options(args)
    if error:
        return _usage_error(error)
    error = _check_input_paths(paths)
    if error:
        return _usage_error(error)

    options = _build_options(args)
    key: str | None = None
    key_note = ""

    if mode in ("decrypt", "encrypt"):
        key, key_note, error = _resolve_key(args, paths, options)
        if error:
            return _usage_error(error)
    else:
        _warn_ignored_key(args, "restore works without a key")

    if verbose:
        _print_settings(options, args, key=key, key_note=key_note)

    output_dir = getattr(args, "output_dir", None)
    if mode == "decrypt":
        result = decrypt_paths(paths, key, output_dir, options=options)
    elif mode == "encrypt":
        result = encrypt_paths(paths, key, output_dir, options=options)
    else:
        result = restore_png_paths(paths, output_dir, options=options)

    # ``archive_path_for`` expects the directory whose *sibling* ``_zip`` folder
    # should hold the archive, so pass the parent of the results directory.
    return _report_batch(
        result,
        quiet=quiet,
        verbose=verbose,
        zip_path=getattr(args, "zip_path", None),
        output_directory=str(Path(output_dir).resolve()) if output_dir else None,
    )


def _cmd_decrypt(args: argparse.Namespace) -> int:
    return _run_batch(args, mode="decrypt")


def _cmd_encrypt(args: argparse.Namespace) -> int:
    return _run_batch(args, mode="encrypt")


def _cmd_restore(args: argparse.Namespace) -> int:
    return _run_batch(args, mode="restore")


def _cmd_detect_key(args: argparse.Namespace) -> int:
    quiet = bool(getattr(args, "quiet", False))
    verbose = bool(getattr(args, "verbose", False))

    error = _validate_header_options(args)
    if error:
        return _usage_error(error)
    error = _check_input_paths(list(args.paths))
    if error:
        return _usage_error(error)
    _warn_ignored_key(args, "detect-key always detects the key itself")

    header_len = getattr(args, "header_len", DEFAULT_HEADER_LEN)
    failures = 0

    for raw in args.paths:
        try:
            result = detect_key(raw, header_len=header_len)
        except (DecrypterError, OSError) as exc:
            failures += 1
            print(f"FAIL {raw}: {_one_line(str(exc))}", file=sys.stderr)
            continue
        except Exception as exc:  # noqa: BLE001 - report, never dump a traceback
            failures += 1
            print(
                f"FAIL {raw}: key detection failed unexpectedly: "
                f"{type(exc).__name__}: {_one_line(str(exc))}",
                file=sys.stderr,
            )
            continue

        if not result.found or not result.key:
            failures += 1
            print(
                f"could not detect an encryption key in {raw}: {_one_line(result.detail)}",
                file=sys.stderr,
            )
            if verbose and result.tried:
                print(f"  strategies tried: {', '.join(result.tried)}", file=sys.stderr)
            continue

        # The key alone on stdout; everything else on stderr, so it can be piped.
        print(result.key)
        if not quiet:
            source = result.source or Path(raw)
            print(
                f"detected key in {source}: {result.description}",
                file=sys.stderr,
            )
            if not result.confirmed:
                # Header values could not be confirmed against the file, and the
                # cipher has no key check, so warn instead of implying the key is
                # verified.
                print(
                    "warning: the header values could not be verified against this "
                    "file, so this key is unverified; decrypting with a wrong key "
                    "silently corrupts the first 16 bytes. Pass --header-len/"
                    "--signature/--version/--remain if you know them.",
                    file=sys.stderr,
                )
            if verbose and result.tried:
                print(f"  strategies tried: {', '.join(result.tried)}", file=sys.stderr)

    return EXIT_FAILURE if failures else EXIT_OK


def _print_info_block(
    path: Path,
    data: bytes,
    *,
    extension: str,
    decrypter: Decrypter,
    supplied_key: str | None,
    verbose: bool,
) -> None:
    print(f"{path}")
    print(f"  extension  : {_describe_extension(extension)}")
    print(f"  size       : {_format_size(len(data))}")

    if not data:
        print("  fake header: n/a (the file is empty)")
        print("  key        : n/a (the file is empty)")
        return

    header_len = decrypter.header_len
    if decrypter.verify_fake_header(data):
        print(f"  fake header: matches ({decrypter.fake_header.hex()})")
    else:
        print(f"  fake header: does not match (first bytes {data[:header_len].hex()})")

    if extension not in KEY_CANDIDATE_EXTENSIONS:
        print(
            "  key        : not applicable (only JSON, rpg_core.js and encrypted "
            "images carry a key)"
        )
        return

    try:
        detected = detect_key(path, header_len=header_len)
    except (DecrypterError, OSError) as exc:
        print(f"  key        : detection failed ({_one_line(str(exc))})")
        return
    except Exception as exc:  # noqa: BLE001 - a broken file must not abort `info`
        print(
            f"  key        : detection failed "
            f"({type(exc).__name__}: {_one_line(str(exc))})"
        )
        return

    if not detected.found or not detected.key:
        print(f"  key        : not found ({_one_line(detected.detail)})")
        return

    suffix = ""
    if supplied_key:
        if detected.key.lower() == supplied_key.lower():
            suffix = " (matches the key given on the command line)"
        else:
            suffix = " (differs from the key given on the command line)"
    print(f"  key        : {detected.key} ({detected.description}){suffix}")
    if verbose and detected.tried:
        print(f"  strategies : {', '.join(detected.tried)}")


def _cmd_info(args: argparse.Namespace) -> int:
    quiet = bool(getattr(args, "quiet", False))
    verbose = bool(getattr(args, "verbose", False))
    paths = list(args.paths)

    error = _validate_header_options(args)
    if error:
        return _usage_error(error)
    error = _check_input_paths(paths)
    if error:
        return _usage_error(error)

    options = _build_options(args)
    supplied_key: str | None = None
    key_note = ""
    if _key_option_given(args):
        supplied_key, key_note, error = _resolve_key(args, paths, options)
        if error:
            return _usage_error(error)

    decrypter = options.build_decrypter(None)
    files = expand_inputs(
        paths, allowed_extensions=INFO_EXTENSIONS, recursive=options.recursive
    )

    if supplied_key and not quiet:
        print(f"key          : {supplied_key} ({key_note})")

    failures = 0
    for path in files:
        try:
            data = path.read_bytes()
        except OSError as exc:
            failures += 1
            print(f"FAIL {path.name}: cannot read the file: {_one_line(str(exc))}", file=sys.stderr)
            continue
        _print_info_block(
            path,
            data,
            extension=split_name(path)[1],
            decrypter=decrypter,
            supplied_key=supplied_key,
            verbose=verbose,
        )

    if not files:
        print("warning: no files found in the given paths", file=sys.stderr)
    if not quiet:
        summary = f"{len(files)} file(s) checked"
        if failures:
            summary += f", {failures} failed"
        print(summary)

    return EXIT_FAILURE if failures else EXIT_OK


# ----------------------------------------------------------------------
# entry point
# ----------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return the process exit code."""
    _configure_streams()
    parser = build_parser()

    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # --help, --version and usage errors
        return _exit_code_from_system_exit(exc)

    handler = getattr(args, "handler", None)
    if handler is None:  # pragma: no cover - `required=True` prevents this
        parser.print_help(sys.stderr)
        return EXIT_USAGE

    try:
        return int(handler(args))
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    except DecrypterError as exc:
        print(f"error: {_one_line(str(exc))}", file=sys.stderr)
        return EXIT_USAGE
    except ValueError as exc:
        print(f"error: {_one_line(str(exc))}", file=sys.stderr)
        return EXIT_USAGE
    except OSError as exc:
        print(f"error: {_one_line(str(exc))}", file=sys.stderr)
        return EXIT_FAILURE
    except Exception as exc:  # noqa: BLE001 - last resort: no bare traceback for the user
        if getattr(args, "verbose", False):
            traceback.print_exc()
        print(
            f"error: unexpected failure: {type(exc).__name__}: {_one_line(str(exc))}",
            file=sys.stderr,
        )
        return EXIT_FAILURE


if __name__ == "__main__":  # pragma: no cover - `python rpgmv_decrypter/cli.py`
    sys.exit(main())
