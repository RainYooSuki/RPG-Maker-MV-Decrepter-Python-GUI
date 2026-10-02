"""File-oriented convenience API.

The :class:`Decrypter` class works on bytes and single files.  This module adds
the batch behaviour the web UI and CLI need: expand directories, skip files that
do not belong, collect per-file results instead of aborting on the first error,
and optionally package everything into a ZIP archive.
"""

from __future__ import annotations

import io
import os
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Iterator, Sequence

from .decrypter import (
    DEFAULT_HEADER_LEN,
    DEFAULT_REMAIN,
    DEFAULT_SIGNATURE,
    DEFAULT_VERSION,
    Decrypter,
)
from .exceptions import DecrypterError, EmptyFileError
from .filetypes import (
    DECRYPT_EXTENSIONS,
    ENCRYPT_EXTENSIONS,
    RpgMakerVersion,
    decrypt_extension,
    encrypt_extension,
    is_encrypted_image,
    media_type_for,
    plain_extension_for,
    split_name,
)
from .key_detect import DetectResult, detect_key

__all__ = [
    "ARCHIVE_FOLDER_NAME",
    "BatchCancelled",
    "DecryptOptions",
    "DetectResult",
    "FileOutcome",
    "RestoreResult",
    "archive_path_for",
    "decrypt_paths",
    "detect_key",
    "encrypt_paths",
    "expand_inputs",
    "is_encrypted_image_path",
    "iter_zip_members",
    "make_zip",
    "media_type_of",
    "plain_extension_candidates",
    "processed_paths",
    "read_input_bytes",
    "restore_png_paths",
    "write_zip",
]

#: Files inside a project that should never be picked up by a directory walk.
_SKIP_DIRECTORIES = frozenset(
    {"node_modules", ".git", ".svn", "__macosx", "save", "saves"}
)

#: Batches smaller than this do not use a thread pool: the hand-off costs more than
#: the few reads and writes involved, and a serial loop can stop exactly where the
#: user cancelled.  Import-time constant so tests and benchmarks can reference it.
PARALLEL_MIN_FILES = 16


@dataclass
class DecryptOptions:
    """Tuning for :func:`decrypt_paths` / :func:`encrypt_paths`."""

    header_len: int = DEFAULT_HEADER_LEN
    signature: str = DEFAULT_SIGNATURE
    version: str = DEFAULT_VERSION
    remain: str = DEFAULT_REMAIN
    ignore_fake_header: bool = False
    rpgmaker_version: RpgMakerVersion = RpgMakerVersion.MV
    recursive: bool = True

    def build_decrypter(self, key: str | None) -> Decrypter:
        return Decrypter(
            key,
            header_len=self.header_len,
            signature=self.signature,
            version=self.version,
            remain=self.remain,
            ignore_fake_header=self.ignore_fake_header,
            rpgmaker_version=self.rpgmaker_version,
        )


class BatchCancelled(Exception):
    """Raise from a ``progress`` callback to stop a batch early.

    Caught by :func:`_process_batch`, which returns the outcomes that did finish
    and sets :attr:`RestoreResult.cancelled`.  Files already handed to a worker are
    allowed to complete, so nothing is left half-written.
    """


@dataclass
class FileOutcome:
    """Result of processing one file."""

    source: Path
    destination: Path | None = None
    size: int = 0
    error: DecrypterError | None = None
    skipped: bool = False
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.error is None and not self.skipped

    @property
    def output_name(self) -> str:
        if self.destination is not None:
            return self.destination.name
        return self.source.name


@dataclass
class RestoreResult:
    """Result of a batch operation."""

    outcomes: list[FileOutcome] = field(default_factory=list)
    key: str | None = None
    key_source: str = ""
    #: True when a progress callback raised :class:`BatchCancelled`, so the batch
    #: stopped early and ``outcomes`` only covers the files that finished.
    cancelled: bool = False

    @property
    def succeeded(self) -> list[FileOutcome]:
        return [outcome for outcome in self.outcomes if outcome.ok]

    @property
    def failed(self) -> list[FileOutcome]:
        return [outcome for outcome in self.outcomes if outcome.error is not None]

    @property
    def skipped(self) -> list[FileOutcome]:
        return [outcome for outcome in self.outcomes if outcome.skipped and outcome.error is None]

    @property
    def total_bytes(self) -> int:
        return sum(outcome.size for outcome in self.succeeded)

    def summary(self) -> str:
        parts = [f"{len(self.succeeded)} processed"]
        if self.skipped:
            parts.append(f"{len(self.skipped)} skipped")
        if self.failed:
            parts.append(f"{len(self.failed)} failed")
        return ", ".join(parts)


