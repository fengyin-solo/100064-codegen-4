"""组织目录：访客业务涉及的操作人员、角色与受访部门口径。

角色分工：
- reception 前台：只能做访客登记；
- host 被访人：只能审批受访部门与自己所属部门一致的来访；
- guard 门禁管理员：负责发放/核销通行证、门禁刷卡，发放受状态与有效期约束。
"""
from __future__ import annotations

from typing import Any

ROLE_RECEPTION = "reception"
ROLE_HOST = "host"
ROLE_GUARD = "guard"

ROLE_LABELS: dict[str, str] = {
    ROLE_RECEPTION: "前台",
    ROLE_HOST: "被访人",
    ROLE_GUARD: "门禁管理员",
}

OPERATORS: list[dict[str, str]] = [
    {"id": "reception_wang", "name": "王敏", "role": ROLE_RECEPTION, "department": "行政前台"},
    {"id": "host_zhang", "name": "张伟", "role": ROLE_HOST, "department": "化学分析部"},
    {"id": "host_li", "name": "李娜", "role": ROLE_HOST, "department": "微生物检测部"},
    {"id": "host_chen", "name": "陈强", "role": ROLE_HOST, "department": "仪器分析部"},
    {"id": "guard_zhao", "name": "赵刚", "role": ROLE_GUARD, "department": "安保组"},
]

# 可受访部门及其被访人（前台登记时受访部门与被访人必须对得上）
DEPARTMENTS: list[dict[str, str]] = [
    {"name": "化学分析部", "host": "张伟", "host_id": "host_zhang"},
    {"name": "微生物检测部", "host": "李娜", "host_id": "host_li"},
    {"name": "仪器分析部", "host": "陈强", "host_id": "host_chen"},
]


def find_operator(operator_id: str | None) -> dict[str, str] | None:
    if not operator_id:
        return None
    for operator in OPERATORS:
        if operator["id"] == operator_id:
            return operator
    return None


def department(name: str) -> dict[str, str] | None:
    for item in DEPARTMENTS:
        if item["name"] == name:
            return item
    return None


def describe(operator: dict[str, Any]) -> str:
    """「赵刚（门禁管理员 · 安保组）」这类可读身份描述，用于越权提示。"""
    return f"{operator['name']}（{ROLE_LABELS.get(operator['role'], operator['role'])} · {operator['department']}）"
