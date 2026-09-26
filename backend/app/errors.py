"""访客与门禁业务错误：越权访问与业务规则违例分开，便于路由层翻译成不同状态码。"""
from __future__ import annotations


class VisitorError(Exception):
    """访客模块的可读错误：message 直接展示给前端，status 决定 HTTP 状态码。"""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class PermissionDenied(VisitorError):
    """越权操作：角色不符或跨部门审批，统一返回 403。"""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=403)
