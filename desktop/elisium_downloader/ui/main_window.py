"""The main window: top bar (mark, section links, link field, Download), count cards, download rows, status bar."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from PySide6.QtCore import QEvent, QObject, QPoint, QSize, QTimer, QUrl, Qt
from PySide6.QtGui import (
    QAccessible,
    QAccessibleAnnouncementEvent,
    QAction,
    QCloseEvent,
    QDesktopServices,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QIcon,
    QKeySequence,
    QPalette,
    QPen,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProxyStyle,
    QPushButton,
    QStyle,
    QStyleOption,
    QStackedWidget,
    QTableView,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from elisium_downloader.engine import runner
from elisium_downloader.engine.queue import DownloadQueue

from . import theme
from .bridge import QueueBridge
from .history_page import HistoryPage
from .playlist_dialog import PlaylistDialog
from .quality_dialog import QualityDialog
from .settings import Settings
from .settings_page import SettingsPage
from .sign_in_dialog import SignInDialog
from .tray import TrayController, tray_wanted
from .model import COLUMNS, DownloadModel, StateFilterProxy, filter_of
from .quality_dialog import dialog_scale, font_scale
from .thumbnail import ThumbnailCache
from .widgets import (
    BrandMark, CountCards, EmptyState, QueueDelegate, RowHeightKeeper, action_icon,
    dialog_card, make_primary, make_quiet,
    enter_animation, open_finished, progress_ease, show_finished,
)

__all__ = ["MainWindow", "ProgressAnnouncer", "SHORTCUTS", "extract_urls"]

PAUSABLE = frozenset({"queued", "probing", "downloading", "merging", "converting"})
CANCELLABLE = frozenset(
    {"queued", "probing", "downloading", "merging", "converting", "paused"}
)
RETRYABLE = frozenset({"failed", "cancelled"})
# Failures that Settings > Accounts fixes (see engine/errors.py).
SIGN_IN_CODES = frozenset(
    {"sign_in_required", "login_required", "session_expired", "http_401"}
)
SECTIONS = ("Downloads", "History", "Settings")
ACTIVE = frozenset({"probing", "downloading", "merging", "converting"})

# (text shown in the F1 cheat sheet, what it does, the key sequences registered
# for it). The cheat sheet and the registered QShortcuts both come from this one
# table, so they cannot drift apart; an empty tuple means "not a QShortcut"
# (Enter in the link box is the line edit's own returnPressed).
SHORTCUTS = (
    ("Ctrl+L", "Go to the link box", ("Ctrl+L",)),
    ("Ctrl+V", "Paste and add links (when the list is focused)", ("Ctrl+V",)),
    ("Enter", "Add the link in the box (playlists ask which videos)", ()),
    ("Ctrl+Return", "Add the link in the box from anywhere in the window",
     ("Ctrl+Return", "Ctrl+Enter")),
    ("Ctrl+Shift+Return", "Choose the quality for the link in the box",
     ("Ctrl+Shift+Return", "Ctrl+Shift+Enter")),
    ("Space", "Pause or resume the selected download", ("Space",)),
    ("Ctrl+1 / Ctrl+2 / Ctrl+3", "Go to Downloads, History or Settings",
     ("Ctrl+1", "Ctrl+2", "Ctrl+3")),
    ("Ctrl+Q", "Quit", ("Ctrl+Q",)),
    ("F1", "Show this list", ("F1",)),
)
PROGRESS_STEPS = (25, 50, 75)
_TERMINAL = frozenset({"done", "failed", "skipped", "cancelled"})


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


_FOCUS_PRIMITIVES = frozenset({
    QStyle.PrimitiveElement.PE_PanelButtonCommand,
    QStyle.PrimitiveElement.PE_FrameLineEdit,
    QStyle.PrimitiveElement.PE_PanelLineEdit,
    QStyle.PrimitiveElement.PE_Frame,
})
_CHECK_PRIMITIVES = frozenset({
    QStyle.PrimitiveElement.PE_IndicatorCheckBox,
    QStyle.PrimitiveElement.PE_IndicatorRadioButton,
    QStyle.PrimitiveElement.PE_IndicatorItemViewItemCheck,
})


class AccessibleStyle(QProxyStyle):
    """Wraps the user's own Qt style and adds what some styles leave faint.

    It outlines check boxes and radio buttons, and draws a clear focus ring, in
    the palette's own text colour (so it follows qt6ct/Kvantum, dark or light,
    and has at least 3:1 contrast against the background). Nothing else changes.
    """

    def _outline(self, painter: Any, rect: Any, option: QStyleOption, width: float) -> None:
        group = (
            QPalette.ColorGroup.Normal
            if option.state & QStyle.StateFlag.State_Enabled
            else QPalette.ColorGroup.Disabled
        )
        painter.save()
        painter.setRenderHint(painter.RenderHint.Antialiasing, False)
        painter.setPen(QPen(option.palette.color(group, QPalette.ColorRole.WindowText), width))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        half = width / 2
        painter.drawRect(rect.adjusted(int(half), int(half), -int(half) - 1, -int(half) - 1))
        painter.restore()

    def drawPrimitive(self, element, option, painter, widget=None) -> None:  # noqa: N802
        super().drawPrimitive(element, option, painter, widget)
        if element in _CHECK_PRIMITIVES:
            self._outline(painter, option.rect, option, 1)
        elif element in _FOCUS_PRIMITIVES and option.state & QStyle.StateFlag.State_HasFocus:
            self._outline(painter, option.rect, option, 2)

    def drawControl(self, element, option, painter, widget=None) -> None:  # noqa: N802
        # The user's style may itself be a proxy (qt6ct), and nested proxies do
        # not see each other's primitives, so the controls are handled here too.
        super().drawControl(element, option, painter, widget)
        ce = QStyle.ControlElement
        focused = bool(option.state & QStyle.StateFlag.State_HasFocus)
        if element in (ce.CE_CheckBox, ce.CE_RadioButton):
            sub = (
                QStyle.SubElement.SE_CheckBoxIndicator
                if element == ce.CE_CheckBox
                else QStyle.SubElement.SE_RadioButtonIndicator
            )
            self._outline(painter, self.subElementRect(sub, option, widget), option, 1)
        elif element in (ce.CE_PushButton, ce.CE_ShapedFrame) and focused:
            self._outline(painter, option.rect, option, 2)

    def drawComplexControl(self, control, option, painter, widget=None) -> None:  # noqa: N802
        super().drawComplexControl(control, option, painter, widget)
        if (
            control in (QStyle.ComplexControl.CC_ComboBox, QStyle.ComplexControl.CC_ToolButton,
                        QStyle.ComplexControl.CC_SpinBox)
            and option.state & QStyle.StateFlag.State_HasFocus
        ):
            self._outline(painter, option.rect, option, 2)


def install_accessible_style() -> None:
    """Wrap the application's style once (safe to call again)."""
    app = QApplication.instance()
    if app is None or isinstance(app.style(), AccessibleStyle):
        return
    app.setStyle(AccessibleStyle(app.style().name()))


