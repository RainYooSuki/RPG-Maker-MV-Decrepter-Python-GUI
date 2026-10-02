"""Compile this project into a standalone folder of executables with Nuitka.

    python build_exe.py                 # build
    python build_exe.py --check         # verify what was built
    python build_exe.py --clean         # remove build/ and dist/ first
    python build_exe.py --jobs 12       # limit the parallel C compilers

Output is a **folder**, not a single file: ``dist/RPGMakerDecrypter/`` holding
``RPGMakerDecrypter.exe`` next to the Python runtime, Qt and the assets it needs.  A
one-file build would unpack all of that into a temporary directory on every launch, which is
a poor trade for a program that is opened often.

What goes in
------------
The ``rpgmv_decrypter`` package including its ``assets/`` (the window icon), the compiled
GUI, and a command-line launcher beside it.  Nuitka collects Qt's own plugins by itself.

What stays out
--------------
Development material - ``tests``, ``tools``, ``verification``, ``docs`` - and Qt modules the
program never imports.  ``QtSvg``, WebEngine, Multimedia, QML and a dozen more are excluded
by name, which is most of the difference between a 69 MB folder and several hundred.

Warnings
--------
* This is not the same thing as ``setup.py``.  ``setup.py`` installs the *dependencies*;
  this script compiles the program.  Run ``python setup.py deps`` first.
* Nuitka needs a C compiler.  If MSVC is not on ``PATH`` this asks Nuitka for its own
  MinGW64 build, which is downloaded once into ``.tmp/nuitka-cache`` and reused.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

#: This script sits in the project root and is run from there; everything is relative to it,
#: so the folder can be moved or renamed without editing anything.
ROOT = Path(__file__).resolve().parent

PYTHON = Path(sys.executable)
BUILD = ROOT / "build"
DIST = ROOT / "dist"
OUTPUT_NAME = "RPGMakerDecrypter"
PACKAGE_DIR = DIST / OUTPUT_NAME

#: Where Nuitka keeps its downloaded toolchain and compiled-artefact cache.  Kept inside the
#: project rather than in ``%LOCALAPPDATA%``: on a machine where that is not writable Nuitka
#: aborts with "failed to create cache directory" before compiling anything, and a build
#: folder that cleans up with the project is easier to reason about.
CACHE_DIR = ROOT / ".tmp" / "nuitka-cache"

#: The package's own version, read from ``pyproject.toml`` so there is one place to change it.
def project_version() -> str:
    try:
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    except OSError:
        return "1.0.0"
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return match.group(1) if match else "1.0.0"


#: Qt modules and standard-library packages the program never imports.  Excluding them by
#: name is what keeps the output at tens of megabytes instead of hundreds: the PySide6 wheel
#: ships WebEngine, Multimedia, QML, 3D and more, none of which this interface touches.
EXCLUDED_MODULES = (
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
    "PySide6.QtNetwork",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtMultimedia",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtBluetooth",
    "PySide6.QtPositioning",
    "PySide6.QtNfc",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtStateMachine",
    "PySide6.QtTextToSpeech",
    "PySide6.QtUiTools",
    "PySide6.QtWebChannel",
    "PySide6.QtWebSockets",
    "PySide6.Qt3DCore",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtGraphs",
    "PySide6.QtLocation",
    "PySide6.QtSpatialAudio",
    "tkinter",
    "unittest",
    "pydoc",
    "doctest",
    "pytest",
    "numpy",
    "PIL",
    "setuptools",
    "pip",
    "wheel",
)


def environment() -> dict[str, str]:
    """The environment Nuitka needs, with its cache pointed into the project."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["NUITKA_CACHE_DIR"] = str(CACHE_DIR)
    return env


