from __future__ import annotations

import logging
import threading
from urllib.parse import urlsplit

from PySide6.QtCore import QObject, QThread, Signal, Slot, Qt
from PySide6.QtGui import QCloseEvent, QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.browser.browser_manager import BrowserManager
from app.browser.login_manager import LoginManager
from app.core.cleanup_manager import CleanupManager
from app.core.exceptions import EdgeUnavailable, LoginExpired, RiskControlDetected, UnsupportedPageState
from app.core.state import CleanupState, STATE_TEXT
from app.storage.database import Database
from app.ui.dialogs import ConfirmDeleteDialog, PreviewDialog
from app.ui.styles import APP_STYLESHEET
from app.utils.paths import AppPaths
from app.xhs.deleter import CommentDeleter
from app.xhs.scanner import HistoryScanner


class BrowserWorker(QObject):
    state_changed = Signal(str, str)
    counts_changed = Signal(dict)
    login_changed = Signal(bool)
    scan_finished = Signal(bool, int)
    error = Signal(str)
    finished = Signal()

    def __init__(self, paths: AppPaths, database: Database, logger: logging.Logger):
        super().__init__()
        self.paths = paths
        self.database = database
        self.logger = logger
        self.browser: BrowserManager | None = None
        self.cleanup: CleanupManager | None = None
        self._pause_requested = threading.Event()

    def request_pause(self) -> None:
        self._pause_requested.set()
        if self.cleanup:
            self.cleanup.pause()

    @Slot()
    def open_xhs(self) -> None:
        self.logger.info("action=open_xhs result=started")
        try:
            page = self._browser().open_xhs()
            logged_in = LoginManager(page).is_logged_in()
            self.login_changed.emit(logged_in)
            state = CleanupState.IDLE if logged_in else CleanupState.LOGIN_REQUIRED
            self.state_changed.emit(state.value, STATE_TEXT[state])
            self.logger.info("action=open_xhs result=success logged_in=%s", logged_in)
        except EdgeUnavailable as exc:
            self.error.emit(str(exc))
        except Exception:
            self.logger.exception("action=open_xhs result=failed")
            self.error.emit("小红书页面加载失败，请稍后重试。")

    @Slot()
    def check_login(self) -> None:
        self.logger.info("action=check_login result=started")
        try:
            page = self._browser().start()
            logged_in = LoginManager(page).is_logged_in()
            self.login_changed.emit(logged_in)
            state = CleanupState.IDLE if logged_in else CleanupState.LOGIN_REQUIRED
            message = "登录状态正常，可以开始扫描" if logged_in else STATE_TEXT[state]
            self.state_changed.emit(state.value, message)
            self.logger.info(
                "action=check_login result=success logged_in=%s host=%s",
                logged_in, self._page_host(page),
            )
        except EdgeUnavailable as exc:
            self.logger.exception("action=check_login result=edge_unavailable")
            self.error.emit(str(exc))
        except Exception as exc:
            self.logger.exception(
                "action=check_login result=failed error=%s", type(exc).__name__
            )
            self.state_changed.emit(CleanupState.ERROR.value, "检查登录状态失败，请重新打开小红书后再试")
            self.error.emit("检查登录状态失败。程序没有继续操作，请重新打开小红书后再试。")

    @Slot()
    def scan(self) -> None:
        self._pause_requested.clear()
        try:
            page = self._browser().start()
            login = LoginManager(page)
            if not login.is_logged_in():
                raise LoginExpired("请先在打开的 Edge 中完成登录")
            user_id = login.current_user_id()
            if not user_id:
                raise UnsupportedPageState("无法可靠识别当前登录账号，请打开个人主页后重试")
            self.database.set_state("current_user_id", user_id)
            self.state_changed.emit(CleanupState.SCANNING.value, STATE_TEXT[CleanupState.SCANNING])
            scanner = HistoryScanner(
                page, self.database, user_id,
                on_discovered=lambda _n: self.counts_changed.emit(self.database.counts()),
                should_pause=self._pause_requested.is_set,
            )
            _new_count, complete = scanner.scan_my_comment_history()
            total = self.database.counts()["discovered"]
            self.counts_changed.emit(self.database.counts())
            self.scan_finished.emit(complete, total)
            state = CleanupState.PAUSED if self._pause_requested.is_set() else CleanupState.READY
            message = "扫描已暂停" if self._pause_requested.is_set() else "扫描完成，可以查看结果"
            self.state_changed.emit(state.value, message)
        except LoginExpired as exc:
            self.state_changed.emit(CleanupState.LOGIN_REQUIRED.value, str(exc))
            self.login_changed.emit(False)
        except RiskControlDetected as exc:
            self.state_changed.emit(CleanupState.BLOCKED.value, str(exc))
        except UnsupportedPageState as exc:
            self._screenshot("scan_unsupported")
            self.state_changed.emit(CleanupState.PAUSED.value, str(exc))
        except Exception:
            self._screenshot("scan_failed")
            self.logger.exception("action=scan result=failed")
            self.state_changed.emit(CleanupState.ERROR.value, "扫描失败，任务已停止")

    @Slot()
    def delete_all(self) -> None:
        self._pause_requested.clear()
        try:
            page = self._browser().start()
            login = LoginManager(page)
            if not login.is_logged_in():
                raise LoginExpired("登录状态已失效，请重新登录小红书。")
            current_user_id = login.current_user_id()
            saved_user_id = self.database.get_state("current_user_id")
            if not current_user_id or current_user_id != saved_user_id:
                raise UnsupportedPageState("当前账号与扫描账号不一致，已停止删除")
            self.cleanup = CleanupManager(
                self.database, CommentDeleter(page, current_user_id), self.logger,
                on_state=lambda state, text: self.state_changed.emit(state.value, text),
                on_progress=self.counts_changed.emit,
                wait_ms=page.wait_for_timeout,
                screenshot=self._screenshot,
            )
            self.cleanup.run()
        except LoginExpired as exc:
            self.state_changed.emit(CleanupState.LOGIN_REQUIRED.value, str(exc))
        except UnsupportedPageState as exc:
            self.state_changed.emit(CleanupState.PAUSED.value, str(exc))
        except EdgeUnavailable as exc:
            self.error.emit(str(exc))
        except Exception as exc:
            self._screenshot("delete_unexpected")
            self.logger.exception(
                "action=delete_all result=failed error=%s", type(exc).__name__
            )
            self.state_changed.emit(CleanupState.ERROR.value, "清理任务发生异常，已安全停止")
            self.error.emit("清理任务发生异常，程序已安全停止。详细信息已写入日志。")
        finally:
            self.cleanup = None

    @Slot()
    def shutdown(self) -> None:
        try:
            if self.browser:
                self.browser.close()
        except Exception:
            self.logger.exception("action=shutdown result=failed")
        finally:
            self.finished.emit()

    def _browser(self) -> BrowserManager:
        if self.browser is None:
            self.browser = BrowserManager(self.paths.profile, self.logger)
        return self.browser

    def _screenshot(self, label: str) -> None:
        if self.browser:
            self.browser.screenshot(self.paths.screenshots, label)

    @staticmethod
    def _page_host(page) -> str:
        try:
            return urlsplit(page.url).hostname or "unknown"
        except Exception:
            return "unavailable"


