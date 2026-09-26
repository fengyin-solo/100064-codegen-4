"""访客登记与门禁通行业务规则。

角色口径（越权一律拒绝并说明原因）：
- 前台：只能做访客登记，不能审批、发证、核销；
- 被访人：只能审批受访部门与自己所属部门一致的来访，不能登记、发证、核销；
- 门禁管理员：发放通行证受控（只能对已批准来访发证、有效期受控、一人一证），
  负责刷门禁与离开核销。

通行证有效期结束后不能再刷门禁；对同一张通行证重复核销只算一次（幂等）。
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from app.errors import PermissionDenied, VisitorError
from app.store import store

VISITOR_MODULE = "visitor"
PASS_MODULE = "visitor_pass"
LOG_MODULE = "visitor_access_log"

ROLE_RECEPTION = "前台"
ROLE_HOST = "被访人"
ROLE_GUARD = "门禁管理员"
ROLE_ALIASES = {
    "前台": ROLE_RECEPTION,
    "reception": ROLE_RECEPTION,
    "receptionist": ROLE_RECEPTION,
    "被访人": ROLE_HOST,
    "host": ROLE_HOST,
    "interviewee": ROLE_HOST,
    "门禁管理员": ROLE_GUARD,
    "guard": ROLE_GUARD,
    "access_admin": ROLE_GUARD,
}

DEPARTMENTS = ["综合办公室", "检测一部", "检测二部", "质量管理部", "设备保障部"]

REQUIRED_FIELDS = ["访客姓名", "受访部门", "来访事由"]
VISIT_STATUS = ["待审批", "已批准", "已拒绝"]
PASS_STATUS_LABEL = ["通行中", "已过期", "已核销", "未生效"]

# 受控发放口径：通行证有效期最短 5 分钟、最长 24 小时。
MIN_VALIDITY = timedelta(minutes=5)
MAX_VALIDITY = timedelta(hours=24)
# 来访当日的允许通行截止时间。
DAY_END = time(23, 59, 59)


def now() -> datetime:
    """单独包一层：测试或联调时可以从这里统一接管当前时间。"""
    return datetime.now()


def parse_dt(value: Any, field_label: str = "时间") -> datetime | None:
    """把前端 datetime-local/ISO 字符串解析成 datetime，非法值给出可读说明。"""
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        raise VisitorError(f"{field_label}格式无法识别，请使用类似 2026-09-26 14:00 的写法") from None


class VisitorService:
    # ---- 身份与权限 -------------------------------------------------------

    def resolve_role(self, role: str | None) -> str:
        normalized = ROLE_ALIASES.get(str(role or "").strip())
        if normalized is None:
            raise VisitorError("未能识别当前操作角色，请先在页面右上角切换角色", status_code=401)
        return normalized

    def _require_role(self, role: str | None, expected: str, action_desc: str) -> str:
        current = self.resolve_role(role)
        if current != expected:
            raise PermissionDenied(f"越权操作被拒绝：{action_desc}仅限「{expected}」，当前角色为「{current}」")
        return current

    # ---- 访客登记 ---------------------------------------------------------

    def list_visitors(
        self,
        *,
        visit_date: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(VISITOR_MODULE)
        if visit_date:
            rows = [row for row in rows if str(row.get("来访日期", "")) == visit_date]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("访客姓名", "")) or keyword in str(row.get("访客单位", ""))]
        # 最新登记的排在最前。
        rows = sorted(rows, key=lambda row: int(row.get("id", 0)), reverse=True)
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self._with_pass(row) for row in rows[start:start + size]], total

    def get_visitor(self, visitor_id: int) -> dict[str, Any]:
        row = store.find(VISITOR_MODULE, visitor_id)
        if row is None:
            raise VisitorError(f"访客登记 {visitor_id} 不存在或已删除", status_code=404)
        return self._with_pass(row)

    def register(self, values: dict[str, Any], role: str | None) -> dict[str, Any]:
        self._require_role(role, ROLE_RECEPTION, "访客登记")
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            raise VisitorError(f"缺少必填信息：{'、'.join(missing)}")
        department = str(values["受访部门"]).strip()
        if department not in DEPARTMENTS:
            raise VisitorError(f"受访部门「{department}」不在在册部门列表中")

        visit_date_raw = str(values.get("来访日期") or "").strip()
        visit_date = date.today().isoformat()
        if visit_date_raw:
            try:
                visit_date = date.fromisoformat(visit_date_raw).isoformat()
            except ValueError:
                raise VisitorError("来访日期格式无法识别，请使用 2026-09-26 这样的写法") from None

        rows = store.rows(VISITOR_MODULE)
        visitor = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "访客编号": self._next_code(rows),
            "访客姓名": str(values["访客姓名"]).strip(),
            "访客单位": str(values.get("访客单位") or "").strip(),
            "联系电话": str(values.get("联系电话") or "").strip(),
            "受访部门": department,
            "被访人": str(values.get("被访人") or "").strip(),
            "来访事由": str(values["来访事由"]).strip(),
            "来访日期": visit_date,
            "登记人": str(values.get("登记人") or "").strip() or ROLE_RECEPTION,
            "审批意见": "",
            "status": VISIT_STATUS[0],
            "pending": True,
            "abnormal": False,
        }
        rows.append(visitor)
        return self._with_pass(visitor)

    def approve(
        self,
        visitor_id: int,
        action: str,
        values: dict[str, Any],
        role: str | None,
        department: str | None,
    ) -> dict[str, Any]:
        current = self._require_role(role, ROLE_HOST, "来访审批")
        visitor = store.find(VISITOR_MODULE, visitor_id)
        if visitor is None:
            raise VisitorError(f"访客登记 {visitor_id} 不存在或已删除", status_code=404)

        own_department = str(department or "").strip()
        if not own_department:
            raise PermissionDenied("当前被访人账号未配置所属部门，无法审批任何来访")
        if visitor["受访部门"] != own_department:
            raise PermissionDenied(
                f"越权操作被拒绝：该来访归属「{visitor['受访部门']}」，"
                f"您所属部门为「{own_department}」，只能审批本部门来访"
            )
        if visitor["status"] != VISIT_STATUS[0]:
            raise VisitorError(f"该来访当前状态为「{visitor['status']}」，无需重复审批")

        if action == "批准来访":
            target = VISIT_STATUS[1]
            abnormal = False
        elif action == "拒绝来访":
            target = VISIT_STATUS[2]
            abnormal = True
        else:
            raise VisitorError(f"动作「{action}」不属于来访审批范围，只能批准或拒绝")

        opinion = str(values.get("审批意见") or "").strip()
        if action == "拒绝来访" and not opinion:
            raise VisitorError("拒绝来访必须填写审批意见，向前台与访客说明原因")
        visitor["status"] = target
        visitor["审批意见"] = opinion or (f"{current}批准" if action == "批准来访" else opinion)
        visitor["pending"] = False
        visitor["abnormal"] = abnormal
        return self._with_pass(visitor)

    # ---- 通行证发放 -------------------------------------------------------

    def list_passes(self, *, only_active: bool = False) -> list[dict[str, Any]]:
        passes = [self._pass_view(row) for row in store.rows(PASS_MODULE)]
        passes.sort(key=lambda item: int(item["id"]), reverse=True)
        if only_active:
            passes = [item for item in passes if item["通行证状态"] == PASS_STATUS_LABEL[0]]
        return passes

    def issue(
        self,
        visitor_id: int,
        values: dict[str, Any],
        role: str | None,
    ) -> dict[str, Any]:
        self._require_role(role, ROLE_GUARD, "通行证发放")
        visitor = store.find(VISITOR_MODULE, visitor_id)
        if visitor is None:
            raise VisitorError(f"访客登记 {visitor_id} 不存在或已删除", status_code=404)

        # 受控发放：只有已批准来访可以发证。
        if visitor["status"] == VISIT_STATUS[0]:
            raise VisitorError("来访尚未审批通过，门禁管理员不能提前发放通行证")
        if visitor["status"] == VISIT_STATUS[2]:
            raise VisitorError("来访已被拒绝，不得发放通行证")

        # 一人一证：仍持有未核销通行证的，不能重复发放（过期证自动失效、可补开新证）。
        existing = self._active_pass(visitor_id)
        if existing is not None:
            raise VisitorError(
                f"该访客已持有通行证 {existing['通行证编号']}（{self._pass_view(existing)['通行证状态']}），"
                "请先核销后再发放新证"
            )

        visit_day = date.fromisoformat(str(visitor["来访日期"]))
        current = now()
        valid_from = parse_dt(values.get("生效时间"), "通行证生效时间") or current
        valid_to = parse_dt(values.get("失效时间"), "通行证失效时间")
        if valid_to is None:
            valid_to = datetime.combine(visit_day, DAY_END)
        valid_to = valid_to.replace(microsecond=0)
        valid_from = valid_from.replace(microsecond=0)

        # 受控口径：有效期必须落在来访当日，且时长在 5 分钟到 24 小时之间。
        if valid_from.date() != visit_day:
            raise VisitorError("通行证生效时间必须在来访当日")
        if valid_to.date() != visit_day:
            raise VisitorError("通行证失效时间必须在来访当日")
        if valid_to <= valid_from:
            raise VisitorError("通行证失效时间必须晚于生效时间")
        duration = valid_to - valid_from
        if duration < MIN_VALIDITY:
            raise VisitorError("受控发放被拒绝：通行证有效期不得短于 5 分钟")
        if duration > MAX_VALIDITY:
            raise VisitorError("受控发放被拒绝：通行证有效期不得超过 24 小时")

        rows = store.rows(PASS_MODULE)
        pass_row = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "通行证编号": self._next_pass_code(rows),
            "访客登记ID": visitor_id,
            "访客姓名": visitor["访客姓名"],
            "受访部门": visitor["受访部门"],
            "来访日期": visitor["来访日期"],
            "生效时间": valid_from.isoformat(),
            "失效时间": valid_to.isoformat(),
            "发放人": str(values.get("发放人") or "").strip() or ROLE_GUARD,
            "核销时间": "",
            "核销人": "",
        }
        rows.append(pass_row)
        return self._pass_view(pass_row)

    def checkout(self, pass_id: int, role: str | None) -> dict[str, Any]:
        self._require_role(role, ROLE_GUARD, "通行证核销")
        pass_row = self._get_pass(pass_id)
        # 重复核销只算一次：不重复改写数据、不重复记录，明确提示已经核销过。
        if pass_row.get("核销时间"):
            pass_row["_checkout_idempotent"] = True
            view = self._pass_view(pass_row)
            view["提示"] = f"通行证已于 {pass_row['核销时间']} 核销，重复核销只计一次"
            return view
        stamp = now().replace(microsecond=0).isoformat()
        pass_row["核销时间"] = stamp
        pass_row["核销人"] = ROLE_GUARD
        view = self._pass_view(pass_row)
        view["提示"] = "访客离开，通行证已核销"
        return view

    # ---- 门禁刷卡 ---------------------------------------------------------

    def swipe(self, pass_code: str, values: dict[str, Any], role: str | None = None) -> dict[str, Any]:
        """刷门禁：非门禁管理员可刷卡通行（访客凭证由闸机读取），但发卡、核销仍受控。

        这里对 role 不做强约束——门禁设备/前台代刷都是常见场景；越权口径在发证与核销上把关。
        """
        code = str(pass_code or values.get("通行证编号") or "").strip()
        if not code:
            raise VisitorError("未读取到通行证编号，请重新刷卡")
        pass_row = self._find_pass_by_code(code)
        view = self._pass_view(pass_row)
        current = now().replace(microsecond=0)
        allowed = False
        reason = ""
        if pass_row.get("核销时间"):
            reason = "通行证已核销，访客已离开，不能继续刷门禁"
        else:
            valid_from = datetime.fromisoformat(pass_row["生效时间"])
            valid_to = datetime.fromisoformat(pass_row["失效时间"])
            if current < valid_from:
                reason = f"通行证尚未生效（生效时间 {pass_row['生效时间']}）"
            elif current > valid_to:
                reason = f"通行证有效期已于 {pass_row['失效时间']} 结束，不能继续刷门禁"
            else:
                allowed = True
                reason = "验证通过，门禁放行"

        logs = store.rows(LOG_MODULE)
        log_row = {
            "id": max((int(row.get("id", 0)) for row in logs), default=0) + 1,
            "通行证编号": code,
            "访客姓名": pass_row["访客姓名"],
            "刷卡时间": current.isoformat(),
            "结果": "放行" if allowed else "拒绝",
            "原因": reason,
        }
        logs.append(log_row)
        return {
            "ok": allowed,
            "message": reason,
            "通行证": view,
            "日志": log_row,
        }

    def list_logs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        logs = sorted(store.rows(LOG_MODULE), key=lambda row: int(row.get("id", 0)), reverse=True)
        return logs[:limit]

    # ---- 视图拼装 ---------------------------------------------------------

    def _with_pass(self, visitor: dict[str, Any]) -> dict[str, Any]:
        """给访客行挂上当前通行证的可发放状态，供列表与门禁页保持同一口径。"""
        view = dict(visitor)
        active = self._active_pass(int(visitor["id"]))
        if active is not None:
            pass_view = self._pass_view(active)
            view["通行证编号"] = active["通行证编号"]
            view["通行证状态"] = pass_view["通行证状态"]
            view["可发放通行证"] = False
            view["发放说明"] = f"已有通行证 {active['通行证编号']}（{pass_view['通行证状态']}）"
        else:
            view["通行证编号"] = ""
            if visitor["status"] != VISIT_STATUS[1]:
                view["通行证状态"] = ""
                view["可发放通行证"] = False
                view["发放说明"] = (
                    "来访已拒绝，不予发证" if visitor["status"] == VISIT_STATUS[2]
                    else "来访待审批，审批通过后才可发证"
                )
                return view
            latest = self._latest_pass(int(visitor["id"]))
            if latest is None:
                view["通行证状态"] = ""
                view["可发放通行证"] = True
                view["发放说明"] = "来访已批准，可发放通行证"
            elif latest.get("核销时间"):
                view["通行证编号"] = latest["通行证编号"]
                view["通行证状态"] = PASS_STATUS_LABEL[2]
                view["可发放通行证"] = False
                view["发放说明"] = "通行证已核销，访客已离开"
            else:
                latest_view = self._pass_view(latest)
                view["通行证编号"] = latest["通行证编号"]
                view["通行证状态"] = latest_view["通行证状态"]
                view["可发放通行证"] = True
                view["发放说明"] = "原通行证已过期，可补开新证"
        return view

    def _pass_view(self, pass_row: dict[str, Any]) -> dict[str, Any]:
        view = dict(pass_row)
        view.pop("_checkout_idempotent", None)
        if pass_row.get("核销时间"):
            label = PASS_STATUS_LABEL[2]
        elif now() > datetime.fromisoformat(pass_row["失效时间"]):
            label = PASS_STATUS_LABEL[1]
        elif now() < datetime.fromisoformat(pass_row["生效时间"]):
            label = PASS_STATUS_LABEL[3]
        else:
            label = PASS_STATUS_LABEL[0]
        view["通行证状态"] = label
        view["可核销"] = not bool(pass_row.get("核销时间"))
        return view

    def _active_pass(self, visitor_id: int) -> dict[str, Any] | None:
        """返回访客名下仍占用发证名额的通行证：未核销，且当前未到失效时间。

        未生效的证也占名额（已预约发放）；已过期未核销的证不占名额，可补开新证。
        """
        for row in store.rows(PASS_MODULE):
            if int(row.get("访客登记ID", 0)) != visitor_id:
                continue
            if row.get("核销时间"):
                continue
            if now() > datetime.fromisoformat(row["失效时间"]):
                continue
            return row
        return None

    def _latest_pass(self, visitor_id: int) -> dict[str, Any] | None:
        matches = [
            row for row in store.rows(PASS_MODULE)
            if int(row.get("访客登记ID", 0)) == visitor_id
        ]
        return max(matches, key=lambda row: int(row.get("id", 0)), default=None)

    def _get_pass(self, pass_id: int) -> dict[str, Any]:
        row = store.find(PASS_MODULE, pass_id)
        if row is None:
            raise VisitorError(f"通行证 {pass_id} 不存在", status_code=404)
        return row

    def _find_pass_by_code(self, code: str) -> dict[str, Any]:
        for row in store.rows(PASS_MODULE):
            if str(row.get("通行证编号", "")) == code:
                return row
        raise VisitorError(f"通行证编号 {code} 不存在或为伪造凭证", status_code=404)

    def _next_code(self, rows: list[dict[str, Any]]) -> str:
        return f"VIS-{date.today().isoformat().replace('-', '')}-{len(rows) + 1:03d}"

    def _next_pass_code(self, rows: list[dict[str, Any]]) -> str:
        return f"PASS-{len(rows) + 1:04d}"


visitor_service = VisitorService()
