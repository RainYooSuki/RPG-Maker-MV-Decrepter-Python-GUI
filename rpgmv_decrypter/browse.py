"""An in-application browser for a run's results.

Asking the operating system's shell to show a folder can be refused outright: in a
restricted session ``ShellExecute`` returns error 5 no matter which API phrases the
request - Qt's ``QDesktopServices``, ``os.startfile``, PowerShell, .NET and the raw
``ShellExecuteExW`` all end in the same call, and starting ``explorer.exe`` dies with
``0xC0000142``.

What is *not* refused is a window of our own: measured in the same session, Qt's native
``QFileDialog`` opens normally while ``ShellExecute`` fails.  So the results are shown
**inside the application** instead - which needs no shell at all, and has the side benefit
of working the same way on every platform.

The window is therefore a viewer, not a launcher: it lists the folder, previews what the
toolkit can render, and puts the selected path on the clipboard.  Nothing in it asks the
system to open a file or a folder.

Layout: the listing keeps the left - and stretchable - side of the window, the preview is
a narrow fixed column on the right.  An earlier revision put the preview *below* the
listing, where it took rows away from it; the user asked for the two to sit side by side
so the listing is never covered.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import gui_theme as theme
from .i18n import tr

#: Extensions worth rendering in the preview pane.
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}

#: How large the preview may get, in pixels, on its longest side.
PREVIEW_MAX = 260

#: The width of the preview column: the largest preview there can be, plus the preview
#: label's own padding and border.  Fixed, so the column can never grow into the listing.
PREVIEW_PANE_WIDTH = PREVIEW_MAX + 2 * theme.SPACE_SM + 2

#: The listing's first column takes whatever is left after the two fixed ones, so the table
#: always fits its viewport and no horizontal scrollbar ever covers the bottom rows.
STRETCH_COLUMN = 0

#: Column widths for the listing's second and third columns.  Fixed, for the same reason the
#: main table's are: measuring every row's text on the first layout pass is what froze the
#: window on a big folder - so nothing here asks for ``ResizeToContents``.
COLUMN_WIDTHS = {1: 78, 2: 96}


def _format_size(size: int) -> str:
    """A human-readable size.  Deliberately duplicated from ui_logic rather than imported:
    this module is about looking at files, and importing the run machinery would drag the
    whole batch pipeline into a dialog."""
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GiB"


class BrowsedFolder:
    """The contents of one folder, read once."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.folders: list[Path] = []
        self.files: list[Path] = []
        self.error: str | None = None
        try:
            for entry in sorted(path.iterdir(), key=lambda item: (item.is_file(), item.name.lower())):
                if entry.is_dir():
                    self.folders.append(entry)
                else:
                    self.files.append(entry)
        except OSError as error:
            self.error = str(error)

    @property
    def entries(self) -> list[Path]:
        """Folders first, then files - the order a file manager would show them in."""
        return [*self.folders, *self.files]

    @property
    def total_size(self) -> int:
        total = 0
        for entry in self.files:
            try:
                total += entry.stat().st_size
            except OSError:
                pass
        return total

    def item_for(self, entry: Path) -> list[str]:
        if entry.is_dir():
            return [f"\U0001f4c1 {entry.name}", tr("browse_folder_row"), ""]
        return [entry.name, entry.suffix.lstrip(".").upper() or "-", _format_size(_size_of(entry))]