def nuitka_available() -> bool:
    """Whether Nuitka can be run.

    The return code is the whole answer.  Nuitka also prints warnings to stderr - for
    instance that it is ignoring a MinGW it did not install - and treating stderr as failure
    once made this script report "Nuitka not importable" while it was installed and working.
    """
    try:
        result = subprocess.run(
            [str(PYTHON), "-m", "nuitka", "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment(),
            timeout=180,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and bool((result.stdout or "").strip())


def install_nuitka() -> int:
    """Install Nuitka, from the Tsinghua mirror when it is reachable.

    Plain build isolation, deliberately.  Nuitka is published as a source distribution only,
    so pip has to build it, and isolation is what makes that work on any machine: pip creates
    a throwaway environment and installs the backend the package declares.

    ``--no-build-isolation`` was tried here first and is the wrong tool.  It makes pip use the
    *host* environment's backend, which since Python 3.12 does not include setuptools, so the
    install fails with ``BackendUnavailable: Cannot import 'setuptools.build_meta'``.  Naming
    setuptools and wheel explicitly also works, but that is a pairing which has to hold on
    every machine forever.

    The half-hour hang that motivated the flag was this machine's sandbox refusing writes to
    ``%LOCALAPPDATA%`` - a local failure mistaken for pip's behaviour.
    """
    mirror = "https://pypi.tuna.tsinghua.edu.cn/simple"
    command = [
        str(PYTHON), "-m", "pip", "install",
        "--no-cache-dir",
        "-i", mirror,
        "nuitka",
    ]
    print("installing Nuitka from the Tsinghua mirror")
    print("  " + " ".join(command))
    return subprocess.call(command, env=environment())


def compiler_flags() -> list[str]:
    """Pick a compiler.

    MSVC when ``cl`` is on ``PATH``, otherwise Nuitka's own MinGW64 - which it insists on
    installing itself, warning that it is "very dependent on the precise one" and ignoring a
    MinGW it did not put there.  ``--mingw64`` plus ``--assume-yes-for-downloads`` lets it
    fetch that once into the cache.
    """
    if shutil.which("cl"):
        print("compiler: MSVC (cl found on PATH)")
        return []
    print("compiler: Nuitka's own MinGW64 (downloaded once into .tmp/nuitka-cache)")
    return ["--mingw64"]


def build(clean: bool, jobs: int | None) -> int:
    if not nuitka_available():
        if install_nuitka() != 0:
            return 1
        if not nuitka_available():
            print("Nuitka still cannot be run after installing it")
            return 1

    if clean:
        for directory in (PACKAGE_DIR, BUILD):
            if directory.exists():
                print(f"removing {directory.relative_to(ROOT)}")
                shutil.rmtree(directory, ignore_errors=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    DIST.mkdir(parents=True, exist_ok=True)

    version = project_version()
    command = [
        str(PYTHON), "-m", "nuitka",
        # A folder, not one file: nothing is unpacked to a temporary directory at launch.
        # Nuitka 4 replaced ``--standalone`` with this mode selector.
        "--mode=standalone",
        "--assume-yes-for-downloads",
        "--enable-plugin=pyside6",  # carries Qt's plugins and DLLs into the folder
        "--windows-console-mode=disable",  # a GUI program; no console window
        f"--windows-icon-from-ico={ROOT / 'rpgmv_decrypter' / 'assets' / 'logo.ico'}",
        f"--output-dir={BUILD}",
        f"--output-filename={OUTPUT_NAME}.exe",
        "--company-name=RPG Maker MV/MZ Decrypter",
        "--product-name=RPG Maker MV/MZ Decrypter",
        "--file-version=1.0.0.0",
        f"--product-version={version}",
        "--file-description=Decrypt, re-encrypt and restore RPG Maker MV/MZ resources",
        # Package data.  Without this the window icon is missing at runtime.
        "--include-data-dir=rpgmv_decrypter/assets=rpgmv_decrypter/assets",
        *[f"--nofollow-import-to={name}" for name in EXCLUDED_MODULES],
        "--noinclude-pytest-mode=nofollow",
        "--noinclude-setuptools-mode=nofollow",
        "--noinclude-unittest-mode=nofollow",
        "--noinclude-pydoc-mode=nofollow",
        "--noinclude-default-mode=error",
        "--follow-imports",  # Qt's signal/slot machinery imports modules dynamically
        "--python-flag=no_docstrings",
        "--python-flag=no_asserts",
        "--lto=no",  # link-time optimisation costs a lot of build time for little gain
        "--remove-output",  # drop the .build intermediates; keep the dist folder
        # Compiled from ``launcher.py`` rather than ``rpgmv_decrypter/gui.py``.  Handing
        # Nuitka the file inside the package makes it execute that file as ``__main__`` with
        # no package context, which trips the "run me as a script" bootstrap at the top of
        # gui.py - it puts the source directory on sys.path, and in a frozen build that
        # directory does not exist.  The result was::
        #
        #     ImportError: cannot import name 'ui_logic' from 'rpgmv_decrypter'
        #
        # The launcher imports the package normally, so that bootstrap never runs, and Nuitka
        # gets a real entry point - which is what makes the executable a windowed one.
        "launcher.py",
    ]
    command += compiler_flags()
    if jobs:
        command += [f"--jobs={jobs}"]

    print("\nrunning:\n  " + " \\\n  ".join(command) + "\n")
    started = time.perf_counter()
    result = subprocess.call(command, cwd=str(ROOT), env=environment())
    print(f"\nNuitka finished in {(time.perf_counter() - started) / 60:.1f} min, exit {result}")
    if result != 0:
        return result

    # Nuitka names the output folder after the *script* it compiled, not after
    # ``--output-filename`` (which only renames the executable inside).  Find it rather than
    # assume, so renaming the entry point cannot silently break the build.
    produced = BUILD / f"{OUTPUT_NAME}.dist"
    if not produced.exists():
        candidates = [p for p in BUILD.glob("*.dist") if p.is_dir()]
        if candidates:
            produced = max(candidates, key=lambda p: p.stat().st_mtime)
            print(f"found the build at {produced.relative_to(ROOT)}")
    if not produced.exists():
        print(f"no *.dist folder appeared under {BUILD.relative_to(ROOT)}")
        return 1

    if PACKAGE_DIR.exists():
        shutil.rmtree(PACKAGE_DIR, ignore_errors=True)
    shutil.move(str(produced), str(PACKAGE_DIR))
    print(f"moved the build to {PACKAGE_DIR.relative_to(ROOT)}")

    write_companion_files(version)
    return 0


def write_companion_files(version: str) -> None:
    """Write the two small files that make the folder usable on its own.

    A packaged build has no Python on ``PATH``, so the documented
    ``python -m rpgmv_decrypter`` cannot be typed there; a launcher that calls the frozen
    executable keeps the command line available.  The readme exists for the same reason a
    shipped box has one: whoever receives this folder did not build it.
    """
    launcher = PACKAGE_DIR / "decrypter-cli.bat"
    launcher.write_text(
        "@echo off\r\n"
        "rem Command line, using the interpreter bundled in this folder.\r\n"
        f'"%~dp0{OUTPUT_NAME}.exe" --cli %*\r\n',
        encoding="ascii",
    )
    print(f"wrote {launcher.relative_to(ROOT)}")

    readme = PACKAGE_DIR / "READ-ME-FIRST.txt"
    readme.write_text(
        f"""RPG Maker MV/MZ Decrypter {version}
=========================================

Double-click  {OUTPUT_NAME}.exe  to open the window.

Nothing has to be installed: Python and Qt are inside this folder.  Keep the folder
together - the .exe needs the DLLs and the PySide6 folder beside it, so to move the
tool somewhere else, move the whole folder rather than just the .exe.

Command line (from this folder):

    decrypter-cli.bat --help
    decrypter-cli.bat decrypt -k 1234567890abcdef -o out game.rpgmvp
    decrypter-cli.bat encrypt -k 1234567890abcdef --rpg-maker MZ -o out hero.png
    decrypter-cli.bat restore -o out www/img/pictures

What it does
------------
RPG Maker MV and MZ can export a project with "Encrypt game data", which wraps every
resource in a 16-byte fake header.  This tool reverses that: it decrypts .rpgmvp /
.rpgmvo / .rpgmvm (MV) and .png_ / .ogg_ / .m4a_ (MZ) back to ordinary files, encrypts
edited files again, and restores a PNG's real header without needing the key at all.

Results go to  output/<timestamp>/  next to the window, one folder per run, so nothing
is ever overwritten.

If this folder is somewhere you cannot write to - unzipped into Program Files, for
instance - then results go to your own profile instead:

    %LOCALAPPDATA%\\RPGMakerDecrypter\\output

The window says which it used, in the log pane at the bottom, the first time it opens.
"View results" browses whichever it is without needing a file manager.

Your own game files
-------------------
This is a modding and recovery tool for files you have the right to work with.  It
contains no game data and no keys.
""",
        encoding="utf-8",
    )
    print(f"wrote {readme.relative_to(ROOT)}")


def _sample_png() -> bytes:
    """A small valid PNG, so ``--check`` can prove the build really decrypts something.

    Generated rather than checked in: no binary asset in the repository, and the bytes are
    guaranteed to be a genuine PNG.
    """
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    from PySide6.QtGui import QColor, QGuiApplication, QImage

    QGuiApplication.instance() or QGuiApplication([])
    image = QImage(8, 8, QImage.Format.Format_RGB32)
    image.fill(QColor(30, 54, 99))
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(data)


def check() -> int:
    """Verify the built folder: the executable runs, the data is there, it does the job."""
    if not PACKAGE_DIR.exists():
        print(f"{PACKAGE_DIR.relative_to(ROOT)} does not exist - run the build first")
        return 1

    executable = PACKAGE_DIR / f"{OUTPUT_NAME}.exe"
    problems: list[str] = []

    print(f"=== {PACKAGE_DIR.relative_to(ROOT)} ===")
    files = [f for f in PACKAGE_DIR.rglob("*") if f.is_file()]
    total = sum(f.stat().st_size for f in files)
    print(f"  {len(files)} files, {total / 1024 / 1024:.0f} MiB")

    if not executable.exists():
        problems.append(f"{executable.name} is missing")
        print("  executable: MISSING")
        return _report(problems)
    print(f"  executable: {executable.name} ({executable.stat().st_size / 1024 / 1024:.1f} MiB)")

    assets = PACKAGE_DIR / "rpgmv_decrypter" / "assets"
    for name in ("logo.ico", "logo-16.png", "logo-256.png"):
        if not (assets / name).exists():
            problems.append(f"asset missing: rpgmv_decrypter/assets/{name}")
    if assets.exists():
        print(f"  assets: {len(list(assets.iterdir()))} files")

    platform_plugin = PACKAGE_DIR / "PySide6" / "qt-plugins" / "platforms" / "qwindows.dll"
    if platform_plugin.exists():
        print(f"  Qt platform plugin: {platform_plugin.relative_to(PACKAGE_DIR)}")
    else:
        problems.append("Qt's windows platform plugin is missing; the window cannot open")

    for extra in ("decrypter-cli.bat", "READ-ME-FIRST.txt"):
        if not (PACKAGE_DIR / extra).exists():
            problems.append(f"{extra} was not written")

    print("\n=== does the executable run? ===")
    result = subprocess.run(
        [str(executable), "--cli", "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    first = (result.stdout or result.stderr or "").strip().splitlines()
    print(f"  --cli --version: exit {result.returncode}  {first[0][:60] if first else ''}")
    if result.returncode != 0:
        problems.append(f"--cli --version returned {result.returncode}")

    print("\n=== can it actually decrypt? ===")
    scratch = BUILD / "check-roundtrip"
    if scratch.exists():
        shutil.rmtree(scratch, ignore_errors=True)
    scratch.mkdir(parents=True, exist_ok=True)
    key = "1234567890abcdef1234567890abcdef"
    source = scratch / "hero.png"
    source.write_bytes(_sample_png())
    encrypted = scratch / "hero.rpgmvp"
    decrypted = scratch / "out"

    for args, label in (
        (["--cli", "encrypt", "-k", key, "-o", str(encrypted), str(source)], "encrypt"),
        (["--cli", "decrypt", "-k", key, "-o", str(decrypted), str(encrypted)], "decrypt"),
    ):
        step = subprocess.run(
            [str(executable), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
        print(f"  {label}: exit {step.returncode}")
        if step.returncode != 0:
            problems.append(f"{label} failed with exit {step.returncode}")

    restored = decrypted / "hero.png"
    if restored.exists():
        same = restored.read_bytes() == source.read_bytes()
        print(f"  the decrypted file matches the original: {same}")
        if not same:
            problems.append("the round trip did not reproduce the original bytes")
    else:
        problems.append("decrypt produced no output")
        print("  decrypt produced no output")

    print("\n=== does the window open? ===")
    gui_env = dict(os.environ, QT_QPA_PLATFORM="offscreen", RPGMV_GUI_SELFTEST="1")
    try:
        gui = subprocess.run(
            [str(executable)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=gui_env,
            timeout=300,
        )
        line = ((gui.stdout or "") + (gui.stderr or "")).strip().splitlines()
        print(f"  self-test: exit {gui.returncode}  {line[0][:60] if line else ''}")
        if gui.returncode != 0 or "window ready" not in "\n".join(line).lower():
            problems.append("the window did not report that it opened")
    except subprocess.TimeoutExpired:
        problems.append("the window did not start within 300 s")

    return _report(problems)


def _report(problems: list[str]) -> int:
    print()
    if problems:
        print(f"{len(problems)} PROBLEM(S):")
        for item in problems:
            print(f"  - {item}")
        return 1
    print("the built folder is complete and works")
    return 0


def package() -> int:
    """ZIP the built folder, for handing to someone who will not build it themselves.

    Deliberately not ``Compress-Archive`` or ``tar``.  Both were tried and both failed here
    for reasons that have nothing to do with the archive: ``Compress-Archive`` dies when its
    ``Write-Progress`` cannot read the console, and the ``tar.exe`` this machine has aborts
    before writing anything.  A packaging step that depends on the host's tooling is a step
    that can fail on a runner for reasons the project cannot control - and the standard
    library's ``zipfile`` is right there, exact on every platform, and testable.

    The folder is zipped with its contents at the root, so unzipping produces
    ``RPGMakerDecrypter.exe`` directly rather than a nested folder.
    """
    import zipfile

    if not PACKAGE_DIR.exists():
        print(f"{PACKAGE_DIR.relative_to(ROOT)} does not exist - run the build first")
        return 1
    target = ROOT / f"{OUTPUT_NAME}-{project_version()}-windows-x64.zip"
    if target.exists():
        target.unlink()
    files = sorted(path for path in PACKAGE_DIR.rglob("*") if path.is_file())
    print(f"packing {len(files)} files into {target.name}")
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            archive.write(path, path.relative_to(PACKAGE_DIR).as_posix())
    print(f"  {target.name}: {target.stat().st_size / 1024 / 1024:.1f} MiB")

    # Prove it: an archive nobody has opened is an archive that might be empty.
    with zipfile.ZipFile(target) as archive:
        names = archive.namelist()
        broken = archive.testzip()
    executable = f"{OUTPUT_NAME}.exe"
    problems = []
    if executable not in names:
        problems.append(f"{executable} is not in the archive")
    if broken:
        problems.append(f"a member failed its CRC check: {broken}")
    if not any(name.endswith("qwindows.dll") for name in names):
        problems.append("Qt's windows platform plugin is not in the archive")
    print(f"  {len(names)} entries, CRC ok: {broken is None}")
    if problems:
        for item in problems:
            print(f"  - {item}")
        return 1
    print("the archive holds a complete, intact build")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="build_exe.py",
        description="Compile this project into dist/RPGMakerDecrypter with Nuitka.",
    )
    parser.add_argument("--check", action="store_true", help="verify an existing build")
    parser.add_argument("--clean", action="store_true", help="remove build/ and dist/ first")
    parser.add_argument("--jobs", type=int, default=None, help="parallel C compilers")
    parser.add_argument("--zip", action="store_true", help="also produce a ZIP of the build")
    parser.add_argument("--version", action="store_true", help="print the version and exit")
    arguments = parser.parse_args()

    if arguments.version:
        print(project_version())
        return 0
    if arguments.check:
        return check()
    if arguments.zip:
        return package()
    return build(arguments.clean, arguments.jobs)


if __name__ == "__main__":
    raise SystemExit(main())
