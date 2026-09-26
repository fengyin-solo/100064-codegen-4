"""门禁通行接口：可发放清单、受控发放、离开核销、刷卡判定与刷卡记录。

发放/核销是门禁管理员专属；刷卡属于门禁终端动作，仍要求携带已登记的操作身份。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.directory import ROLE_GUARD
from app.schemas import ActionResult, EntryPayload, PageResult
from app.security import current_operator, require_roles
from app.services.access import AccessService

router = APIRouter(prefix="/api/access", tags=["门禁通行"])

service = AccessService()


@router.get("/issuable")
def list_issuable(
    visit_date: str | None = Query(default=None, description="可发放清单默认只看当天"),
) -> dict[str, Any]:
    """当天已批准且尚未发放通行证的来访，供门禁管理员发放。"""
    items = service.issuable_visits(visit_date)
    return {"items": items, "total": len(items)}


@router.get("/passes", response_model=PageResult[dict])
def list_passes(
    status: str | None = Query(default=None, description="通行中、已过期、未生效、已核销"),
    keyword: str | None = Query(default=None, description="按通行证号或访客姓名检索"),
    page: int = 1,
    size: int = 50,
) -> PageResult[dict]:
    """通行证台账：通行证状态按当前时刻动态计算。"""
    items, total = service.list_passes(status=status, keyword=keyword, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/logs")
def list_logs(keyword: str | None = Query(default=None), size: int = 30) -> dict[str, Any]:
    """最近的刷卡/核销记录，放行与拒绝都留痕。"""
    return {"items": service.list_logs(keyword=keyword, size=size)}


@router.post("/passes", response_model=ActionResult)
def issue_pass(
    payload: EntryPayload,
    operator: dict = Depends(current_operator),
) -> ActionResult:
    """门禁管理员受控发放：角色、来访状态、来访日、重复发放、有效期跨日都会被拦。"""
    require_roles(operator, (ROLE_GUARD,), "发放通行证")
    values = payload.values
    try:
        visit_id = int(values.get("visit_id"))
    except (TypeError, ValueError):
        return ActionResult(ok=False, message="缺少来访标识 visit_id，无法发放通行证")
    entry, message = service.issue_pass(
        visit_id,
        str(values.get("valid_from") or "").strip(),
        str(values.get("valid_until") or "").strip(),
        str(values.get("point") or "").strip(),
        operator,
    )
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/checkout", response_model=ActionResult)
def checkout_pass(
    payload: EntryPayload,
    operator: dict = Depends(current_operator),
) -> ActionResult:
    """离开核销：门禁管理员操作；重复核销同一张通行证只计一次，不报错。"""
    require_roles(operator, (ROLE_GUARD,), "核销通行证")
    code = str(payload.values.get("pass_no") or "").strip().upper()
    if not code:
        return ActionResult(ok=False, message="请输入要核销的通行证号")
    entry, message, already = service.checkout_pass(code, operator)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/swipe")
def swipe(
    payload: EntryPayload,
    operator: dict = Depends(current_operator),
) -> dict[str, Any]:
    """刷门禁：过期、未生效、已核销或号码不存在一律拒绝并记录原因。"""
    values = payload.values
    code = str(values.get("pass_no") or "").strip().upper()
    point = str(values.get("point") or "东门访客通道").strip()
    if not code:
        raise HTTPException(status_code=400, detail="请输入通行证号再刷卡")
    result = service.swipe(code, point)
    result["operator"] = {"id": operator["id"], "name": operator["name"]}
    return result
