"""All page selectors live here.

These candidates are intentionally limited to semantic text and stable-looking data
attributes. They MUST be revalidated against the current Xiaohongshu web page before
a release. No positional selectors or screen coordinates are allowed.
"""

LOGIN_REQUIRED_TEXT = ("登录后推荐更懂你的笔记", "登录", "扫码登录")
LOGGED_IN_MARKERS = (
    'a[href*="/user/profile/"] img',
    '[data-testid="user-avatar"]',
)
CURRENT_USER_LINKS = (
    'a[href*="/user/profile/"][class*="user"]',
    'a[href*="/user/profile/"]:has(img)',
)

# Exact comment container lookup is only allowed when the live DOM exposes an ID.
COMMENT_BY_ID = (
    '[data-comment-id="{comment_id}"]',
    '[data-id="{comment_id}"][class*="comment"]',
    '#comment-{comment_id}',
)
COMMENT_CONTAINERS = (
    '[data-comment-id]',
    '[data-id][class*="comment"]',
)
COMMENT_AUTHOR_LINK = 'a[href*="/user/profile/"]'
COMMENT_MENU_BUTTONS = ("更多", "评论操作")
DELETE_TEXT = "删除"
CONFIRM_DELETE_TEXT = ("确认删除", "删除")

RISK_TEXT = (
    "访问过于频繁", "操作频繁", "账号异常", "安全验证", "验证码", "请完成验证", "请求失败"
)
LOGIN_EXPIRED_TEXT = ("登录状态已失效", "请登录", "重新登录")

# Used only to observe history items already rendered by a normal page.
HISTORY_END_TEXT = ("没有更多了", "已经到底了")
