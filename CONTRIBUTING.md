# Contributing

欢迎提交问题和改进。这个项目涉及不可恢复的删除操作，安全性优先于兼容范围和速度。

## 开发约束

- 不提交 Cookie、Token、手机号、真实账号数据或带登录状态的浏览器 profile。
- 不加入验证码绕过、指纹伪装、代理池、私有 API 高频调用或坐标点击。
- 所有小红书页面 selector 集中维护在 `app/xhs/selectors.py`。
- 不能确认评论 ID、作者身份或删除结果时，应停止或跳过，不能猜测操作目标。
- 页面适配变更应说明验证日期、测试页面和失败时的安全行为。

## 提交前检查

```bash
python -m unittest discover -s tests -v
python -m compileall -q app tests
```

涉及真实页面的变更还应使用专门测试账号完成单条评论删除、刷新验证、登录失效和风控暂停测试。
