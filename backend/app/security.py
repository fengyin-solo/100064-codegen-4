"""访客与门禁的操作身份依赖：从请求头识别操作人，并按角色/部门做越权拦截。"""
from __future__ import annotations

from typing import Any

from fastapi import Header, HTTPException

from app import directory
from app.directory import ROLE_LABELS, describe


def current_operator(x_operator_id: str | None = Header(default=None, alias="X-Operator-Id")) -> dict[str, str]:
    """所有访客写操作都要带 X-Operator-Id；不带或查无此人直接拒绝。"""
    operator = directory.find_operator(x_operator_id)
    if operator is None:
        raise HTTPException(
            status_code=401,
            detail="未能识别操作身份，请先在页面右上角选择操作人后再操作",
        )
    return operator


def require_roles(operator: dict[str, Any], roles: tuple[str, ...], action: str) -> None:
    """角色不符时 403 拒绝，并把「谁、是什么角色、为什么不能做」说清楚。"""
    if operator["role"] not in roles:
        allowed = "、".join(ROLE_LABELS[role] for role in roles)
        raise HTTPException(
            status_code=403,
            detail=f"{describe(operator)}无权{action}：该操作仅限{allowed}执行，已被系统拒绝",
        )
