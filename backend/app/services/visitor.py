"""访客登记业务规则：字段校验、部门归属、审批流转都收在这里。

角色拦截放在 routers 层（由依赖统一返回 403），服务层专注业务口径，
例如「受访部门必须存在」「被访人必须归属受访部门」「只有待审批的来访可审批」。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app import directory
from app.directory import ROLE_LABELS
from app.store import store

MODULE = "visitor"
REQUIRED_FIELDS = ["访客姓名", "来访单位", "受访部门", "被访人", "来访事由", "来访日期", "到访时间"]
OPTIONAL_FIELDS = ["联系方式", "证件号"]
STATUS_ORDER = ["待审批", "已批准", "已驳回", "已核销"]


class VisitorService:
    def list_entries(
        self,
        *,
        visit_date: str | None = None,
        dept: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if visit_date:
            rows = [row for row in rows if row.get("来访日期") == visit_date]
        if dept:
            rows = [row for row in rows if row.get("受访部门") == dept]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if keyword:
            rows = [
                row
                for row in rows
                if keyword in str(row.get("访客姓名", ""))
                or keyword in str(row.get("来访编号", ""))
                or keyword in str(row.get("来访单位", ""))
            ]
        # 新登记的排最前面，方便登记后立刻看到
        rows = sorted(rows, key=lambda row: int(row.get("id", 0)), reverse=True)
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def find_by_code(self, code: str) -> dict[str, Any] | None:
        for row in store.rows(MODULE):
            if row.get("来访编号") == code:
                return row
        return None

    def create_entry(
        self,
        values: dict[str, Any],
        operator: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str]:
        cleaned = {field: str(values.get(field) or "").strip() for field in REQUIRED_FIELDS}
        missing = [field for field in REQUIRED_FIELDS if not cleaned[field]]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"

        dept = directory.department(cleaned["受访部门"])
        if dept is None:
            return None, f"受访部门「{cleaned['受访部门']}」不在可受访部门名录内"
        if cleaned["被访人"] != dept["host"]:
            return None, (
                f"被访人「{cleaned['被访人']}」不属于{cleaned['受访部门']}，"
                f"该部门登记的被访人应为{dept['host']}"
            )

        try:
            datetime.strptime(cleaned["来访日期"], "%Y-%m-%d")
        except ValueError:
            return None, "来访日期格式应为 YYYY-MM-DD"
        if cleaned["到访时间"] and not self._valid_time(cleaned["到访时间"]):
            return None, "到访时间格式应为 HH:MM"

        rows = store.rows(MODULE)
        # 同一访客、同一天、同一部门重复登记没有意义
        duplicated = any(
            row.get("访客姓名") == cleaned["访客姓名"]
            and row.get("来访日期") == cleaned["来访日期"]
            and row.get("受访部门") == cleaned["受访部门"]
            and row.get("status") not in ("已驳回",)
            for row in rows
        )
        if duplicated:
            return None, "该访客当天已有一条同一受访部门的有效登记，请勿重复登记"

        entry_id = max((int(row.get("id", 0)) for row in rows), default=0) + 1
        entry: dict[str, Any] = {"id": entry_id, "status": "待审批", "pending": True, "abnormal": False}
        entry["来访编号"] = f"VIS-{entry_id:04d}"
        for field in REQUIRED_FIELDS:
            entry[field] = cleaned[field]
        for field in OPTIONAL_FIELDS:
            entry[field] = str(values.get(field) or "").strip()
        entry["登记人"] = f"{operator['name']}（{ROLE_LABELS[operator['role']]}）"
        entry["登记时间"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry["审批人"] = ""
        entry["审批意见"] = ""
        rows.append(entry)
        return entry, ""

    def approve(
        self,
        entry_id: int,
        approved: bool,
        comment: str,
        operator: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"来访登记 {entry_id} 不存在或已删除"
        # 被访人只能审批本部门的来访
        if entry.get("受访部门") != operator["department"]:
            return None, (
                f"该来访的受访部门是{entry.get('受访部门')}，"
                f"您属于{operator['department']}，只能审批本部门的来访"
            )
        if entry.get("status") != "待审批":
            return None, f"该来访当前为「{entry.get('status')}」状态，不能重复审批"
        entry["status"] = "已批准" if approved else "已驳回"
        entry["pending"] = False
        entry["abnormal"] = not approved
        entry["审批人"] = f"{operator['name']}（{operator['department']}）"
        entry["审批意见"] = comment.strip() or ("同意来访" if approved else "不同意来访")
        action = "批准" if approved else "驳回"
        return entry, f"已{action}{entry['访客姓名']}的来访申请"

    def mark_checked_out(self, visit_code: str) -> None:
        """通行证核销后，联动把来访记录置为已核销。"""
        entry = self.find_by_code(visit_code)
        if entry is not None and entry.get("status") == "已批准":
            entry["status"] = "已核销"
            entry["pending"] = False

    @staticmethod
    def _valid_time(value: str) -> bool:
        try:
            datetime.strptime(value, "%H:%M")
            return True
        except ValueError:
            return False
