"""``setup.py`` - install this project, or install its dependencies, with one command.

``pyproject.toml`` is the real configuration; this file exists because a lot of people
reach for ``setup.py`` first, and because it is a comfortable place to put the two
operations that are awkward to express as an install: ``setup.py deps`` (install the
runtime and test dependencies, optionally from the Tsinghua mirror) and
``setup.py check`` (report whether everything the project needs is importable).

Typical use::

    python setup.py deps                 # runtime + test dependencies
    python setup.py deps --mirror        # ... from the Tsinghua mirror
    python setup.py check                # what is missing?
    python setup.py install              # install the package itself (or: pip install .)

Under Python 3.12 ``setup.py install`` is discouraged; ``pip install .`` is equivalent
and better supported.  ``deps`` and ``check`` are the parts worth keeping here.
"""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

#: Package -> the version floor the project needs, and why.
RUNTIME = {
    "PySide6": "6.5",  # the desktop interface; PySide6-Essentials is enough
}
TEST = {
    "pytest": "7.0",
}

#: Mirrors offered by ``--mirror``.  Tsinghua is the default because the user asked for
#: it and it is the fastest of these from mainland China.
MIRRORS = {
    "tsinghua": "https://pypi.tuna.tsinghua.edu.cn/simple",
    "aliyun": "https://mirrors.aliyun.com/pypi/simple/",
    "ustc": "https://pypi.mirrors.ustc.edu.cn/simple/",
}
DEFAULT_MIRROR = "tsinghua"

#: The Qt distribution that actually provides PySide6.  ``pip install PySide6`` would
#: pull the full ~1 GB bundle with WebEngine; ``pyside6-essentials`` is the one this
#: project uses and is far smaller.
QT_PACKAGE = "pyside6-essentials"


def _installed(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def command_deps(arguments: argparse.Namespace) -> int:
    """Install the runtime (and optionally test) dependencies."""
    packages = [f"{QT_PACKAGE}>={RUNTIME['PySide6']}"]
    if not arguments.runtime_only:
        packages += [f"{name}>={floor}" for name, floor in TEST.items()]

    command = [sys.executable, "-m", "pip", "install", "--upgrade", *packages]
    if arguments.mirror:
        url = MIRRORS[arguments.mirror]
        command += ["-i", url]
        print(f"using the {arguments.mirror} mirror: {url}")
    if arguments.no_build_isolation:
        # Nuitka ships as a source distribution only, and building it in pip's isolated
        # environment hung on this machine; the same flag makes short work of it.
        command.append("--no-build-isolation")

    print("running: " + " ".join(command))
    return subprocess.call(command)


def command_check(arguments: argparse.Namespace) -> int:
    """Report what is importable, and what the project still needs."""
    print(f"python {sys.version.split()[0]}  ({sys.executable})")
    if sys.version_info < (3, 10):
        print("  the project needs Python 3.10 or newer")

    print("\nruntime:")
    missing = []
    for name in RUNTIME:
        present = _installed("PySide6")
        print(f"  {name:<10} {'found' if present else 'MISSING'}")
        if not present:
            missing.append(name)
    # The parts of Qt the interface actually uses, rather than just the top package.
    for module in ("PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets"):
        present = _installed(module)
        print(f"  {module:<18} {'found' if present else 'MISSING'}")
        if not present and "PySide6" not in missing:
            missing.append("PySide6")

    print("\ntest:")
    for name in TEST:
        present = _installed(name)
        print(f"  {name:<10} {'found' if present else 'MISSING'}")

    print("\nthe package itself:")
    present = _installed("rpgmv_decrypter")
    if present:
        import rpgmv_decrypter

        print(f"  importable from {Path(rpgmv_decrypter.__file__).parent}")
    else:
        print("  not installed as a package; running from this directory works too")

    print()
    if missing:
        print(f"install the missing pieces with:  python setup.py deps")
        return 1
    print("everything the project needs is present")
    return 0


def command_install(arguments: argparse.Namespace) -> int:
    """Delegate to pip, which is the supported way to install a modern project."""
    command = [sys.executable, "-m", "pip", "install", "."]
    if arguments.mirror:
        command += ["-i", MIRRORS[arguments.mirror]]
    print("running: " + " ".join(command))
    return subprocess.call(command, cwd=str(ROOT))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="setup.py",
        description="Install RPG Maker MV/MZ Decrypter, or its dependencies.",
    )
    subparsers = parser.add_subparsers(dest="command")

    deps = subparsers.add_parser("deps", help="install the dependencies")
    deps.add_argument(
        "--mirror",
        nargs="?",
        const=DEFAULT_MIRROR,
        choices=sorted(MIRRORS),
        help=f"use a mirror for the download (default when given: {DEFAULT_MIRROR})",
    )
    deps.add_argument(
        "--runtime-only", action="store_true", help="skip the test dependencies"
    )
    deps.add_argument(
        "--no-build-isolation",
        action="store_true",
        help="build wheels against the current environment (needed for Nuitka here)",
    )
    deps.set_defaults(func=command_deps)

    check = subparsers.add_parser("check", help="report what is missing")
    check.set_defaults(func=command_check)

    install = subparsers.add_parser("install", help="install the package itself")
    install.add_argument("--mirror", nargs="?", const=DEFAULT_MIRROR, choices=sorted(MIRRORS))
    install.set_defaults(func=command_install)
    return parser


def main() -> int:
    parser = build_parser()
    arguments = parser.parse_args()
    if not getattr(arguments, "command", None):
        parser.print_help()
        return 2
    return arguments.func(arguments)


# ----------------------------------------------------------------------------
# setuptools entry point.  ``setup()`` is called with no arguments so that all of the
# real metadata stays in pyproject.toml - one place, not two that can drift.
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in {"deps", "check", "install"}:
        raise SystemExit(main())

    try:
        from setuptools import setup
    except ImportError:
        print(
            "setuptools is not installed, so the package cannot be installed from here.\n"
            "  python -m pip install setuptools\n"
            "or run:  python setup.py check",
            file=sys.stderr,
        )
        raise SystemExit(1)

    setup()