def _size_of(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


class BrowseDialog(QDialog):
    """Lists a folder on the left and previews the selected file on the right.

    Two ways out, and both work in every environment: **copy the path** - no shell involved
    - and **close**.  Nothing here asks the system to open a file or a folder; that is the
    request a restricted session refuses, and the route that does not need it is the path
    on the clipboard.

    The listing is the wide, stretchable side; the preview is a fixed narrow column beside
    it, so it cannot cover a single row of the listing.

    Folders are entered by **double-clicking** them.  That is what a file manager does, and
    what the main window's own results table already uses, so it needs no explaining.  A
    single click stays plain selection on purpose: selecting a row is what fills the
    preview, and click-to-enter would make it impossible to look at a folder without
    leaving the listing.  A double-click on a *file* changes nothing - the preview it
    already shows is the only thing this window offers for a file.
    """

    def __init__(self, path: Path, lang: str = "zh", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.lang = lang
        self._history: list[Path] = []
        self.setObjectName("browseDialog")
        self.setMinimumSize(720, 520)
        self.setStyleSheet(f"QDialog#browseDialog {{ background: {theme.BACKDROP_BASE}; }}")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(theme.SPACE_LG, theme.SPACE_LG, theme.SPACE_LG, theme.SPACE_LG)
        outer.setSpacing(theme.SPACE_SM)

        self.title = QLabel()
        self.title.setFont(theme.ui_font(size_role="title"))
        self.title.setStyleSheet(f"color: {theme.TEXT_PRIMARY}; background: transparent;")
        outer.addWidget(self.title)

        self.where = theme.HintLabel()
        self.where.setWordWrap(True)
        outer.addWidget(self.where)

        self.table = QTableWidget(0, 3, self)
        self.table.setObjectName("browseTable")
        self.table.setHorizontalHeaderLabels(
            [
                tr("browse_column_name", self.lang),
                tr("browse_column_type", self.lang),
                tr("browse_column_size", self.lang),
            ]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(STRETCH_COLUMN, QHeaderView.ResizeMode.Stretch)
        for column, width in COLUMN_WIDTHS.items():
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(column, width)
        self.table.itemSelectionChanged.connect(self._on_selection)
        self.table.itemDoubleClicked.connect(self._on_double_click)
        self.table.setStyleSheet(
            f"""
            QTableWidget#browseTable {{
                background: transparent; color: {theme.TEXT_PRIMARY};
                border: 1px solid {theme.GLASS_BORDER_SOFT};
                border-radius: {theme.RADIUS_SM}px;
                selection-background-color: rgba(93,118,186,120);
                selection-color: #ffffff;
            }}
            QTableWidget#browseTable::item {{ padding: 5px 8px; }}
            QHeaderView::section {{
                background: rgba(255,255,255,18);
                color: {theme.TEXT_SECONDARY};
                border: none;
                border-bottom: 1px solid {theme.GLASS_BORDER_SOFT};
                padding: 7px 8px;
                font-weight: 600;
            }}
            """
        )

        # Left: the listing, which takes every pixel the preview column does not need.
        # Right: the preview, at a fixed width so the listing can never be covered.
        content = QHBoxLayout()
        content.setSpacing(theme.SPACE_MD)
        content.addWidget(self.table, 1)
        content.addWidget(self._preview_pane())
        outer.addLayout(content, 1)

        self.summary = theme.HintLabel()
        outer.addWidget(self.summary)

        buttons = QHBoxLayout()
        buttons.setSpacing(theme.SPACE_SM)
        self.up_button = self._button("browse_up", self._on_up)
        self.copy_button = self._button("browse_copy_path", self._on_copy)
        self.close_button = self._button("close", self.accept)
        for button in (self.up_button, self.copy_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        buttons.addWidget(self.close_button)
        outer.addLayout(buttons)

        self.show_folder(path)

    def _preview_pane(self) -> QWidget:
        """The right-hand column: a caption over the preview, at a fixed width."""
        pane = QWidget(self)
        pane.setObjectName("browsePreviewPane")
        pane.setFixedWidth(PREVIEW_PANE_WIDTH)
        column = QVBoxLayout(pane)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(theme.SPACE_SM)

        self.preview_caption = theme.SectionLabel(tr("browse_preview", self.lang), pane)
        self.preview_caption.setObjectName("browsePreviewCaption")
        column.addWidget(self.preview_caption)

        self.preview = QLabel(pane)
        self.preview.setObjectName("browsePreview")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setWordWrap(True)
        self.preview.setMinimumHeight(120)
        self.preview.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; background: transparent;"
            f" border: 1px dashed {theme.GLASS_BORDER_SOFT};"
            f" border-radius: {theme.RADIUS_SM}px; padding: {theme.SPACE_SM}px;"
        )
        column.addWidget(self.preview, 1)
        return pane

    def _button(self, key: str, slot: object) -> QPushButton:
        button = QPushButton(tr(key, self.lang))
        button.setObjectName(key)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setMinimumHeight(theme.input_min_height())
        button.clicked.connect(slot)  # type: ignore[arg-type]
        return button

    # -- contents ------------------------------------------------------
    def show_folder(self, path: Path, *, remember: bool = True) -> None:
        """List ``path``.

        ``remember`` is what keeps the history honest: going *forward* pushes the folder
        being left behind, going *back* must not, or the stack grows on every press of "up"
        and the button never disables.
        """
        if remember and self.table.rowCount() and self.current != path:
            self._history.append(self.current)
        self._browsed = BrowsedFolder(path)
        self.current = self._browsed.path

        entries = self._browsed.entries
        self.table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            for column, text in enumerate(self._browsed.item_for(entry)):
                item = QTableWidgetItem(text)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, str(entry))
                self.table.setItem(row, column, item)
        if entries:
            self.table.selectRow(0)

        self.title.setText(path.name or str(path))
        self.where.setText(str(path))
        if self._browsed.error:
            self.summary.setText(tr("browse_unreadable", self.lang, error=self._browsed.error))
        else:
            self.summary.setText(
                tr(
                    "browse_summary",
                    self.lang,
                    folders=len(self._browsed.folders),
                    files=len(self._browsed.files),
                    size=_format_size(self._browsed.total_size),
                )
            )
        self.up_button.setEnabled(bool(self._history))
        self._on_selection()

    def _selected(self) -> Path | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if item is None:
            return None
        stored = item.data(Qt.ItemDataRole.UserRole)
        return Path(stored) if stored else None

    # -- preview -------------------------------------------------------
    def _show_hint(self, text: str) -> None:
        """Put explanatory text where the picture would be."""
        self.preview.setPixmap(QPixmap())
        self.preview.setText(text)

    def _on_selection(self) -> None:
        entry = self._selected()
        self.copy_button.setEnabled(entry is not None)
        if entry is None:
            self._show_hint(tr("browse_pick_a_file", self.lang))
            return
        if entry.is_dir():
            # The preview cannot show a folder, so it says how to get into it instead.
            self._show_hint(tr("browse_enter_folder", self.lang))
            return
        if entry.suffix.lower() not in IMAGE_SUFFIXES:
            self._show_hint(f"{entry.name}\n{tr('browse_no_preview', self.lang)}")
            return
        pixmap = QPixmap(str(entry))
        if pixmap.isNull():
            self._show_hint(tr("browse_unreadable", self.lang, error=entry.name))
            return
        scaled = pixmap.scaled(
            PREVIEW_MAX,
            PREVIEW_MAX,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview.setPixmap(scaled)
        self.preview.setText("")

    # -- actions -------------------------------------------------------
    def _on_up(self) -> None:
        if self._history:
            self.show_folder(self._history.pop(), remember=False)

    def _on_copy(self) -> None:
        entry = self._selected() or self.current
        from PySide6.QtGui import QGuiApplication

        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(str(entry))
        self.summary.setText(tr("browse_copied", self.lang, path=str(entry)))

    def _on_double_click(self, _item: QTableWidgetItem) -> None:
        """Descend into the double-clicked folder; a file needs no second action.

        Double-click rather than a single click, see the class docstring: selection alone
        drives the preview, so only the deliberate gesture navigates.
        """
        entry = self._selected()
        if entry is not None and entry.is_dir():
            self.show_folder(entry)
