"""Entry point for ``python -m rpgmv_decrypter``.

Everything is implemented in :mod:`rpgmv_decrypter.cli`; this module only
forwards the command line and the resulting exit code.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - `python rpgmv_decrypter/__main__.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from rpgmv_decrypter.cli import main
else:
    from .cli import main

if __name__ == "__main__":
    sys.exit(main())