class ProgressAnnouncer:
    """Decides what a screen reader hears about download progress.

    Per item: one announcement at 25, 50 and 75 percent (a jump past several
    steps announces only the highest), then one for "finished" or "failed".
    Plain progress ticks never announce, so 100 ticks give at most 4 messages.
    """

    def __init__(self, say: Callable[[str], None]) -> None:
        self._say = say
        self._step: dict[int, int] = {}
        self._ended: set[int] = set()

    @staticmethod
    def _name(item: dict[str, Any]) -> str:
        return item.get("title") or item.get("url") or "Download"

    def feed(self, event: dict[str, Any]) -> None:
        item = event.get("item")
        if not isinstance(item, dict) or "id" not in item:
            return
        item_id, state = item["id"], item.get("state")
        if state not in _TERMINAL and item_id in self._ended:
            # Retried or resumed after finishing: announce afresh.
            self._ended.discard(item_id)
            self._step.pop(item_id, None)
        if state == "done" and item_id not in self._ended:
            self._ended.add(item_id)
            self._say(f"{self._name(item)} finished")
            return
        if state == "failed" and item_id not in self._ended:
            self._ended.add(item_id)
            error = item.get("error") or {}
            detail = f": {error['message']}" if error.get("message") else ""
            self._say(f"{self._name(item)} failed{detail}")
            return
        if state not in ("downloading", "merging", "converting"):
            return
        percent = (item.get("progress") or {}).get("percent")
        if percent is None:
            return
        reached = sum(1 for step in PROGRESS_STEPS if percent >= step)
        if reached > self._step.get(item_id, 0):
            self._step[item_id] = reached
            self._say(f"{self._name(item)}: {PROGRESS_STEPS[reached - 1]} percent")


def card_action_kinds(state: str | None) -> list[str]:
    """The card buttons that make sense in *state*, in display order.

    Same rules as the toolbar actions (``pause``/``resume``/``retry``/``cancel``/``open``),
    plus ``launch`` (open the finished file) next to ``open`` (show it in its folder).
    """
    kinds: list[str] = []
    if state in PAUSABLE:
        kinds.append("pause")
    if state == "paused":
        kinds.append("resume")
    if state in RETRYABLE:
        kinds.append("retry")
    if state in CANCELLABLE:
        kinds.append("cancel")
    if state == "done":
        kinds.extend(["launch", "open"])
    return kinds


