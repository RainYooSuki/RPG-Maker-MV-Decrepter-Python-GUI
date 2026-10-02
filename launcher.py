"""Entry point for the packaged executable.

Nuitka has no ``-m module`` form, and handing it ``rpgmv_decrypter/gui.py`` directly
makes it *execute* that file as ``__main__`` with no package context - which trips the
"run me as a script" bootstrap near the top of ``gui.py``.  That bootstrap puts the
source directory on ``sys.path`` so ``python rpgmv_decrypter/gui.py`` works; inside a
frozen build the directory does not exist, and the executable dies at startup with::

    ImportError: cannot import name 'ui_logic' from 'rpgmv_decrypter' (unknown location)

Starting from a tiny module that imports the package normally avoids the whole
situation: ``gui`` is then imported *as a module of its package*, ``__package__`` is
correct, and the bootstrap is skipped.  Building this file also gives Nuitka a real
entry point, so the result is a windowed application rather than a console one.

Not used when running from source - use ``python -m rpgmv_decrypter.gui`` there.
"""

from __future__ import annotations

import multiprocessing

from rpgmv_decrypter.gui import main

if __name__ == "__main__":
    # Harmless when unused, and it keeps a frozen build from re-launching itself if the
    # interpreter ever starts a child process.
    multiprocessing.freeze_support()
    raise SystemExit(main())