# ----------------------------------------------------------------------
# input expansion
# ----------------------------------------------------------------------
def _is_skipped_directory(path: Path) -> bool:
    return any(part.lower() in _SKIP_DIRECTORIES for part in path.parts)


def expand_inputs(
    inputs: Iterable[str | os.PathLike[str]],
    *,
    allowed_extensions: frozenset[str],
    recursive: bool = True,
) -> list[Path]:
    """Expand files and directories into a sorted list of matching files.

    Directories are walked (recursively by default) and filtered by
    ``allowed_extensions``.  Explicitly named files are always returned, even
    when their extension does not match, so the caller can report a clear error
    instead of silently doing nothing.
    """
    found: list[Path] = []
    seen: set[Path] = set()

    for item in inputs:
        path = Path(item)
        if path.is_dir():
            iterator = path.rglob("*") if recursive else path.glob("*")
            for candidate in iterator:
                if not candidate.is_file():
                    continue
                if _is_skipped_directory(candidate.relative_to(path)):
                    continue
                _, extension = split_name(candidate)
                if extension in allowed_extensions:
                    resolved = candidate.resolve()
                    if resolved not in seen:
                        seen.add(resolved)
                        found.append(candidate)
        elif path.is_file():
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                found.append(path)
        # Non-existent paths are reported by the caller through the outcome list.

    return sorted(found, key=lambda item: (str(item.parent).lower(), item.name.lower()))


def iter_zip_members(
    source: str | os.PathLike[str], allowed_extensions: frozenset[str]
) -> Iterator[tuple[str, bytes]]:
    """Yield ``(name, data)`` for the matching members of a ZIP file."""
    import zipfile as _zipfile

    with _zipfile.ZipFile(source) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            if split_name(info.filename)[1] in allowed_extensions:
                yield info.filename, archive.read(info)


def read_input_bytes(path: Path) -> bytes:
    """Read a file's bytes, transparently looking inside ZIP archives.

    Returns the *first* matching entry for a ZIP, which is what a drop-a-zip
    workflow wants.  Callers that need every entry should use
    :func:`iter_zip_members`.  Note that a ZIP without a matching member yields
    the raw archive bytes rather than raising.
    """
    if split_name(path)[1] == "zip":
        for _name, data in iter_zip_members(path, DECRYPT_EXTENSIONS | ENCRYPT_EXTENSIONS):
            return data
    return path.read_bytes()


def plain_extension_candidates(extension: str) -> set[str]:
    """Plain extensions a file with ``extension`` turns into.

    Accepts both plain and encrypted extensions, so ``rpgmvp`` and ``png`` both
    answer ``{"png"}``.  Used to skip files that were decrypted already - a game
    folder a user has processed once contains both ``hero.rpgmvp`` and
    ``hero.png``, and the second must not be treated as an encrypted input.
    """
    plain = plain_extension_for(extension)
    return {plain} if plain else set()


def processed_paths(
    inputs: Iterable[str | os.PathLike[str]],
    *,
    mode: str,
    options: DecryptOptions | None = None,
) -> set[Path]:
    """Files in ``inputs`` that are already the *output* of ``mode``.

    :param mode: ``"decrypt"`` (an encrypted file that already has its plain
        sibling), ``"encrypt"`` (a plain file that already has its encrypted
        sibling) or ``"restore"`` (same rule as decrypt)
    :returns: resolved paths that should be skipped
    """
    settings = options or DecryptOptions()
    already: set[Path] = set()

    for item in inputs:
        path = Path(item)
        if not path.is_file():
            continue
        extension = split_name(path)[1]

        if mode == "encrypt":
            candidates = {encrypt_extension(extension, settings.rpgmaker_version)}
        else:
            candidates = plain_extension_candidates(extension)
        candidates.discard(None)

        if not candidates:
            continue
        stem = path.with_suffix("")
        for candidate in candidates:
            sibling = stem.with_suffix(f".{candidate}")
            if sibling != path and sibling.is_file():
                already.add(path.resolve())
                break

    return already