class CardActions(QObject):
    """Action buttons on the hovered (else the selected) download row.

    ONE set of buttons lives on the table viewport and is moved to the right row;
    a click selects that row and triggers the window's own action, so the toolbar,
    the menu and the shortcuts stay the single source of behaviour. Buttons are in the
    Tab order right after the list and are named "<Action> <title>".

    Their look follows the row: small round icon buttons (pause, resume, cancel, retry
    of a cancelled item), the one inverted pill of a failed row ("Retry" or "Sign in"),
    and the "Open" and "Show in folder" links of a finished one.
    """

    KINDS = ("pause", "resume", "retry", "cancel", "launch", "open")
    ICON_KINDS = ("pause", "resume", "retry", "cancel")

    def __init__(self, window: MainWindow) -> None:
        super().__init__(window)
        self._w = window
        self._table = window.table
        self._hover_row = -1
        self._row = -1
        self._actions = {
            "pause": window.pause_action, "resume": window.resume_action,
            "retry": window.retry_action, "cancel": window.cancel_action,
            "launch": window.launch_action, "open": window.open_action,
        }
        self.buttons: dict[str, QToolButton] = {}
        viewport = self._table.viewport()
        for kind in self.KINDS:
            button = QToolButton(viewport)
            button.setObjectName("cardAction")
            button.setProperty("role", "icon")
            button.setAutoRaise(False)
            button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            button.setToolTip(self._actions[kind].text())
            button.setAccessibleDescription(self._actions[kind].toolTip())
            button.clicked.connect(lambda _=False, k=kind: self.activate(k))
            button.hide()
            self.buttons[kind] = button
        viewport.setMouseTracking(True)
        viewport.installEventFilter(self)
        model = self._table.model()
        for signal in (model.rowsInserted, model.rowsRemoved, model.modelReset,
                       model.dataChanged, model.layoutChanged):
            signal.connect(self.refresh)
        self._table.selectionModel().selectionChanged.connect(self.refresh)
        self._table.verticalScrollBar().valueChanged.connect(self.refresh)

    # -- what is shown ---------------------------------------------------
    def card_row(self) -> int:
        """Row that currently carries the buttons (-1 for none)."""
        return self._row

    def visible_kinds(self) -> list[str]:
        return [k for k in self.KINDS if not self.buttons[k].isHidden()]

    def _target_row(self) -> int:
        if any(b.hasFocus() for b in self.buttons.values()):
            return self._row  # keyboard use: stay on the row being operated
        if self._hover_row >= 0:
            return self._hover_row
        rows = self._table.selectionModel().selectedRows()
        return rows[0].row() if rows else -1

    def _style(self, button: QToolButton, role: str) -> None:
        if button.property("role") != role:
            button.setProperty("role", role)
            button.style().unpolish(button)
            button.style().polish(button)

    def refresh(self, *_: object) -> None:
        had_focus = next((k for k, b in self.buttons.items() if b.hasFocus()), None)
        row = self._target_row()
        proxy = self._w.proxy
        snap = proxy.snapshot_at(row) if row >= 0 else None
        delegate = self._w.delegate
        rect = self._table.visualRect(proxy.index(row, 0)) if snap else None
        if snap is None or rect is None or not rect.isValid() or not self._table.viewport().rect().intersects(rect):
            self._row = -1
            for b in self.buttons.values():
                b.hide()
            delegate.actions_row_id, delegate.actions_width = None, 0.0
            self._table.viewport().update()
            self._restore_focus(had_focus)
            return
        self._row = row
        kinds = card_action_kinds(snap["state"])
        title = DownloadModel.title_of(snap)
        font = self._table.font()
        m = delegate.metrics(font)
        u = m["u"]
        side = int(round(28 * u))
        spacing = int(round(4 * u))
        icons = [k for k in kinds if k in self.ICON_KINDS and snap["state"] != "failed"]
        total = len(icons) * side + max(len(icons) - 1, 0) * spacing
        geo = delegate.geometry(rect, snap, font, actions_width=float(total))
        pill_text = delegate.pill_text(snap)
        x = int(round(geo.actions_right)) - total
        for kind in self.KINDS:
            button = self.buttons[kind]
            if kind not in kinds:
                button.hide()
                continue
            action = self._actions[kind]
            label = action.text()
            description = action.toolTip()
            if kind == "retry" and pill_text:  # a failed row: the one inverted pill
                signing_in = pill_text == "Sign in"
                label = pill_text
                if signing_in:
                    description = "Pick the browser you are signed in to, then retry"
                self._style(button, "pill")
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
                button.setText(pill_text)
                button.setIcon(QIcon())
                pill = geo.pill
                button.setFixedSize(int(round(pill.width())), int(round(pill.height())))
                button.setStyleSheet(f"QToolButton {{ border-radius: {int(pill.height() // 2)}px; }}")
                button.move(int(round(pill.left())), int(round(pill.top())))
            elif kind in ("launch", "open"):
                link = geo.link_open if kind == "launch" else geo.link_folder
                self._style(button, "link")
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
                button.setText("Open" if kind == "launch" else "Show in folder")
                button.setIcon(QIcon())
                button.setFixedSize(int(round(link.width())), int(round(link.height())))
                button.move(int(round(link.left())), int(round(link.top())))
            else:
                self._style(button, "icon")
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                button.setText("")
                button.setStyleSheet("")
                button.setFixedSize(side, side)
                button.setIconSize(QSize(int(side * 0.6), int(side * 0.6)))
                button.setIcon(action.icon())
                button.move(x, int(round(geo.centre_y - side / 2)))
                x += side + spacing
            button.setToolTip(f"{label}: {title}")
            button.setAccessibleDescription(description)
            button.setAccessibleName(f"{label} {title}")
            button.show()
            button.raise_()
        delegate.actions_row_id, delegate.actions_width = snap["id"], float(total)
        self._table.viewport().update()
        self._restore_focus(had_focus)

    def _restore_focus(self, kind: str | None) -> None:
        """A focused button that vanished (Pause -> Resume) hands focus to a sibling."""
        if kind is None or self.buttons[kind].isVisible() or any(
                b.hasFocus() for b in self.buttons.values()):
            return
        shown = [b for b in self.buttons.values() if not b.isHidden()]
        (shown[0] if shown else self._table).setFocus(Qt.FocusReason.OtherFocusReason)

    def refresh_icons(self) -> None:
        self.refresh()

    # -- doing -----------------------------------------------------------
    def activate(self, kind: str) -> None:
        """Select the row the buttons are on, then run the window's own action."""
        if self._row < 0:
            return
        if [r.row() for r in self._table.selectionModel().selectedRows()] != [self._row]:
            self._table.selectRow(self._row)
        if kind == "retry" and self.buttons["retry"].property("role") == "pill" \
                and self.buttons["retry"].text() == "Sign in":
            self._w.open_sign_in_dialog()
            return
        self._actions[kind].trigger()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        kind = event.type()
        if kind == QEvent.Type.MouseMove:
            index = self._table.indexAt(event.position().toPoint())
            row = index.row() if index.isValid() else -1
            if row != self._hover_row:
                self._hover_row = row
                self.refresh()
        elif kind in (QEvent.Type.Leave, QEvent.Type.Hide):
            if self._hover_row != -1:
                self._hover_row = -1
                self.refresh()
        elif kind == QEvent.Type.Resize:
            QTimer.singleShot(0, self.refresh)
        return False


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
        tray_factory: Callable[[MainWindow], TrayController | None] | None = None,
        detect_fn: Callable[[], list[str]] | None = None,
    ) -> None:
        """``tray_factory(window)`` builds the tray controller (or returns ``None``).

        Left out, the real tray is built on a desktop session that has one, and
        never under the offscreen/minimal Qt platforms. Tests inject a factory
        that uses a fake icon.
        """
        super().__init__(parent)
        install_accessible_style()
        self.queue = queue
        self._quitting = False
        self._pending_playlists: list[str] = []
        self._draining_playlists = False
        self.tray: TrayController | None = None
        self._probe_fn = probe_fn or self._default_probe
        self._thumbnail_fetcher = thumbnail_fetcher
        self.settings = settings or Settings()
        self._settings_path = settings_path
        self._version_fn = version_fn
        self._detect_fn = detect_fn
        self.sign_in_dialog: SignInDialog | None = None
        self.setWindowTitle("Elisium")
        self.resize(900, 520)

        self.bridge = bridge or QueueBridge(queue, self)
        self.model = DownloadModel(self)
        self.bridge.event.connect(self._on_event)
        self.model.load(queue.items())

        self._build_ui()
        self._build_actions()
        self._build_shortcuts()
        self._wire_tab_order()
        self._fit_to_font()
        self.announcements: list[str] = []
        self.announcer = ProgressAnnouncer(self._announce)
        if tray_factory is not None:
            self.tray = tray_factory(self)
        elif tray_wanted():
            self.tray = TrayController(self)
        self._refresh_ui()

    # -- construction ----------------------------------------------------
    def _build_ui(self) -> None:
        # Top bar: the mark, the section links, then the link field and the Download pill.
        self.url_edit = QLineEdit()
        self.url_edit.setObjectName("linkField")
        self.url_edit.setPlaceholderText("Paste a link from YouTube, Instagram, TikTok…")
        self.url_edit.setClearButtonEnabled(True)
        self.url_edit.setAccessibleName("Video link")
        self.url_edit.setAccessibleDescription(
            "Type or paste one or more video links, then press Enter to add them."
        )
        self.paste_button = QPushButton("Paste")
        self.paste_button.setProperty("quiet", True)
        self.paste_button.setAccessibleName("Paste")
        self.paste_button.setAccessibleDescription(
            "Add the links from the clipboard to the download list."
        )
        self.add_button = QPushButton("Download")
        self.add_button.setObjectName("downloadButton")
        self.add_button.setProperty("primary", True)
        self.add_button.setAccessibleName("Download")
        self.add_button.setAccessibleDescription(
            "Add the link in the box to the download list."
        )
        self.options_button = QPushButton("Options...")
        self.options_button.setProperty("quiet", True)
        self.options_button.setAccessibleName("Options")
        self.options_button.setAccessibleDescription(
            "Check the link and choose the quality before adding it."
        )

        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setFlow(QListWidget.Flow.LeftToRight)
        self.nav.setWrapping(False)
        self.nav.setFrameShape(QFrame.Shape.NoFrame)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav.setAccessibleName("Sections")
        self.nav.setAccessibleDescription(
            "Switch between Downloads, History and Settings with the left and right arrow keys."
        )
        for name in SECTIONS:
            self.nav.addItem(name)
        self.nav.setCurrentRow(0)
        self.nav.currentRowChanged.connect(self.show_section)

        self.brand = BrandMark()
        self.top_bar = QWidget(self)
        self.top_bar.setObjectName("topBar")
        bar = QHBoxLayout(self.top_bar)
        bar.setContentsMargins(int(theme.SPACE["gutter"]), 0, int(theme.SPACE["gutter"]), 0)
        bar.setSpacing(int(theme.SPACE["gap"]))
        bar.addWidget(self.brand)
        bar.addSpacing(14)
        bar.addWidget(self.nav)
        bar.addStretch(1)
        self.url_edit.setMinimumWidth(160)
        self.url_edit.setMaximumWidth(380)
        bar.addWidget(self.url_edit, 100)
        bar.addWidget(self.paste_button)
        bar.addWidget(self.add_button)
        bar.addWidget(self.options_button)
        self.bar_rule = QFrame(self)
        self.bar_rule.setObjectName("barRule")
        self.bar_rule.setFixedHeight(1)
        self.bar_rule.setAccessibleName("")
        self.bar_rule.hide()  # appears only once the list scrolls

        # Downloads page: count cards (filters), the rows, then the quiet action toolbar.
        downloads_page = QWidget(self)
        layout = QVBoxLayout(downloads_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(int(theme.SPACE["gap"]))
        self.cards = CountCards()
        layout.addWidget(self.cards)

        self.proxy = StateFilterProxy(self.model, self)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setAccessibleName("Downloads")
        self.table.setAccessibleDescription(
            "List of downloads with status, progress, speed, time left and size."
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setObjectName("cards")
        self.table.setFrameShape(QFrame.Shape.NoFrame)
        # Rows: one delegate paints the whole row into column 0; the other
        # columns stay in the model (accessible text, tests) but are hidden.
        self.delegate = QueueDelegate(self.table)
        self.delegate.sign_in_codes = SIGN_IN_CODES
        self.thumbnails = ThumbnailCache(self._thumbnail_fetcher, self)
        self.thumbnails.ready.connect(self._repaint_rows)
        self.delegate.thumbnails = self.thumbnails
        self.table.setItemDelegateForColumn(0, self.delegate)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        for column in range(1, len(COLUMNS)):
            self.table.setColumnHidden(column, True)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setShowGrid(False)
        # Tab must leave the table, not walk its cells.
        self.table.setTabKeyNavigation(False)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.row_heights = RowHeightKeeper(self.table, self.delegate)
        self.empty_state = EmptyState(self.table.viewport())
        layout.addWidget(self.table, 1)
        self._downloads_layout = layout
        self.cards.filterChanged.connect(self._on_filter)
        self.table.verticalScrollBar().valueChanged.connect(self._on_scrolled)

        self.history_page = HistoryPage(self.queue, self.bridge)
        self.settings_page = SettingsPage(
            self.settings, self.queue, self._settings_path, self._version_fn,
            detect_fn=self._detect_fn,
        )
        self.settings_page.settingsChanged.connect(self._on_settings_changed)
        self.stack = QStackedWidget()
        for page in (downloads_page, self.history_page, self.settings_page):
            self.stack.addWidget(page)

        central = QWidget(self)
        frame = QVBoxLayout(central)
        frame.setContentsMargins(0, 0, 0, 0)
        frame.setSpacing(0)
        frame.addWidget(self.top_bar)
        frame.addWidget(self.bar_rule)
        outer = QHBoxLayout()
        outer.setContentsMargins(int(theme.SPACE["gutter"]), int(theme.SPACE["gap"]),
                                 int(theme.SPACE["gutter"]), int(theme.SPACE["gap"]))
        outer.addWidget(self.stack, 1)
        frame.addLayout(outer, 1)
        self.setCentralWidget(central)

        self.summary_label = QLabel()
        self.summary_label.setAccessibleName("Download summary")
        self.sign_in_button = QPushButton("Sign in...")
        self.sign_in_button.setFlat(True)
        self.sign_in_button.setAccessibleName("Sign in")
        self.sign_in_button.setAccessibleDescription(
            "Some downloads need a sign-in. Opens a window to choose your browser and retry."
        )
        self.sign_in_button.setToolTip("Some downloads need a sign-in")
        self.sign_in_button.clicked.connect(self.open_sign_in_dialog)
        self.sign_in_button.hide()
        self.statusBar().addPermanentWidget(self.sign_in_button)
        self.statusBar().addPermanentWidget(self.summary_label)
        # One zero-height live label: screen readers are told about progress
        # here, at coarse steps only (see ProgressAnnouncer).
        self.live_label = QLabel()
        self.live_label.setAccessibleName("Progress announcements")
        self.live_label.setFixedHeight(0)
        self.statusBar().addWidget(self.live_label)
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
        self, text: str, _icon_name: str, _fallback: QStyle.StandardPixmap, description: str, slot: Any
    ) -> QAction:
        action = QAction(text, self)
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
        self.launch_action = self._make_action(
            "Open", "document-open", sp.SP_FileIcon,
            "Open the finished file", self.launch_selected,
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
        self._downloads_layout.addWidget(self.toolbar)
        self.card_actions = CardActions(self)
        self._apply_icons()
        theme.notifier().changed.connect(self._on_theme_changed)
        # One shared animation drives every new row's enter (fade + 6 px rise) and one
        # eases the bars; neither loops, and both are off with reduced motion.
        self.model.rowsInserted.connect(self._on_rows_inserted)
        enter_animation().valueChanged.connect(self._on_enter_tick)
        progress_ease().valueChanged.connect(self._on_enter_tick)

    def _on_enter_tick(self, *_: object) -> None:
        self.table.viewport().update()

    def _repaint_rows(self) -> None:
        self.table.viewport().update()

    def _on_filter(self, key: str) -> None:
        """A count card was chosen: show only those downloads."""
        self.proxy.set_filter(key)
        self.card_actions.refresh()
        self._update_summary()
        self._update_actions()

    def _on_scrolled(self, value: int) -> None:
        """The 1 px rule under the top bar shows only once the list has scrolled."""
        self.bar_rule.setVisible(value > 0 and self.stack.currentIndex() == 0)

    def _on_rows_inserted(self, _parent: Any, first: int, last: int) -> None:
        for row in range(first, last + 1):
            item_id = self.model.item_id_at(row)
            if item_id is not None:
                enter_animation().add(item_id)

    def _apply_icons(self) -> None:
        for action, kind in (
            (self.pause_action, "pause"), (self.resume_action, "play"),
            (self.retry_action, "retry"), (self.cancel_action, "cancel"),
            (self.open_action, "folder"),
        ):
            action.setIcon(action_icon(kind))
        if hasattr(self, "card_actions"):
            self.card_actions.refresh_icons()

    def _on_theme_changed(self) -> None:
        self._apply_icons()
        self.table.viewport().update()
        self.history_page.table.viewport().update()

    def _build_shortcuts(self) -> None:
        def shortcut(keys: str, slot: Any, widget: QWidget, context: Qt.ShortcutContext) -> QShortcut:
            sc = QShortcut(QKeySequence(keys), widget)
            sc.setContext(context)
            sc.activated.connect(slot)
            return sc

        window = Qt.ShortcutContext.WindowShortcut
        own = Qt.ShortcutContext.WidgetShortcut
        # key sequence -> (slot, widget, context); the keys themselves are listed
        # (once) in SHORTCUTS, which also feeds the F1 cheat sheet.
        handlers: dict[str, tuple[Any, QWidget, Qt.ShortcutContext]] = {
            "Ctrl+L": (self.focus_url_bar, self, window),
            "Ctrl+V": (self.paste_from_clipboard, self.table, own),
            "Ctrl+Return": (self._add_from_box, self, window),
            "Ctrl+Enter": (self._add_from_box, self, window),
            "Ctrl+Shift+Return": (self.open_options, self, window),
            "Ctrl+Shift+Enter": (self.open_options, self, window),
            "Space": (self.toggle_pause_resume, self.table, own),
            "Ctrl+Q": (self.quit_app, self, window),
            "F1": (self.show_shortcuts, self, window),
        }
        for n in (1, 2, 3):
            handlers[f"Ctrl+{n}"] = (lambda n=n: self.show_section(n - 1), self, window)
        built = {
            keys: shortcut(keys, *handlers[keys])
            for _text, _meaning, sequences in SHORTCUTS
            for keys in sequences
        }
        self._section_shortcuts = [built[f"Ctrl+{n}"] for n in (1, 2, 3)]
        self._add_shortcuts = [
            built[k] for k in ("Ctrl+Return", "Ctrl+Enter", "Ctrl+Shift+Return", "Ctrl+Shift+Enter")
        ]
        self._shortcuts = [built[k] for k in ("Ctrl+V", "Space", "Ctrl+L", "Ctrl+Q", "F1")]

    def _wire_tab_order(self) -> None:
        widgets: list[QWidget] = [
            self.nav, self.url_edit, self.paste_button, self.add_button, self.options_button,
            *self.cards.cards.values(), self.table,
        ]
        widgets.extend(self.card_actions.buttons[k] for k in CardActions.KINDS)
        for action in (
            self.pause_action, self.resume_action, self.retry_action,
            self.cancel_action, self.open_action,
        ):
            widgets.append(self.toolbar.widgetForAction(action))
        for first, second in zip(widgets, widgets[1:]):
            QWidget.setTabOrder(first, second)

    # -- text size -------------------------------------------------------
    def _fit_to_font(self) -> None:
        """Size the top bar, the section links and the rows from the text size (so 200% fits)."""
        fm = QFontMetrics(self.font())
        self.row_heights.update()
        self.table.setMinimumWidth(fm.horizontalAdvance("M") * 24 + self.table.frameWidth() * 2)
        bar_h = max(int(theme.SIZE["topBar"]), fm.height() + 20, self.nav.minimumSizeHint().height())
        self.top_bar.setFixedHeight(bar_h)
        link_font = QFont(self.font())
        link_font.setWeight(QFont.Weight.DemiBold)
        lfm = QFontMetrics(link_font)
        width = 0
        for row in range(self.nav.count()):
            item = self.nav.item(row)
            w = lfm.horizontalAdvance(item.text()) + 28
            item.setSizeHint(QSize(w, bar_h))
            width += w
        self.nav.setFixedSize(width + 8, bar_h)

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if hasattr(self, "table") and event.type() in (
            QEvent.Type.FontChange,
            QEvent.Type.ApplicationFontChange,
        ):
            self._fit_to_font()

    # -- sections --------------------------------------------------------
    def show_section(self, index: int) -> None:
        """Show page *index* (0 Downloads, 1 History, 2 Settings)."""
        if not 0 <= index < self.stack.count():
            return
        self.stack.setCurrentIndex(index)
        if self.nav.currentRow() != index:
            self.nav.setCurrentRow(index)
        self.toolbar.setVisible(index == 0)
        self.bar_rule.setVisible(index == 0 and self.table.verticalScrollBar().value() > 0)
        if index == 1:
            self.history_page.refresh()

    def _on_settings_changed(self, settings: Settings) -> None:
        previous = self.settings
        self.settings = settings
        app = QApplication.instance()
        if settings.appearance != previous.appearance and app is not None:
            theme.apply(app, settings.appearance)
        theme.set_reduce_motion(settings.reduce_motion)

    def open_accounts(self) -> None:
        """Show Settings > Accounts, where a sign-in failure tells the user to go."""
        self.show_section(2)
        self.settings_page.show_accounts()

    def open_sign_in_dialog(self) -> SignInDialog:
        """Open the small modal sign-in dialog (only from a user action)."""
        dialog = SignInDialog(
            self._detect_fn, self,
            detected=self.settings_page.detected_browsers or None,
        )
        dialog.browserChosen.connect(self.settings_page.use_browser)
        dialog.retryRequested.connect(self.retry_sign_in_failures)
        dialog.settingsRequested.connect(self.open_accounts)
        dialog.finished.connect(lambda _r: setattr(self, "sign_in_dialog", None))
        self.sign_in_dialog = dialog
        dialog.open()
        return dialog

    def retry_sign_in_failures(self) -> int:
        """Retry every failed item whose error needs a sign-in (existing retry path)."""
        count = 0
        for snap in self.queue.items():
            error = snap.get("error") or {}
            if snap["state"] == "failed" and error.get("code") in SIGN_IN_CODES:
                if self.queue.retry(snap["id"]):
                    count += 1
        if count:
            self.statusBar().showMessage(
                f"Retrying {count} download{'s' if count != 1 else ''}", 8000
            )
        return count

    def _update_sign_in_hint(self) -> None:
        needs = False
        for row in range(self.model.rowCount()):
            snap = self.model.snapshot_at(row)
            if (
                snap is not None and snap["state"] == "failed"
                and (snap.get("error") or {}).get("code") in SIGN_IN_CODES
            ):
                needs = True
                break
        self.sign_in_button.setVisible(needs)

    # -- model feed ------------------------------------------------------
    def _on_event(self, event: dict[str, Any]) -> None:
        self.model.handle_event(event)
        self._refresh_ui()
        self.announcer.feed(event)
        if self.tray is not None:
            self.tray.on_event(event)
        item = event.get("item")
        if isinstance(item, dict) and item.get("state") == "failed":
            error = item.get("error") or {}
            if error.get("code") in SIGN_IN_CODES:
                # The error's suggested action: Settings > Accounts.
                self.statusBar().showMessage(
                    f"{error.get('message', 'Sign-in needed.')} "
                    f"{error.get('fix', 'Settings > Accounts')}",
                    12000,
                )
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
        self._update_sign_in_hint()
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
        card_counts = {"all": self.model.rowCount()}
        for row in range(self.model.rowCount()):
            key = filter_of(self.model.snapshot_at(row)["state"])
            if key:
                card_counts[key] = card_counts.get(key, 0) + 1
        self.cards.set_counts(card_counts)
        self.empty_state.setVisible(self.proxy.rowCount() == 0)
        self.empty_state.text = (
            "Paste a link from YouTube, Instagram, TikTok…" if self.model.rowCount() == 0
            else f"No {self.cards.cards[self.proxy.filter_key].label.lower()} downloads right now"
        )
        self.empty_state.setAccessibleDescription(self.empty_state.text)
        self.empty_state.update()
        if self.tray is not None:
            self.tray.update_tooltip(self.summary_label.text())

    def _announce(self, text: str) -> None:
        """Tell assistive technology *text* (polite, never interrupts speech)."""
        self.announcements.append(text)
        del self.announcements[:-50]
        self.live_label.setText(text)
        self.live_label.setAccessibleDescription(text)
        event = QAccessibleAnnouncementEvent(self.live_label, text)
        event.setPoliteness(QAccessible.AnnouncementPoliteness.Polite)
        QAccessible.updateAccessibility(event)

    # -- selection -------------------------------------------------------
    def selected_snapshot(self) -> dict[str, Any] | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        return self.proxy.snapshot_at(rows[0].row())

    def _update_actions(self) -> None:
        snap = self.selected_snapshot()
        state = snap["state"] if snap else None
        self.pause_action.setEnabled(state in PAUSABLE)
        self.resume_action.setEnabled(state == "paused")
        self.retry_action.setEnabled(state in RETRYABLE)
        self.cancel_action.setEnabled(state in CANCELLABLE)
        self.open_action.setEnabled(state == "done")
        self.launch_action.setEnabled(state == "done")
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
        return self.queue.probe(url)

    def _queue_links(
        self, urls: list[str], ignored: int
    ) -> tuple[int, int, int, list[str]]:
        """Queue the plain links; return (added, known, ignored, playlist links).

        Playlist and channel links are never queued here; the caller decides
        when to open the picker for them.
        """
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
        return added, known, ignored, playlists

    def _report_added(self, added: int, known: int, ignored: int, playlists: list[str]) -> None:
        if playlists and not (added or known or ignored):
            self.statusBar().showMessage("Checking the playlist...", 5000)
            return
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
            message = ", ".join(parts) if added else "No links added, " + ", ".join(parts)
        self.statusBar().showMessage(message, 8000)

    def add_text(self, text: str) -> None:
        """Add every link in *text* and report what happened in the status bar.

        Plain links are queued at once with the default preset. A link that
        looks like a playlist or channel is probed and the playlist picker
        opens instead, so an unknown number of videos is never queued blindly.
        """
        urls, ignored = extract_urls(text)
        added, known, ignored, playlists = self._queue_links(urls, ignored)
        self._report_added(added, known, ignored, playlists)
        for url in playlists:
            self._open_playlist(url)

    def receive_links(self, urls: list[str]) -> dict[str, int]:
        """Links handed over by another process (``elisium add``, ``elisium://``).

        Always the default preset. Playlist links open the picker (after the
        reply has gone out) instead of being queued. Never raises or focuses
        the window; the user is told by the status bar and a notification.
        """
        added, known, ignored, playlists = self._queue_links(list(urls), 0)
        self._report_added(added, known, ignored, playlists)
        if added and self.tray is not None:
            self.tray.notify_added(added)
        if playlists:
            self._pending_playlists.extend(playlists)
            QTimer.singleShot(0, self._drain_playlists)
        result = {"added": added, "known": known, "ignored": ignored}
        if playlists:
            result["playlists"] = len(playlists)
        return result

    def _drain_playlists(self) -> None:
        """Open the playlist pickers one after another (a picker is modal)."""
        if self._draining_playlists:
            return
        self._draining_playlists = True
        try:
            while self._pending_playlists:
                self._open_playlist(self._pending_playlists.pop(0))
        finally:
            self._draining_playlists = False

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

    def pause_all(self) -> None:
        for snap in self.queue.items():
            if snap["state"] in PAUSABLE:
                self.queue.pause(snap["id"])

    def resume_all(self) -> None:
        for snap in self.queue.items():
            if snap["state"] == "paused":
                self.queue.resume(snap["id"])

    def open_folder(self) -> None:
        """"Show in folder": select the finished file (the first one of a post) in the file manager."""
        snap = self.selected_snapshot()
        if snap is None or snap["state"] != "done":
            return
        show_finished(snap.get("file_path"), self.queue.output_dir)

    def launch_selected(self) -> None:
        """"Open": the file with the desktop's default app; a multi-file post opens its folder."""
        snap = self.selected_snapshot()
        if snap is None or snap["state"] != "done":
            return
        total = (snap.get("progress") or {}).get("files_total")
        open_finished(snap.get("file_path"), total, self.queue.output_dir)

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
        error = (self.selected_snapshot() or {}).get("error") or {}
        if error.get("code") in SIGN_IN_CODES:
            sign_in = menu.addAction("Sign in...")
            sign_in.setToolTip("Pick the browser you are signed in to, then retry")
            sign_in.setStatusTip("Pick the browser you are signed in to, then retry")
            sign_in.triggered.connect(self.open_sign_in_dialog)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def build_shortcuts_dialog(self) -> QDialog:
        dialog = QDialog(self)
        dialog.setWindowTitle("Keyboard shortcuts")
        dialog.setAccessibleName("Keyboard shortcuts")
        layout = dialog_card(dialog)
        layout.setSpacing(8)
        dialog.setMinimumWidth(round(480 * dialog_scale(dialog)))
        for keys, meaning, _sequences in SHORTCUTS:
            label = QLabel(f"<b>{keys}</b>  {meaning}")
            label.setWordWrap(True)
            layout.addWidget(label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        make_primary(buttons.button(QDialogButtonBox.StandardButton.Close))
        layout.addWidget(buttons)
        dialog.adjustSize()  # honours wrapped labels' height-for-width
        # Pin each wrapped label to the height its text needs at the final width, so a
        # later re-layout (different font engine, text size change) cannot clip a line.
        margins = layout.contentsMargins()
        width = dialog.width() - margins.left() - margins.right()
        for label in dialog.findChildren(QLabel):
            label.setMinimumHeight(label.heightForWidth(width))
        dialog.adjustSize()
        return dialog

    def show_shortcuts(self) -> None:
        self._run_dialog(self.build_shortcuts_dialog())

    # -- closing ---------------------------------------------------------
    def _confirm_close(self) -> str:
        """Ask what to do about running downloads: 'pause', 'keep' or 'cancel'."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.NoIcon)
        box.setWindowTitle("Downloads are running")
        box.setText("Downloads are running. Pause them and quit?")
        pause = box.addButton("Pause and quit", QMessageBox.ButtonRole.AcceptRole)
        keep = box.addButton("Keep downloading", QMessageBox.ButtonRole.RejectRole)
        cancel = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        make_primary(keep)  # the safe choice is the inverted pill (it is also the default)
        make_quiet(pause)
        make_quiet(cancel)
        box.setDefaultButton(keep)
        box.setEscapeButton(cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked is pause:
            return "pause"
        if clicked is keep:
            return "keep"
        return "cancel"

    def quit_app(self) -> None:
        """Really quit (tray menu, Ctrl+Q): never just hide to the tray."""
        self._quitting = True
        try:
            self.close()
        finally:
            self._quitting = False

    def _hides_to_tray(self) -> bool:
        return (
            not self._quitting
            and self.tray is not None
            and self.settings.close_to_tray
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._hides_to_tray():
            # Keep running: downloads carry on while the window is hidden.
            event.ignore()
            self.hide()
            self.tray.announce_hidden()
            return
        active = self.queue.active_ids()
        if active:
            choice = self._confirm_close()
            if choice != "pause":
                event.ignore()
                return
            for item_id in active:
                self.queue.pause(item_id)
        self.bridge.close()
        event.accept()
        if self.tray is not None:
            self.tray.shutdown()
