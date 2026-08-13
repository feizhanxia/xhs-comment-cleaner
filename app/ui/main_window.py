from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QObject, QThread, Signal, Slot, Qt
from PySide6.QtGui import QCloseEvent, QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
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
        try:
            page = self._browser().open_xhs()
            logged_in = LoginManager(page).is_logged_in()
            self.login_changed.emit(logged_in)
            state = CleanupState.IDLE if logged_in else CleanupState.LOGIN_REQUIRED
            self.state_changed.emit(state.value, STATE_TEXT[state])
        except EdgeUnavailable as exc:
            self.error.emit(str(exc))
        except Exception:
            self.logger.exception("action=open_xhs result=failed")
            self.error.emit("小红书页面加载失败，请稍后重试。")

    @Slot()
    def check_login(self) -> None:
        try:
            page = self._browser().start()
            logged_in = LoginManager(page).is_logged_in()
            self.login_changed.emit(logged_in)
            if not logged_in:
                self.state_changed.emit(CleanupState.LOGIN_REQUIRED.value, STATE_TEXT[CleanupState.LOGIN_REQUIRED])
        except EdgeUnavailable as exc:
            self.error.emit(str(exc))

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
        finally:
            self.cleanup = None

    @Slot()
    def shutdown(self) -> None:
        if self.browser:
            self.browser.close()
        self.finished.emit()

    def _browser(self) -> BrowserManager:
        if self.browser is None:
            self.browser = BrowserManager(self.paths.profile, self.logger)
        return self.browser

    def _screenshot(self, label: str) -> None:
        if self.browser:
            self.browser.screenshot(self.paths.screenshots, label)


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
        self.setWindowTitle("小红书历史评论清理工具")
        self.setMinimumSize(560, 580)
        self._build_ui()

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
        layout = QVBoxLayout(central)
        title = QLabel("小红书历史评论清理工具")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 22px; font-weight: 600; margin: 14px;")
        layout.addWidget(title)

        login_box = QGroupBox("登录状态")
        login_layout = QHBoxLayout(login_box)
        self.login_label = QLabel("● 未确认")
        self.open_button = QPushButton("打开小红书 / 登录")
        self.check_button = QPushButton("我已登录，检查状态")
        login_layout.addWidget(self.login_label)
        login_layout.addStretch()
        login_layout.addWidget(self.open_button)
        login_layout.addWidget(self.check_button)
        layout.addWidget(login_box)

        history_box = QGroupBox("历史评论")
        grid = QGridLayout(history_box)
        self.count_labels: dict[str, QLabel] = {}
        for column, (key, text) in enumerate((
            ("discovered", "已发现"), ("pending", "待删除"),
            ("deleted", "已删除"), ("failed", "失败"), ("skipped", "已跳过"),
        )):
            grid.addWidget(QLabel(text), 0, column)
            label = QLabel("0")
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("font-size: 18px; font-weight: 600;")
            self.count_labels[key] = label
            grid.addWidget(label, 1, column)
        controls = QHBoxLayout()
        self.scan_button = QPushButton("扫描当前评论记录页")
        self.preview_button = QPushButton("查看扫描结果")
        controls.addWidget(self.scan_button)
        controls.addWidget(self.preview_button)
        grid.addLayout(controls, 2, 0, 1, 5)
        self.coverage_label = QLabel("尚未扫描")
        self.coverage_label.setWordWrap(True)
        grid.addWidget(self.coverage_label, 3, 0, 1, 5)
        layout.addWidget(history_box)

        delete_box = QGroupBox("清理进度")
        delete_layout = QVBoxLayout(delete_box)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.delete_button = QPushButton("删除全部已扫描评论")
        self.pause_button = QPushButton("暂停")
        buttons = QHBoxLayout()
        buttons.addWidget(self.delete_button)
        buttons.addWidget(self.pause_button)
        delete_layout.addWidget(self.progress)
        delete_layout.addLayout(buttons)
        layout.addWidget(delete_box)

        status_box = QGroupBox("当前状态")
        status_layout = QVBoxLayout(status_box)
        self.status_label = QLabel("等待操作")
        self.status_label.setWordWrap(True)
        status_layout.addWidget(self.status_label)
        layout.addWidget(status_box)

        footer = QHBoxLayout()
        self.log_button = QPushButton("查看日志")
        footer.addStretch()
        footer.addWidget(self.log_button)
        layout.addLayout(footer)
        self.setCentralWidget(central)

        self.open_button.clicked.connect(self.open_requested.emit)
        self.check_button.clicked.connect(self.check_login_requested.emit)
        self.scan_button.clicked.connect(self.scan_requested.emit)
        self.preview_button.clicked.connect(self._preview)
        self.delete_button.clicked.connect(self._confirm_delete)
        self.pause_button.clicked.connect(self._pause)
        self.log_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.paths.log_file))))

    @Slot(str, str)
    def _set_state(self, state: str, message: str) -> None:
        self.current_state = CleanupState(state)
        self.status_label.setText(message)
        busy = self.current_state in (CleanupState.SCANNING, CleanupState.DELETING)
        self.scan_button.setEnabled(not busy)
        self.delete_button.setEnabled(not busy and self.database.counts()["pending"] > 0)
        self.pause_button.setEnabled(busy)

    @Slot(dict)
    def _update_counts(self, counts: dict[str, int]) -> None:
        for key, label in self.count_labels.items():
            label.setText(str(counts.get(key, 0)))
        total = counts.get("discovered", 0)
        done = counts.get("deleted", 0) + counts.get("failed", 0) + counts.get("skipped", 0)
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(done)
        self.progress.setFormat(f"{done} / {total}")
        self.delete_button.setText("继续删除" if counts.get("deleted", 0) else "删除全部已扫描评论")
        self.delete_button.setEnabled(self.current_state not in (CleanupState.SCANNING, CleanupState.DELETING) and counts.get("pending", 0) > 0)

    @Slot(bool)
    def _update_login(self, logged_in: bool) -> None:
        self.login_label.setText("● 已登录" if logged_in else "● 未登录")
        self.login_label.setStyleSheet("color: #18864b;" if logged_in else "color: #a33;")

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
        event.accept()