# ----------------------------------------------------------------------
# batches
# ----------------------------------------------------------------------
#: Folder name used for the ZIP written next to an output directory.
ARCHIVE_FOLDER_NAME = "_zip"


def archive_path_for(output_directory: str | os.PathLike[str]) -> Path:
    """Where the ZIP belonging to the results in ``output_directory`` goes.

    The archive is kept in a ``_zip`` folder **inside** the results directory,
    so the individual files stay clean, the archive travels with the run it
    belongs to, and a later run can never be confused with an earlier one::

        output/2025-01-31_204512/hero.png     <- files
        output/2025-01-31_204512/_zip/2025-01-31_204512.zip   <- optional archive

    Passing something already inside a ``_zip`` folder is a no-op, which keeps
    the helper idempotent.
    """
    directory = Path(output_directory)
    if directory.name == ARCHIVE_FOLDER_NAME:
        directory = directory.parent
    return directory / ARCHIVE_FOLDER_NAME / f"{directory.name}.zip"


def _unique_destination(directory: Path, name: str, taken: set[Path]) -> Path:
    candidate = directory / name
    if candidate not in taken and not candidate.exists():
        taken.add(candidate)
        return candidate
    stem, extension = split_name(candidate)
    counter = 1
    while True:
        candidate = directory / f"{stem} ({counter}).{extension}"
        if candidate not in taken and not candidate.exists():
            taken.add(candidate)
            return candidate
        counter += 1


def _default_destination(source: Path, options: DecryptOptions, *, encrypt: bool) -> Path:
    stem, extension = split_name(source)
    if encrypt:
        new_extension = encrypt_extension(extension, options.rpgmaker_version)
    else:
        new_extension = decrypt_extension(extension)
    if new_extension is None:
        new_extension = f"{extension}.out"
    return source.with_name(f"{stem}.{new_extension}")