class MainWindow(QMainWindow):
    open_requested = Signal()
    check_login_requested = Signal()
    scan_requested = Signal()
    delete_requested = Signal()
    shutdown_requested = Signal()

    def __init__(self, paths: AppPaths, database: Database, logger: logging.Logger):
        super().__init__()
        self.paths = paths
        self.database = database
        self.logger = logger
        self.current_state = CleanupState.IDLE
        self.logged_in = False
        self.setWindowTitle("小红书历史评论清理工具")
        self.setMinimumSize(780, 720)
        self.resize(860, 780)
        self.setStyleSheet(APP_STYLESHEET)
        self._build_ui()
        self._update_login(False)
        self.pause_button.setEnabled(False)

        self.thread = QThread(self)
        self.worker = BrowserWorker(paths, database, logger)
        self.worker.moveToThread(self.thread)
        self.open_requested.connect(self.worker.open_xhs)
        self.check_login_requested.connect(self.worker.check_login)
        self.scan_requested.connect(self.worker.scan)
        self.delete_requested.connect(self.worker.delete_all)
        self.shutdown_requested.connect(self.worker.shutdown)
        self.worker.state_changed.connect(self._set_state)
        self.worker.counts_changed.connect(self._update_counts)
        self.worker.login_changed.connect(self._update_login)
        self.worker.scan_finished.connect(self._scan_finished)
        self.worker.error.connect(self._show_error)
        # quit() must run even while closeEvent is synchronously waiting for the
        # worker; a queued connection back to the GUI thread would deadlock.
        self.worker.finished.connect(self.thread.quit, Qt.DirectConnection)
        self.thread.start()
        self._update_counts(self.database.counts())

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("root")
        layout = QVBoxLayout(central)
        layout.setContentsMargins(38, 30, 38, 30)
        layout.setSpacing(18)

        header = QHBoxLayout()
        header.setSpacing(18)
        header_text = QVBoxLayout()
        header_text.setSpacing(3)
        eyebrow = QLabel("XHS COMMENT CLEANER")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("历史评论清理")
        title.setObjectName("title")
        subtitle = QLabel("本地运行 · 使用独立 Edge 环境 · 每条删除均经过确认")
        subtitle.setObjectName("subtitle")
        header_text.addWidget(eyebrow)
        header_text.addWidget(title)
        header_text.addWidget(subtitle)
        header.addLayout(header_text)
        header.addStretch()
        self.log_button = self._button("查看日志", "quiet")
        header.addWidget(self.log_button, 0, Qt.AlignBottom)
        layout.addLayout(header)

        account = self._surface()
        account_layout = QHBoxLayout(account)
        account_layout.setContentsMargins(24, 20, 24, 20)
        account_layout.setSpacing(14)
        self.login_dot = QFrame()
        self.login_dot.setObjectName("statusDot")
        self.login_dot.setFixedSize(12, 12)
        account_layout.addWidget(self.login_dot, 0, Qt.AlignVCenter)
        login_text = QVBoxLayout()
        login_text.setSpacing(2)
        self.login_label = QLabel("尚未检查登录状态")
        self.login_label.setObjectName("statusTitle")
        self.login_hint = QLabel("打开小红书并完成扫码或手机号登录")
        self.login_hint.setObjectName("muted")
        login_text.addWidget(self.login_label)
        login_text.addWidget(self.login_hint)
        account_layout.addLayout(login_text)
        account_layout.addStretch()
        self.open_button = self._button("打开小红书", "primary")
        self.check_button = self._button("检查登录状态", "secondary")
        account_layout.addWidget(self.open_button)
        account_layout.addWidget(self.check_button)
        layout.addWidget(account)

        history = self._surface()
        history_layout = QVBoxLayout(history)
        history_layout.setContentsMargins(24, 20, 24, 22)
        history_layout.setSpacing(16)
        history_header = QHBoxLayout()
        history_title = QLabel("扫描结果")
        history_title.setObjectName("sectionTitle")
        history_header.addWidget(history_title)
        history_header.addStretch()
        self.preview_button = self._button("查看结果", "quiet")
        self.scan_button = self._button("开始扫描", "secondary")
        history_header.addWidget(self.preview_button)
        history_header.addWidget(self.scan_button)
        history_layout.addLayout(history_header)

        metrics = QHBoxLayout()
        metrics.setSpacing(18)
        self.count_labels: dict[str, QLabel] = {}
        metric_items = (
            ("discovered", "已发现"), ("pending", "待删除"),
            ("deleted", "已删除"), ("failed", "失败"), ("skipped", "已跳过"),
        )
        for index, (key, text) in enumerate(metric_items):
            metric, value = self._metric(text)
            self.count_labels[key] = value
            metrics.addWidget(metric, 1)
            if index < len(metric_items) - 1:
                divider = QFrame()
                divider.setObjectName("divider")
                metrics.addWidget(divider)
        history_layout.addLayout(metrics)
        self.coverage_label = QLabel("尚未扫描。请先确认登录状态，再开始扫描。")
        self.coverage_label.setObjectName("muted")
        self.coverage_label.setWordWrap(True)
        history_layout.addWidget(self.coverage_label)
        layout.addWidget(history)

        cleanup = self._surface()
        delete_layout = QVBoxLayout(cleanup)
        delete_layout.setContentsMargins(24, 20, 24, 22)
        delete_layout.setSpacing(14)
        cleanup_header = QHBoxLayout()
        cleanup_title = QLabel("清理进度")
        cleanup_title.setObjectName("sectionTitle")
        self.progress_detail = QLabel("0 / 0")
        self.progress_detail.setObjectName("muted")
        cleanup_header.addWidget(cleanup_title)
        cleanup_header.addStretch()
        cleanup_header.addWidget(self.progress_detail)
        delete_layout.addLayout(cleanup_header)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.delete_button = self._button("删除全部已扫描评论", "primary")
        self.pause_button = self._button("暂停", "secondary")
        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        buttons.addWidget(self.delete_button)
        buttons.addWidget(self.pause_button)
        delete_layout.addWidget(self.progress)
        delete_layout.addLayout(buttons)
        layout.addWidget(cleanup)

        status = QFrame()
        status.setObjectName("surface")
        status_layout = QHBoxLayout(status)
        status_layout.setContentsMargins(24, 16, 24, 16)
        status_caption = QLabel("当前状态")
        status_caption.setObjectName("sectionTitle")
        self.status_label = QLabel("等待操作")
        self.status_label.setObjectName("statusText")
        self.status_label.setWordWrap(True)
        self.status_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        status_layout.addWidget(status_caption)
        status_layout.addSpacing(18)
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        layout.addWidget(status)
        layout.addStretch(1)
        self.setCentralWidget(central)

        self.open_button.clicked.connect(self.open_requested.emit)
        self.check_button.clicked.connect(self.check_login_requested.emit)
        self.scan_button.clicked.connect(self.scan_requested.emit)
        self.preview_button.clicked.connect(self._preview)
        self.delete_button.clicked.connect(self._confirm_delete)
        self.pause_button.clicked.connect(self._pause)
        self.log_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.paths.log_file))))

    @staticmethod
    def _button(text: str, variant: str) -> QPushButton:
        button = QPushButton(text)
        button.setProperty("variant", variant)
        button.setCursor(Qt.PointingHandCursor)
        return button

    @staticmethod
    def _surface() -> QFrame:
        frame = QFrame()
        frame.setObjectName("surface")
        return frame

    @staticmethod
    def _metric(text: str) -> tuple[QWidget, QLabel]:
        widget = QWidget()
        widget.setStyleSheet("background: transparent;")
        column = QVBoxLayout(widget)
        column.setContentsMargins(4, 2, 4, 2)
        column.setSpacing(1)
        value = QLabel("0")
        value.setObjectName("metricValue")
        value.setAlignment(Qt.AlignCenter)
        label = QLabel(text)
        label.setObjectName("metricLabel")
        label.setAlignment(Qt.AlignCenter)
        column.addWidget(value)
        column.addWidget(label)
        return widget, value

    @Slot(str, str)
    def _set_state(self, state: str, message: str) -> None:
        self.current_state = CleanupState(state)
        self.status_label.setText(message)
        busy = self.current_state in (CleanupState.SCANNING, CleanupState.DELETING)
        self.open_button.setEnabled(not busy)
        self.check_button.setEnabled(not busy)
        self.scan_button.setEnabled(not busy and self.logged_in)
        self.delete_button.setEnabled(
            not busy and self.logged_in and self.database.counts()["pending"] > 0
        )
        self.pause_button.setEnabled(busy)

    @Slot(dict)
    def _update_counts(self, counts: dict[str, int]) -> None:
        for key, label in self.count_labels.items():
            label.setText(str(counts.get(key, 0)))
        total = counts.get("discovered", 0)
        done = counts.get("deleted", 0) + counts.get("failed", 0) + counts.get("skipped", 0)
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(done)
        self.progress_detail.setText(f"{done} / {total}")
        self.delete_button.setText("继续删除" if counts.get("deleted", 0) else "删除全部已扫描评论")
        self.preview_button.setEnabled(total > 0)
        self.delete_button.setEnabled(
            self.logged_in
            and self.current_state not in (CleanupState.SCANNING, CleanupState.DELETING)
            and counts.get("pending", 0) > 0
        )

    @Slot(bool)
    def _update_login(self, logged_in: bool) -> None:
        self.logged_in = logged_in
        self.login_label.setText("已登录，可以继续" if logged_in else "尚未确认登录")
        self.login_hint.setText(
            "登录状态保存在此工具的独立 Edge 环境中" if logged_in else
            "打开小红书并完成扫码或手机号登录"
        )
        color = "#22A06B" if logged_in else "#A7ABB2"
        self.login_dot.setStyleSheet(f"background: {color}; border-radius: 6px;")
        busy = self.current_state in (CleanupState.SCANNING, CleanupState.DELETING)
        self.scan_button.setEnabled(logged_in and not busy)
        self.delete_button.setEnabled(
            logged_in and not busy and self.database.counts()["pending"] > 0
        )

    @Slot(bool, int)
    def _scan_finished(self, complete: bool, total: int) -> None:
        self.coverage_label.setText(
            f"已明确到达记录末尾，共找到 {total} 条。" if complete else
            f"已找到 {total} 条，但无法确认是否覆盖全部历史记录。"
        )

    def _confirm_delete(self) -> None:
        pending = self.database.counts()["pending"]
        if pending and ConfirmDeleteDialog(pending, self).exec() == QDialog.Accepted:
            self.delete_requested.emit()

    def _pause(self) -> None:
        # Direct call is intentional: it only sets thread-safe Events, allowing the
        # running worker loop to notice without waiting for its Qt event loop.
        self.worker.request_pause()
        self.status_label.setText("正在完成当前操作，随后暂停…")

    def _preview(self) -> None:
        PreviewDialog(self.database.list_comments(), self).exec()

    @Slot(str)
    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "无法继续", message)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.current_state == CleanupState.DELETING:
            answer = QMessageBox.question(
                self, "确认退出", "当前正在执行删除任务。\n\n关闭不会丢失已完成进度，是否退出？"
            )
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            self.worker.request_pause()
        self.shutdown_requested.emit()
        if not self.thread.wait(35_000):
            self.logger.warning("action=shutdown result=timeout")
            QMessageBox.warning(self, "正在安全退出", "当前操作尚未结束，请稍后再次关闭程序。")
            event.ignore()
            return
        self.logger.info("action=app_stop result=success")
        event.accept()
