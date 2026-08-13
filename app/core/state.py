from enum import Enum


class CleanupState(str, Enum):
    IDLE = "IDLE"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    SCANNING = "SCANNING"
    READY = "READY"
    DELETING = "DELETING"
    PAUSED = "PAUSED"
    BLOCKED = "BLOCKED"
    FINISHED = "FINISHED"
    ERROR = "ERROR"


STATE_TEXT = {
    CleanupState.IDLE: "等待操作",
    CleanupState.LOGIN_REQUIRED: "请在小红书完成登录",
    CleanupState.SCANNING: "正在扫描历史评论",
    CleanupState.READY: "扫描结果可以处理",
    CleanupState.DELETING: "正在逐条删除",
    CleanupState.PAUSED: "已暂停",
    CleanupState.BLOCKED: "小红书要求人工处理",
    CleanupState.FINISHED: "当前扫描到的评论已全部处理",
    CleanupState.ERROR: "发生错误，任务已停止",
}