def _process_batch(
    inputs: Sequence[str | os.PathLike[str]],
    *,
    key: str | None,
    output_directory: str | os.PathLike[str] | None,
    allowed_extensions: frozenset[str],
    options: DecryptOptions,
    mode: str,
    progress: Callable[[int, int, Path], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> RestoreResult:
    """Shared implementation for decrypt/encrypt/restore batches.

    A failure on one file never aborts the batch; every input produces exactly
    one :class:`FileOutcome`.

    :param progress: optional ``(done, total, source)`` callback, called from the
        worker threads as files complete.  It must be thread-safe.  Raising
        :class:`BatchCancelled` from it stops the batch: files already finished are
        returned, the rest are left alone (files already handed to a worker run to
        completion, so nothing is left half-written).
    :param cancelled: optional ``() -> bool`` polled before each file on the serial
        path, which can stop a small batch exactly.
    """
    result = RestoreResult(key=key)
    decrypter = options.build_decrypter(key)
    out_dir = Path(output_directory) if output_directory is not None else None
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
    taken: set[Path] = set()

    files = expand_inputs(inputs, allowed_extensions=allowed_extensions, recursive=options.recursive)
    if not files:
        # Distinguish "nothing matched" from "these paths do not exist".
        for item in inputs:
            path = Path(item)
            if not path.exists():
                result.outcomes.append(
                    FileOutcome(source=path, skipped=True, reason="path does not exist")
                )
        return result

    expected = ", ".join(f".{item}" for item in sorted(allowed_extensions))

    # Resolve destinations first, on this thread: ``_unique_destination`` mutates
    # ``taken`` to avoid clashes, which is much easier to reason about serialised.
    jobs: list[tuple[Path, Path | None]] = []
    for source in files:
        _, extension = split_name(source)
        if extension not in allowed_extensions:
            result.outcomes.append(
                FileOutcome(
                    source=source,
                    skipped=True,
                    reason=f"unsupported extension '.{extension}'; expected one of {expected}",
                )
            )
            continue

        if out_dir is not None:
            new_extension = extension
            if mode == "encrypt":
                new_extension = encrypt_extension(extension, options.rpgmaker_version) or extension
            elif mode in ("decrypt", "restore"):
                new_extension = decrypt_extension(extension) or extension
            stem, _ = split_name(source)
            destination = _unique_destination(out_dir, f"{stem}.{new_extension}", taken)
        else:
            destination = _default_destination(source, options, encrypt=mode == "encrypt")
        jobs.append((source, destination))

    # The work is read -> transform -> write, and the transform releases the GIL,
    # so threads give a real speedup without the cost of processes.  Measured with
    # tools/benchmark_parallel.py (3000 files, 12 cores): 2.4x for many small
    # images, 2.4x for medium ones, 1.8x for a few large ones.
    if len(jobs) < 2:
        result.outcomes.extend(
            _process_one(decrypter, mode, source, destination) for source, destination in jobs
        )
        if progress is not None:
            for done, outcome in enumerate(result.outcomes, start=1):
                progress(done, len(jobs), outcome.source)
        return result

    # Below a few files the pool costs more than it saves (thread hand-off, and the
    # per-file work is only a couple of reads and writes), and a serial loop can
    # honour a cancel between files exactly.  Above it, the pool wins by a wide
    # margin - see tools/benchmark_parallel.py.
    if len(jobs) < PARALLEL_MIN_FILES:
        for done, (source, destination) in enumerate(jobs, start=1):
            # Asked before each file so cancelling mid-run stops here, with nothing
            # half-done; no progress event is emitted for a file that is not started.
            if cancelled is not None and cancelled():
                result.cancelled = True
                break
            result.outcomes.append(_process_one(decrypter, mode, source, destination))
            if progress is not None:
                try:
                    progress(done, len(jobs), source)
                except BatchCancelled:
                    result.cancelled = True
                    break
        return result

    workers = min(32, (os.cpu_count() or 1) + 4, len(jobs))
    outcomes: list[FileOutcome | None] = [None] * len(jobs)
    done = 0
    cancelled = False
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="rpgmv") as pool:
        futures = {
            pool.submit(_process_one, decrypter, mode, source, destination): index
            for index, (source, destination) in enumerate(jobs)
        }
        try:
            for future in as_completed(futures):
                outcomes[futures[future]] = future.result()
                # Report in *input* order: a worker finishing early must not make an
                # earlier file look finished.  Buffered until the prefix is
                # contiguous, so "n of m done" always means the first n files.
                while done < len(outcomes) and outcomes[done] is not None:
                    done += 1
                    if progress is not None:
                        progress(done, len(jobs), jobs[done - 1][0])
        except BatchCancelled:
            # Stop handing out work.  Files already running are waited for below, so
            # nothing is left writing a file after we return; whatever they produce
            # is reported like any other outcome.
            cancelled = True
            for pending in futures:
                pending.cancel()

    result.outcomes.extend(item for item in outcomes if item is not None)
    result.cancelled = cancelled
    return result


def _process_one(
    decrypter: Decrypter,
    mode: str,
    source: Path,
    destination: Path | None,
) -> FileOutcome:
    """Read, transform and write a single file.  Never raises for a bad file.

    Safe to call from a worker thread: it touches only its own paths (the
    destination was already made unique by the caller) and the decrypter, which is
    read-only once built.
    """
    try:
        data = source.read_bytes()
        if not data:
            raise EmptyFileError(f"file is empty: {source}")

        if mode == "decrypt":
            output = decrypter.decrypt_bytes(data)
        elif mode == "encrypt":
            output = decrypter.encrypt_bytes(data)
        else:
            output = decrypter.restore_png_header_bytes(data)

        if destination is not None:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(output)
        return FileOutcome(source=source, destination=destination, size=len(output))
    except DecrypterError as error:
        return FileOutcome(source=source, error=error)
    except OSError as error:
        return FileOutcome(source=source, error=DecrypterError(str(error)))


def decrypt_paths(
    inputs: Iterable[str | os.PathLike[str]],
    key: str | None,
    output_directory: str | os.PathLike[str] | None = None,
    *,
    options: DecryptOptions | None = None,
    progress: Callable[[int, int, Path], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> RestoreResult:
    """Decrypt every supported file in ``inputs``.

    :param key: hex encryption key; see :func:`detect_key` to obtain one
    :param output_directory: write results here instead of next to the inputs
    :param progress: optional ``(done, total, source)`` callback, called from the
        worker threads as files complete; raise :class:`BatchCancelled` to stop
    """
    return _process_batch(
        list(inputs),
        key=key,
        output_directory=output_directory,
        allowed_extensions=DECRYPT_EXTENSIONS,
        options=options or DecryptOptions(),
        mode="decrypt",
        progress=progress,
        cancelled=cancelled,
    )


def encrypt_paths(
    inputs: Iterable[str | os.PathLike[str]],
    key: str | None,
    output_directory: str | os.PathLike[str] | None = None,
    *,
    options: DecryptOptions | None = None,
    progress: Callable[[int, int, Path], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> RestoreResult:
    """(Re-)encrypt every supported plain file in ``inputs``.

    :param progress: optional ``(done, total, source)`` callback, called from the
        worker threads as files complete; raise :class:`BatchCancelled` to stop
    """
    return _process_batch(
        list(inputs),
        key=key,
        output_directory=output_directory,
        allowed_extensions=ENCRYPT_EXTENSIONS,
        options=options or DecryptOptions(),
        mode="encrypt",
        progress=progress,
        cancelled=cancelled,
    )


def restore_png_paths(
    inputs: Iterable[str | os.PathLike[str]],
    output_directory: str | os.PathLike[str] | None = None,
    *,
    options: DecryptOptions | None = None,
    progress: Callable[[int, int, Path], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> RestoreResult:
    """Restore encrypted image headers without an encryption key.

    :param progress: optional ``(done, total, source)`` callback, called from the
        worker threads as files complete; raise :class:`BatchCancelled` to stop
    """
    return _process_batch(
        list(inputs),
        key=None,
        output_directory=output_directory,
        allowed_extensions=frozenset({"rpgmvp", "png_"}),
        options=options or DecryptOptions(),
        mode="restore",
        progress=progress,
        cancelled=cancelled,
    )


# ----------------------------------------------------------------------
# packaging
# ----------------------------------------------------------------------
def make_zip(
    outcomes: Iterable[FileOutcome], archive_name: str | None = "RPG-Files.zip"
) -> bytes | None:
    """Bundle successfully processed files into an in-memory ZIP.

    :param archive_name: unused as a *file* name (the caller decides where the
        bytes go) - it is honoured by putting the members inside a folder of
        that name, so the same ``archive_name`` a UI shows is what the user
        actually finds in the archive.  Pass ``None`` to store the members at
        the root of the ZIP.
    :returns: the ZIP bytes, or ``None`` when there is nothing to archive
    """
    prefix = ""
    if archive_name:
        folder = Path(archive_name).stem.strip()
        if folder:
            prefix = f"{folder}/"

    buffer = io.BytesIO()
    added = 0
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for outcome in outcomes:
            if not outcome.ok or outcome.destination is None:
                continue
            archive.write(outcome.destination, arcname=f"{prefix}{outcome.destination.name}")
            added += 1
    if added == 0:
        return None
    return buffer.getvalue()


def write_zip(
    outcomes: Iterable[FileOutcome],
    destination: str | os.PathLike[str],
    *,
    archive_name: str | None = None,
) -> Path | None:
    """Write the ZIP produced by :func:`make_zip` to ``destination``.

    :param archive_name: folder name for the members inside the archive;
        defaults to the destination's stem
    """
    target = Path(destination)
    if archive_name is None:
        archive_name = target.stem
    data = make_zip(outcomes, archive_name=archive_name)
    if data is None:
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def is_encrypted_image_path(path: str | os.PathLike[str]) -> bool:
    """Convenience wrapper around :func:`rpgmv_decrypter.filetypes.is_encrypted_image`."""
    return is_encrypted_image(split_name(path)[1])


def media_type_of(path: str | os.PathLike[str]) -> str:
    """MIME type guess for a path's extension."""
    return media_type_for(split_name(path)[1])
