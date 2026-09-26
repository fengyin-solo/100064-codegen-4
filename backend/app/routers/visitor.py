"""访客登记接口：前台登记来访，被访人按部门审批。

鉴权口径：
- 登记：仅前台；
- 审批/驳回：仅被访人，且来访受访部门必须与其所属部门一致（服务层再校验一次）。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app import directory
from app.directory import ROLE_GUARD, ROLE_HOST, ROLE_RECEPTION
from app.schemas import ActionResult, EntryPayload, PageResult
from app.security import current_operator, require_roles
from app.services.visitor import VisitorService

router = APIRouter(prefix="/api/visitor", tags=["访客登记"])

service = VisitorService()

LIST_FIELDS = ["来访编号", "访客姓名", "来访单位", "受访部门", "被访人", "来访事由", "来访日期", "到访时间", "登记人", "审批人"]


@router.get("/operators")
def list_operators() -> dict[str, Any]:
    """操作人目录：前端身份切换器按角色分组渲染。"""
    return {
        "roles": [
            {"id": role_id, "name": directory.ROLE_LABELS[role_id]}
            for role_id in (ROLE_RECEPTION, ROLE_HOST, ROLE_GUARD)
        ],
        "operators": directory.OPERATORS,
        "departments": [item["name"] for item in directory.DEPARTMENTS],
        "departmentHosts": directory.DEPARTMENTS,
    }


@router.get("", response_model=PageResult[dict])
def list_entries(
    visit_date: str | None = Query(default=None, description="按来访日期过滤，默认全部；前端默认传今天"),
    dept: str | None = Query(default=None, description="按受访部门过滤"),
    status: str | None = Query(default=None, description="待审批、已批准、已驳回、已核销"),
    keyword: str | None = Query(default=None, description="按访客姓名/单位/编号检索"),
    page: int = 1,
    size: int = 50,
) -> PageResult[dict]:
    """访客登记列表；无来访时返回空页，由前端展示空态文案。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(
        visit_date=visit_date, dept=dept, status=status, keyword=keyword, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"来访登记 {entry_id} 不存在或已删除")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(
    payload: EntryPayload,
    operator: dict = Depends(current_operator),
) -> ActionResult:
    """访客登记：前台专属操作，越权调用返回 403 并说明原因。"""
    require_roles(operator, (ROLE_RECEPTION,), "登记访客")
    entry, message = service.create_entry(payload.values, operator)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="访客登记成功，已提交被访人审批", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(
    entry_id: int,
    payload: EntryPayload,
    operator: dict = Depends(current_operator),
) -> ActionResult:
    """被访人审批：仅本部门来访可批；动作支持 批准来访 / 驳回来访。"""
    require_roles(operator, (ROLE_HOST,), "审批来访")
    action = str(payload.values.get("action") or "").strip()
    if action == "批准来访":
        approved = True
    elif action == "驳回来访":
        approved = False
    else:
        return ActionResult(ok=False, message=f"动作「{action}」不属于访客审批可执行范围")

    # 被访人审批别的部门的来访属于越权，直接 403 并说明原因
    entry_before = service.get_entry(entry_id)
    if entry_before is None:
        return ActionResult(ok=False, message=f"来访登记 {entry_id} 不存在或已删除")
    if entry_before.get("受访部门") != operator["department"]:
        raise HTTPException(
            status_code=403,
            detail=(
                f"{operator['name']}（被访人 · {operator['department']}）无权审批该来访："
                f"受访部门为{entry_before.get('受访部门')}，被访人只能审批自己部门的来访"
            ),
        )

    comment = str(payload.values.get("comment") or "").strip()
    entry, message = service.approve(entry_id, approved, comment, operator)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
