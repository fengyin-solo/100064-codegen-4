"""访客登记与门禁通行接口。

角色身份优先取请求头 X-Operator-Role / X-Operator-Department，
也允许在提交体 values 里携带（role、department），便于脚本与自动化测试直接调用。

错误口径：
- 越权操作（角色不符、跨部门审批）抛 PermissionDenied，由全局处理器统一转成 403；
- 业务规则违例（缺字段、状态不对、有效期受控等）沿用全平台约定，返回 200 + ok:false 说明原因。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, Query
from fastapi.responses import Response

from app.errors import PermissionDenied, VisitorError
from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.visitor import (
    DEPARTMENTS,
    PASS_STATUS_LABEL,
    ROLE_GUARD,
    ROLE_HOST,
    ROLE_RECEPTION,
    VISIT_STATUS,
    visitor_service,
)

router = APIRouter(prefix="/api", tags=["访客与门禁"])

LIST_FIELDS = [
    "访客编号", "访客姓名", "访客单位", "联系电话", "受访部门",
    "被访人", "来访事由", "来访日期", "status",
]


def _operator_role(payload: EntryPayload, header_role: str | None) -> str | None:
    if payload.values.get("role"):
        return str(payload.values["role"])
    return header_role


def _operator_department(payload: EntryPayload, header_dept: str | None) -> str | None:
    if payload.values.get("department"):
        return str(payload.values["department"])
    return header_dept


def _business_result(exc: VisitorError) -> ActionResult:
    """403 越权错误继续上抛，由全局处理器转译；其余业务错误返回可读的 ok:false。"""
    if isinstance(exc, PermissionDenied) or exc.status_code in (401, 403, 404):
        raise exc
    return ActionResult(ok=False, message=exc.message)


# ---- 字典与列表 ---------------------------------------------------------


@router.get("/visitor/meta")
def visitor_meta() -> dict[str, Any]:
    """给前端提供部门、角色、状态字典，避免各页面各写一份。"""
    return {
        "departments": DEPARTMENTS,
        "roles": [
            {"value": ROLE_RECEPTION, "label": "前台", "desc": "仅访客登记"},
            {"value": ROLE_HOST, "label": "被访人", "desc": "仅审批本部门来访"},
            {"value": ROLE_GUARD, "label": "门禁管理员", "desc": "受控发证、核销、门禁"},
        ],
        "visit_status": list(VISIT_STATUS),
        "pass_status": list(PASS_STATUS_LABEL),
    }


@router.get("/visitor", response_model=PageResult[dict])
def list_visitors(
    visit_date: str | None = Query(default=None, description="按来访日期过滤，默认传今天；传 all 表示不过滤"),
    status: str | None = Query(default=None, description="待审批、已批准、已拒绝"),
    keyword: str | None = Query(default=None, description="按访客姓名或单位检索"),
    page: int = 1,
    size: int = 50,
) -> PageResult[dict]:
    """访客登记列表：每条都带可发放状态，登记页与门禁页共用同一口径。"""
    if size > 200:
        raise VisitorError("每页最多 200 条，请缩小分页范围", status_code=400)
    date_filter = None if visit_date == "all" else visit_date
    items, total = visitor_service.list_visitors(
        visit_date=date_filter, status=status, keyword=keyword, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/visitor/passes")
def list_passes(only_active: bool = False) -> dict[str, Any]:
    """通行证清单（门禁页使用）：状态由服务端按当前时间实时计算。"""
    return {"items": visitor_service.list_passes(only_active=only_active)}


@router.get("/visitor/access-logs")
def list_logs(limit: int = 30) -> dict[str, Any]:
    """最近的门禁刷卡记录。"""
    return {"items": visitor_service.list_logs(limit=limit)}


# ---- 登记与审批 --------------------------------------------------------


@router.post("/visitor", response_model=ActionResult)
def register_visitor(
    payload: EntryPayload,
    response: Response,
    x_operator_role: str | None = Header(default=None),
) -> ActionResult:
    """前台登记来访人员、受访部门归属与来访事由；其他角色登记会被拒绝。"""
    try:
        entry = visitor_service.register(payload.values, _operator_role(payload, x_operator_role))
    except VisitorError as exc:
        return _business_result(exc)
    response.status_code = 201
    return ActionResult(ok=True, message="访客已登记，等待受访部门审批", entry=entry)


@router.post("/visitor/{visitor_id}/approval", response_model=ActionResult)
def approve_visitor(
    visitor_id: int,
    payload: EntryPayload,
    x_operator_role: str | None = Header(default=None),
    x_operator_department: str | None = Header(default=None),
) -> ActionResult:
    """被访人审批：只能处理归属本部门的待审批来访，越权时说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    try:
        entry = visitor_service.approve(
            visitor_id,
            action,
            payload.values,
            _operator_role(payload, x_operator_role),
            _operator_department(payload, x_operator_department),
        )
    except VisitorError as exc:
        return _business_result(exc)
    message = "来访已批准，可由门禁管理员发放通行证" if action == "批准来访" else "来访已拒绝"
    return ActionResult(ok=True, message=message, entry=entry)


# ---- 通行证发放、核销与刷卡 -------------------------------------------


@router.post("/visitor/{visitor_id}/pass", response_model=ActionResult)
def issue_pass(
    visitor_id: int,
    payload: EntryPayload,
    response: Response,
    x_operator_role: str | None = Header(default=None),
) -> ActionResult:
    """门禁管理员受控发证：已批准、一人一证、有效期在来访当日且 5 分钟~24 小时。"""
    try:
        entry = visitor_service.issue(visitor_id, payload.values, _operator_role(payload, x_operator_role))
    except VisitorError as exc:
        return _business_result(exc)
    response.status_code = 201
    return ActionResult(ok=True, message=f"通行证 {entry['通行证编号']} 已发放", entry=entry)


@router.post("/visitor/pass/{pass_id}/checkout", response_model=ActionResult)
def checkout_pass(
    pass_id: int,
    payload: EntryPayload,
    x_operator_role: str | None = Header(default=None),
) -> ActionResult:
    """离开核销：只有门禁管理员可核销；重复核销同一张证只算一次。"""
    try:
        entry = visitor_service.checkout(pass_id, _operator_role(payload, x_operator_role))
    except VisitorError as exc:
        return _business_result(exc)
    return ActionResult(ok=True, message=str(entry.pop("提示", "通行证已核销")), entry=entry)


@router.post("/visitor/pass/{pass_code}/swipe", response_model=ActionResult)
def swipe_pass(pass_code: str, payload: EntryPayload | None = None) -> ActionResult:
    """门禁闸机刷卡：过期/已核销/未生效一律拒绝并说明原因。"""
    payload = payload or EntryPayload()
    try:
        result = visitor_service.swipe(pass_code, payload.values)
    except VisitorError as exc:
        return _business_result(exc)
    return ActionResult(ok=bool(result["ok"]), message=result["message"], entry=result["通行证"])
