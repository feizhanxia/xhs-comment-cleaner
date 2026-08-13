from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.storage.models import Comment


class ConfirmDeleteDialog(QDialog):
    def __init__(self, count: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("确认永久删除")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            f"已扫描到 {count} 条待处理的历史评论和回复。\n\n"
            "即将永久删除这些内容，删除后通常无法恢复。\n\n是否继续？"
        ))
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        self.confirm_button = buttons.button(QDialogButtonBox.Ok)
        self.confirm_button.setText("确认删除（2）")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        self.confirm_button.setEnabled(False)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._remaining = 2
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1_000)

    def _tick(self) -> None:
        self._remaining -= 1
        if self._remaining <= 0:
            self._timer.stop()
            self.confirm_button.setText("确认删除")
            self.confirm_button.setEnabled(True)
        else:
            self.confirm_button.setText(f"确认删除（{self._remaining}）")


class PreviewDialog(QDialog):
    def __init__(self, comments: list[Comment], parent=None):
        super().__init__(parent)
        self.setWindowTitle("扫描结果")
        self.resize(760, 440)
        layout = QVBoxLayout(self)
        table = QTableWidget(len(comments), 3)
        table.setHorizontalHeaderLabels(["评论内容", "笔记链接", "状态"])
        for row, comment in enumerate(comments):
            table.setItem(row, 0, QTableWidgetItem(comment.content))
            table.setItem(row, 1, QTableWidgetItem(comment.note_url))
            table.setItem(row, 2, QTableWidgetItem(comment.delete_status))
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(table)
