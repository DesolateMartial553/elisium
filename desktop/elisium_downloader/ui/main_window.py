"""The main window: URL bar, queue table, toolbar, status bar."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from PySide6.QtCore import QModelIndex, QPoint, QUrl, Qt
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QDesktopServices,
    QGuiApplication,
    QIcon,
    QKeySequence,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionProgressBar,
    QStackedWidget,
    QStyleOptionViewItem,
    QTableView,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from elisium_downloader.engine import runner
from elisium_downloader.engine.queue import DownloadQueue

from .bridge import QueueBridge
from .history_page import HistoryPage
from .playlist_dialog import PlaylistDialog
from .quality_dialog import QualityDialog
from .settings import Settings
from .settings_page import SettingsPage
from .model import COL_PROGRESS, COL_TITLE, COLUMNS, PERCENT_ROLE, DownloadModel

__all__ = ["MainWindow", "ProgressDelegate", "extract_urls"]

PAUSABLE = frozenset({"queued", "probing", "downloading", "merging", "converting"})
CANCELLABLE = frozenset(
    {"queued", "probing", "downloading", "merging", "converting", "paused"}
)
RETRYABLE = frozenset({"failed", "cancelled"})
SECTIONS = ("Downloads", "History", "Settings")
ACTIVE = frozenset({"probing", "downloading", "merging", "converting"})

SHORTCUTS = (
    ("Ctrl+L", "Go to the link box"),
    ("Ctrl+V", "Paste and add links (when the list is focused)"),
    ("Enter / Ctrl+Return", "Add the link in the box (playlists ask which videos)"),
    ("Ctrl+Shift+Return", "Choose the quality for the link in the box"),
    ("Space", "Pause or resume the selected download"),
    ("Ctrl+1 / Ctrl+2 / Ctrl+3", "Go to Downloads, History or Settings"),
    ("Ctrl+Q", "Quit"),
    ("F1", "Show this list"),
)


def extract_urls(text: str) -> tuple[list[str], int]:
    """Split *text* on whitespace; return (valid http(s) links, ignored count)."""
    urls: list[str] = []
    ignored = 0
    for token in text.split():
        parts = urlsplit(token)
        if parts.scheme.lower() in ("http", "https") and parts.netloc:
            urls.append(token)
        else:
            ignored += 1
    return urls, ignored


def _links(count: int) -> str:
    return f"{count} link" if count == 1 else f"{count} links"


class ProgressDelegate(QStyledItemDelegate):
    """Draws a progress bar with the percent text on it."""

    def paint(self, painter: Any, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        percent = index.data(PERCENT_ROLE)
        if percent is None:
            super().paint(painter, option, index)
            return
        style = option.widget.style() if option.widget else QApplication.style()
        # Paint the row background first, so a selected row has no gap in
        # its highlight, then the bar, then the percent as plain text in the
        # palette's own text colour (always readable, never on the bar fill).
        style.drawPrimitive(
            QStyle.PrimitiveElement.PE_PanelItemViewItem, option, painter, option.widget
        )
        text_width = 44
        bar = QStyleOptionProgressBar()
        bar.rect = option.rect.adjusted(6, 8, -(text_width + 8), -8)
        bar.state = option.state | QStyle.StateFlag.State_Horizontal
        bar.direction = option.direction
        bar.palette = option.palette
        bar.minimum = 0
        bar.maximum = 100
        bar.progress = int(round(percent))
        bar.textVisible = False
        style.drawControl(QStyle.ControlElement.CE_ProgressBar, bar, painter, option.widget)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        colour = (
            option.palette.highlightedText() if selected else option.palette.text()
        )
        painter.save()
        painter.setPen(colour.color())
        painter.drawText(
            option.rect.adjusted(0, 0, -6, 0),
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            f"{percent:.0f}%",
        )
        painter.restore()


class MainWindow(QMainWindow):
    def __init__(
        self,
        queue: DownloadQueue,
        bridge: QueueBridge | None = None,
        parent: QWidget | None = None,
        *,
        settings: Settings | None = None,
        settings_path: str | Path | None = None,
        version_fn: Callable[[], str | None] | None = None,
        probe_fn: Callable[[str], dict[str, Any]] | None = None,
        thumbnail_fetcher: Callable[..., None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.queue = queue
        self._probe_fn = probe_fn or self._default_probe
        self._thumbnail_fetcher = thumbnail_fetcher
        self.settings = settings or Settings()
        self._settings_path = settings_path
        self._version_fn = version_fn
        self.setWindowTitle("Elisium Downloader")
        self.resize(900, 520)

        self.bridge = bridge or QueueBridge(queue, self)
        self.model = DownloadModel(self)
        self.bridge.event.connect(self._on_event)
        self.model.load(queue.items())

        self._build_ui()
        self._build_actions()
        self._build_shortcuts()
        self._wire_tab_order()
        self._refresh_ui()

    # -- construction ----------------------------------------------------
    def _build_ui(self) -> None:
        downloads_page = QWidget(self)
        layout = QVBoxLayout(downloads_page)

        row = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("Paste a video link")
        self.url_edit.setClearButtonEnabled(True)
        self.url_edit.setAccessibleName("Video link")
        self.url_edit.setAccessibleDescription(
            "Type or paste one or more video links, then press Enter to add them."
        )
        self.paste_button = QPushButton("Paste")
        self.paste_button.setAccessibleName("Paste")
        self.paste_button.setAccessibleDescription(
            "Add the links from the clipboard to the download list."
        )
        self.add_button = QPushButton("Add")
        self.add_button.setAccessibleName("Add")
        self.add_button.setAccessibleDescription(
            "Add the link in the box to the download list."
        )
        row.addWidget(self.url_edit, 1)
        row.addWidget(self.paste_button)
        self.options_button = QPushButton("Options...")
        self.options_button.setAccessibleName("Options")
        self.options_button.setAccessibleDescription(
            "Check the link and choose the quality before adding it."
        )
        row.addWidget(self.add_button)
        row.addWidget(self.options_button)
        layout.addLayout(row)

        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setAccessibleName("Downloads")
        self.table.setAccessibleDescription(
            "List of downloads with status, progress, speed, time left and size."
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setItemDelegateForColumn(COL_PROGRESS, ProgressDelegate(self.table))
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(COL_TITLE, QHeaderView.ResizeMode.Stretch)
        for column in range(1, len(COLUMNS)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        for column, width in zip(range(1, len(COLUMNS)), (130, 150, 90, 70, 90), strict=True):
            self.table.setColumnWidth(column, width)
        layout.addWidget(self.table, 1)

        self.history_page = HistoryPage(self.queue, self.bridge)
        self.settings_page = SettingsPage(
            self.settings, self.queue, self._settings_path, self._version_fn
        )
        self.settings_page.settingsChanged.connect(self._on_settings_changed)
        self.stack = QStackedWidget()
        for page in (downloads_page, self.history_page, self.settings_page):
            self.stack.addWidget(page)

        self.sidebar = QListWidget()
        self.sidebar.setAccessibleName("Sections")
        self.sidebar.setAccessibleDescription(
            "Switch between Downloads, History and Settings with the arrow keys."
        )
        self.sidebar.setFixedWidth(150)
        for name in SECTIONS:
            self.sidebar.addItem(name)
        self.sidebar.setCurrentRow(0)
        self.sidebar.currentRowChanged.connect(self.show_section)

        central = QWidget(self)
        outer = QHBoxLayout(central)
        outer.addWidget(self.sidebar)
        outer.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self.summary_label = QLabel()
        self.summary_label.setAccessibleName("Download summary")
        self.statusBar().addPermanentWidget(self.summary_label)
        self.statusBar().setAccessibleName("Status bar")

        self.add_button.clicked.connect(self._add_from_box)
        self.url_edit.returnPressed.connect(self._add_from_box)
        self.options_button.clicked.connect(self.open_options)
        self.paste_button.clicked.connect(self.paste_from_clipboard)
        self.table.selectionModel().selectionChanged.connect(
            lambda *_: self._update_actions()
        )
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.doubleClicked.connect(lambda *_: self.open_folder())

    def _make_action(
        self, text: str, theme: str, fallback: QStyle.StandardPixmap, description: str, slot: Any
    ) -> QAction:
        action = QAction(QIcon.fromTheme(theme, self.style().standardIcon(fallback)), text, self)
        action.setToolTip(description)
        action.setStatusTip(description)
        action.triggered.connect(slot)
        return action

    def _build_actions(self) -> None:
        sp = QStyle.StandardPixmap
        self.pause_action = self._make_action(
            "Pause", "media-playback-pause", sp.SP_MediaPause,
            "Pause the selected download", self.pause_selected,
        )
        self.resume_action = self._make_action(
            "Resume", "media-playback-start", sp.SP_MediaPlay,
            "Resume the selected download", self.resume_selected,
        )
        self.retry_action = self._make_action(
            "Retry", "view-refresh", sp.SP_BrowserReload,
            "Try the selected download again", self.retry_selected,
        )
        self.cancel_action = self._make_action(
            "Cancel", "process-stop", sp.SP_DialogCancelButton,
            "Cancel the selected download", self.cancel_selected,
        )
        self.open_action = self._make_action(
            "Open folder", "folder-open", sp.SP_DirOpenIcon,
            "Open the folder with the finished file", self.open_folder,
        )
        self.copy_action = QAction("Copy link", self)
        self.copy_action.setToolTip("Copy the video link to the clipboard")
        self.copy_action.triggered.connect(self.copy_link)

        self.toolbar = QToolBar("Download actions", self)
        self.toolbar.setAccessibleName("Download actions")
        self.toolbar.setMovable(False)
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        for action in (
            self.pause_action, self.resume_action, self.retry_action,
            self.cancel_action, self.open_action,
        ):
            self.toolbar.addAction(action)
            button = self.toolbar.widgetForAction(action)
            button.setAccessibleName(action.text())
            button.setAccessibleDescription(action.toolTip())
            button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar)

    def _build_shortcuts(self) -> None:
        def shortcut(keys: str, slot: Any, widget: QWidget, context: Qt.ShortcutContext) -> QShortcut:
            sc = QShortcut(QKeySequence(keys), widget)
            sc.setContext(context)
            sc.activated.connect(slot)
            return sc

        window = Qt.ShortcutContext.WindowShortcut
        own = Qt.ShortcutContext.WidgetShortcut
        self._section_shortcuts = [
            shortcut(f"Ctrl+{n}", lambda n=n: self.show_section(n - 1), self, window)
            for n in (1, 2, 3)
        ]
        self._add_shortcuts = [
            shortcut("Ctrl+Return", self._add_from_box, self, window),
            shortcut("Ctrl+Enter", self._add_from_box, self, window),
            shortcut("Ctrl+Shift+Return", self.open_options, self, window),
            shortcut("Ctrl+Shift+Enter", self.open_options, self, window),
        ]
        self._shortcuts = [
            shortcut("Ctrl+V", self.paste_from_clipboard, self.table, own),
            shortcut("Space", self.toggle_pause_resume, self.table, own),
            shortcut("Ctrl+L", self.focus_url_bar, self, window),
            shortcut("Ctrl+Q", self.close, self, window),
            shortcut("F1", self.show_shortcuts, self, window),
        ]

    def _wire_tab_order(self) -> None:
        widgets: list[QWidget] = [
            self.url_edit, self.paste_button, self.add_button, self.options_button,
            self.table,
        ]
        for action in (
            self.pause_action, self.resume_action, self.retry_action,
            self.cancel_action, self.open_action,
        ):
            widgets.append(self.toolbar.widgetForAction(action))
        for first, second in zip(widgets, widgets[1:]):
            QWidget.setTabOrder(first, second)

    # -- sections --------------------------------------------------------
    def show_section(self, index: int) -> None:
        """Show page *index* (0 Downloads, 1 History, 2 Settings)."""
        if not 0 <= index < self.stack.count():
            return
        self.stack.setCurrentIndex(index)
        if self.sidebar.currentRow() != index:
            self.sidebar.setCurrentRow(index)
        self.toolbar.setVisible(index == 0)
        if index == 1:
            self.history_page.refresh()

    def _on_settings_changed(self, settings: Settings) -> None:
        self.settings = settings

    # -- model feed ------------------------------------------------------
    def _on_event(self, event: dict[str, Any]) -> None:
        self.model.handle_event(event)
        self._refresh_ui()
        item = event.get("item")
        if (
            self.settings.notify_on_done
            and event.get("type") == "state"
            and isinstance(item, dict)
            and item.get("state") == "done"
        ):
            self.statusBar().showMessage(
                f"Finished: {item.get('title') or item.get('url')}", 8000
            )

    def _refresh_ui(self) -> None:
        self._update_summary()
        self._update_actions()

    def _update_summary(self) -> None:
        counts = {"downloading": 0, "checking": 0, "queued": 0, "paused": 0,
                  "done": 0, "failed": 0, "skipped": 0, "cancelled": 0}
        for row in range(self.model.rowCount()):
            state = self.model.snapshot_at(row)["state"]
            key = {"merging": "downloading", "converting": "downloading",
                   "probing": "checking"}.get(state, state)
            if key in counts:
                counts[key] += 1
        text = ", ".join(f"{n} {name}" for name, n in counts.items() if n)
        self.summary_label.setText(text or "No downloads")

    # -- selection -------------------------------------------------------
    def selected_snapshot(self) -> dict[str, Any] | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        return self.model.snapshot_at(rows[0].row())

    def _update_actions(self) -> None:
        snap = self.selected_snapshot()
        state = snap["state"] if snap else None
        self.pause_action.setEnabled(state in PAUSABLE)
        self.resume_action.setEnabled(state == "paused")
        self.retry_action.setEnabled(state in RETRYABLE)
        self.cancel_action.setEnabled(state in CANCELLABLE)
        self.open_action.setEnabled(state == "done")
        self.copy_action.setEnabled(snap is not None)

    # -- adding links ----------------------------------------------------
    def focus_url_bar(self) -> None:
        self.url_edit.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.url_edit.selectAll()

    def _add_from_box(self) -> None:
        text = self.url_edit.text()
        if not text.strip():
            self.statusBar().showMessage("Paste a video link first", 5000)
            return
        self.add_text(text)
        self.url_edit.clear()

    def paste_from_clipboard(self) -> None:
        text = QGuiApplication.clipboard().text()
        if not text.strip():
            self.statusBar().showMessage("The clipboard has no text", 5000)
            return
        self.add_text(text)

    def _default_probe(self, url: str) -> dict[str, Any]:
        """Probe with the queue's own probe function and yt-dlp path."""
        probe = getattr(self.queue, "_probe_url", runner.probe)
        return probe(url, getattr(self.queue, "_ytdlp", "yt-dlp"))

    def add_text(self, text: str) -> None:
        """Add every link in *text* and report what happened in the status bar.

        Plain links are queued at once with the default preset. A link that
        looks like a playlist or channel is probed and the playlist picker
        opens instead, so an unknown number of videos is never queued blindly.
        """
        urls, ignored = extract_urls(text)
        playlists = [u for u in urls if runner._looks_like_playlist(u)]
        added = 0
        known = 0
        for url in urls:
            if url in playlists:
                continue
            existing = {item["id"] for item in self.queue.items()}
            try:
                snapshot = self.queue.add(url)
            except ValueError:
                ignored += 1
                continue
            if snapshot["id"] in existing:
                known += 1
                continue
            added += 1
            if not self.model.has_item(snapshot["id"]):
                self.model.upsert(snapshot)
        self._refresh_ui()
        if playlists and not (added or known or ignored):
            self.statusBar().showMessage("Checking the playlist...", 5000)
        else:
            if added == 0 and known == 1 and ignored == 0:
                message = "That video is already in the list"
            else:
                parts = []
                if added or not (known or ignored):
                    parts.append(f"Added {_links(added)}")
                if known:
                    parts.append(f"{known} already in the list")
                if ignored:
                    parts.append(f"{ignored} ignored")
                message = (
                    ", ".join(parts) if added else "No links added, " + ", ".join(parts)
                )
            self.statusBar().showMessage(message, 8000)
        for url in playlists:
            self._open_playlist(url)

    # -- choose quality / playlist dialogs -------------------------------
    def _default_preset_id(self) -> str:
        return self.settings.preset_id

    def _run_dialog(self, dialog: QDialog) -> None:
        """Show *dialog* modally (tests replace this so nothing blocks)."""
        dialog.exec()

    def open_options(self) -> None:
        """Probe the link in the box and open the Choose quality dialog."""
        text = self.url_edit.text()
        if not text.strip():
            self.statusBar().showMessage("Paste a video link first", 5000)
            return
        urls, _ignored = extract_urls(text)
        if not urls:
            self.statusBar().showMessage("That is not a link I can use", 5000)
            return
        if len(urls) > 1:
            self.statusBar().showMessage("Options works on one link at a time", 5000)
            return
        if runner._looks_like_playlist(urls[0]):
            self._open_playlist(urls[0])
        else:
            self._open_quality(urls[0])

    def _open_quality(self, url: str) -> QualityDialog:
        dialog = QualityDialog(
            url,
            self.queue,
            self._probe_fn,
            default_preset_id=self._default_preset_id(),
            thumbnail_fetcher=self._thumbnail_fetcher,
            parent=self,
        )
        dialog.itemsAdded.connect(self._on_dialog_added)
        self._run_dialog(dialog)
        return dialog

    def _open_playlist(self, url: str) -> PlaylistDialog:
        dialog = PlaylistDialog(
            url,
            self.queue,
            self._probe_fn,
            default_preset_id=self._default_preset_id(),
            parent=self,
        )
        dialog.itemsAdded.connect(self._on_dialog_added)
        self._run_dialog(dialog)
        return dialog

    def _on_dialog_added(self, results: list) -> None:
        added = known = 0
        for snapshot, is_new in results:
            if is_new:
                added += 1
            else:
                known += 1
            if not self.model.has_item(snapshot["id"]):
                self.model.upsert(snapshot)
        self.url_edit.clear()
        self._refresh_ui()
        if added == 0 and known == 1 and len(results) == 1:
            message = "That video is already in the list"
        else:
            parts = [f"Added {_links(added)}"]
            if known:
                parts.append(f"{known} already in the list")
            message = ", ".join(parts)
        self.statusBar().showMessage(message, 8000)

    # -- actions ---------------------------------------------------------
    def _selected_id(self) -> int | None:
        snap = self.selected_snapshot()
        return snap["id"] if snap else None

    def pause_selected(self) -> None:
        item_id = self._selected_id()
        if item_id is not None:
            self.queue.pause(item_id)

    def resume_selected(self) -> None:
        item_id = self._selected_id()
        if item_id is not None:
            self.queue.resume(item_id)

    def retry_selected(self) -> None:
        item_id = self._selected_id()
        if item_id is not None:
            self.queue.retry(item_id)

    def cancel_selected(self) -> None:
        item_id = self._selected_id()
        if item_id is not None:
            self.queue.cancel(item_id)

    def toggle_pause_resume(self) -> None:
        snap = self.selected_snapshot()
        if snap is None:
            return
        if snap["state"] == "paused":
            self.queue.resume(snap["id"])
        elif snap["state"] in PAUSABLE:
            self.queue.pause(snap["id"])

    def open_folder(self) -> None:
        snap = self.selected_snapshot()
        if snap is None or snap["state"] != "done":
            return
        folder = self.queue.output_dir
        file_path = snap.get("file_path")
        if file_path:
            parent = Path(file_path).parent
            if parent.is_dir():
                folder = parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def copy_link(self) -> None:
        snap = self.selected_snapshot()
        if snap is not None:
            QGuiApplication.clipboard().setText(snap["url"])
            self.statusBar().showMessage("Link copied", 5000)

    def _context_menu(self, pos: QPoint) -> None:
        index = self.table.indexAt(pos)
        if index.isValid():
            self.table.selectRow(index.row())
        menu = QMenu(self)
        for action in (
            self.pause_action, self.resume_action, self.retry_action,
            self.cancel_action, self.open_action,
        ):
            menu.addAction(action)
        menu.addSeparator()
        menu.addAction(self.copy_action)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def show_shortcuts(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Keyboard shortcuts")
        dialog.setAccessibleName("Keyboard shortcuts")
        layout = QVBoxLayout(dialog)
        for keys, meaning in SHORTCUTS:
            layout.addWidget(QLabel(f"<b>{keys}</b>  {meaning}"))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    # -- closing ---------------------------------------------------------
    def _confirm_close(self) -> str:
        """Ask what to do about running downloads: 'pause', 'keep' or 'cancel'."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Downloads are running")
        box.setText("Downloads are running. Pause them and quit?")
        pause = box.addButton("Pause and quit", QMessageBox.ButtonRole.AcceptRole)
        keep = box.addButton("Keep downloading", QMessageBox.ButtonRole.RejectRole)
        cancel = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(keep)
        box.setEscapeButton(cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked is pause:
            return "pause"
        if clicked is keep:
            return "keep"
        return "cancel"

    def closeEvent(self, event: QCloseEvent) -> None:
        active = self.queue.active_ids()
        if active:
            choice = self._confirm_close()
            if choice != "pause":
                # "Keep downloading" just cancels the close until a tray exists.
                event.ignore()
                return
            for item_id in active:
                self.queue.pause(item_id)
        self.bridge.close()
        event.accept()
