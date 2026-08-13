# Third-party research references

No third-party package is vendored into this repository. The following open-source projects were consulted to validate current Xiaohongshu Web interoperability behavior:

- [jackwener/xiaohongshu-cli](https://github.com/jackwener/xiaohongshu-cli), Apache License 2.0 — confirmed current web comment-list/delete endpoints and the fields required for comment deletion.
- [BodaFu/auto-rednote](https://github.com/BodaFu/auto-rednote), MIT License — confirmed that the normal `/notification` page exposes reply notification data through `/api/sns/web/v1/you/mentions`, including target-comment and note metadata.

This project implements its own Python/Playwright workflow. It does not include authentication secrets, signing implementations, browser-fingerprint spoofing, or code copied from those projects.
