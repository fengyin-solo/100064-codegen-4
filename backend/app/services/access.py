"""门禁通行业务规则：通行证受控发放、有效期校验、刷卡判定与幂等核销。

受控口径：
- 只给「已批准、来访日当天、尚无未核销通行证」的来访发放；
- 通行证有效期不得跨日，最长到来访当日 23:59；
- 已过期/已核销/未生效的通行证刷卡一律拒绝；
- 同一通行证重复核销只生效一次，但不报错，便于前台/门禁重复点击。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.directory import ROLE_LABELS
from app.services.visitor import VisitorService
from app.store import store

PASS_MODULE = "pass"
LOG_MODULE = "access_log"
TIME_FMT = "%Y-%m-%d %H:%M"


class AccessService:
    def __init__(self) -> None:
        self.visitors = VisitorService()

    # ---------- 查询 ----------

    def list_passes(
        self,
        *,
        status: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [self._decorate(dict(row)) for row in store.rows(PASS_MODULE)]
        if status:
            rows = [row for row in rows if row["通行证状态"] == status]
        if keyword:
            rows = [
                row
                for row in rows
                if keyword in str(row.get("通行证号", "")) or keyword in str(row.get("访客姓名", ""))
            ]
        rows.sort(key=lambda row: int(row.get("id", 0)), reverse=True)
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def issuable_visits(self, visit_date: str | None = None) -> list[dict[str, Any]]:
        """可发放通行证的来访：已批准、指定日期、且没有未核销通行证。"""
        target_date = visit_date or datetime.now().strftime("%Y-%m-%d")
        visits, _ = self.visitors.list_entries(visit_date=target_date, status="已批准", size=1000)
        active_codes = {
            row["来访编号"] for row in store.rows(PASS_MODULE) if not row.get("核销时间")
        }
        return [row for row in visits if row["来访编号"] not in active_codes]

    def list_logs(self, *, keyword: str | None = None, size: int = 30) -> list[dict[str, Any]]:
        rows = list(store.rows(LOG_MODULE))
        if keyword:
            rows = [
                row
                for row in rows
                if keyword in str(row.get("通行证号", "")) or keyword in str(row.get("访客姓名", ""))
            ]
        rows.sort(key=lambda row: int(row.get("id", 0)), reverse=True)
        return rows[:size]

    def get_pass(self, code: str) -> dict[str, Any] | None:
        for row in store.rows(PASS_MODULE):
            if row.get("通行证号") == code:
                return self._decorate(dict(row))
        return None

    # ---------- 发放 ----------

    def issue_pass(
        self,
        visit_id: int,
        valid_from: str,
        valid_until: str,
        point: str,
        operator: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str]:
        visit = self.visitors.get_entry(visit_id)
        if visit is None:
            return None, f"来访登记 {visit_id} 不存在或已删除"
        if visit.get("status") != "已批准":
            return None, f"该来访为「{visit.get('status')}」状态，只有已批准的来访才能发放通行证"

        today = datetime.now().strftime("%Y-%m-%d")
        if visit.get("来访日期") != today:
            return None, "只能在来访当天发放通行证，非当日来访请先核对来访日期"

        for row in store.rows(PASS_MODULE):
            if row.get("来访编号") == visit.get("来访编号") and not row.get("核销时间"):
                return None, f"该来访已有一张未核销通行证 {row.get('通行证号')}，不得重复发放"

        try:
            start = datetime.strptime(valid_from, TIME_FMT)
            end = datetime.strptime(valid_until, TIME_FMT)
        except ValueError:
            return None, "有效期时间格式应为 YYYY-MM-DD HH:MM"

        now = datetime.now().replace(second=0, microsecond=0)
        if start >= end:
            return None, "有效开始时间必须早于有效截止时间"
        if end <= now:
            return None, "截止时间早于当前时间，发放即过期的通行证不允许发放"
        # 受控：不允许跨日发放，最长到来访当日 23:59
        latest_end = datetime.strptime(f"{today} 23:59", TIME_FMT)
        if start.strftime("%Y-%m-%d") != today or end.strftime("%Y-%m-%d") != today:
            return None, "通行证有效期仅限来访当日，不允许跨日发放"
        if end > latest_end:
            return None, "通行证有效截止不得超过来访当日 23:59"

        rows = store.rows(PASS_MODULE)
        pass_id = max((int(row.get("id", 0)) for row in rows), default=0) + 1
        entry = {
            "id": pass_id,
            "status": "通行中",
            "pending": True,
            "abnormal": False,
            "通行证号": f"PASS-{pass_id:04d}",
            "来访编号": visit["来访编号"],
            "访客姓名": visit["访客姓名"],
            "受访部门": visit["受访部门"],
            "门禁点": (point or "东门访客通道").strip(),
            "发证时间": now.strftime(TIME_FMT),
            "有效开始": start.strftime(TIME_FMT),
            "有效截止": end.strftime(TIME_FMT),
            "核销时间": "",
            "核销人": "",
        }
        rows.append(entry)
        self._write_log(entry, "放行", "通行证已发放，首次授权", allowed=True)
        return self._decorate(dict(entry)), f"通行证 {entry['通行证号']} 已发放，有效期至 {entry['有效截止']}"

    # ---------- 核销（幂等） ----------

    def checkout_pass(
        self,
        code: str,
        operator: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str, bool]:
        """返回 (通行证, 说明, 是否已处于核销状态)。重复核销只算一次。"""
        entry = None
        for row in store.rows(PASS_MODULE):
            if row.get("通行证号") == code:
                entry = row
                break
        if entry is None:
            return None, f"通行证 {code} 不存在，请核对通行证号", False
        if entry.get("核销时间"):
            # 幂等：不重复核销、不重复联动，直接回执
            return self._decorate(dict(entry)), f"通行证 {code} 已在 {entry['核销时间']} 核销，重复核销只计一次", True

        moment = datetime.now().strftime(TIME_FMT)
        entry["核销时间"] = moment
        entry["核销人"] = f"{operator['name']}（{ROLE_LABELS[operator['role']]}）"
        entry["status"] = "已核销"
        entry["pending"] = False
        entry["abnormal"] = False
        self.visitors.mark_checked_out(str(entry.get("来访编号", "")))
        self._write_log(entry, "核销", f"访客离开，{entry['核销人']}核销通行证", allowed=True)
        return self._decorate(dict(entry)), f"通行证 {code} 已核销，访客离开登记完成", False

    # ---------- 刷卡 ----------

    def swipe(self, code: str, point: str) -> dict[str, Any]:
        entry = None
        for row in store.rows(PASS_MODULE):
            if row.get("通行证号") == code:
                entry = row
                break

        def deny(reason: str, snapshot: dict[str, Any] | None) -> dict[str, Any]:
            log_row = self._write_log(snapshot, "拒绝", reason, allowed=False, point=point)
            return {"allowed": False, "message": reason, "log": log_row}

        if entry is None:
            # 号码不存在也要把所刷号码记入异常日志，便于排查冒用
            return deny(f"通行证 {code} 不存在或号码有误，门禁保持关闭", {"通行证号": code})

        now = datetime.now().replace(second=0, microsecond=0)
        if entry.get("核销时间"):
            return deny(f"通行证 {code} 已于 {entry['核销时间']} 核销，访客已离开，禁止再刷门禁", entry)
        try:
            start = datetime.strptime(str(entry["有效开始"]), TIME_FMT)
            end = datetime.strptime(str(entry["有效截止"]), TIME_FMT)
        except ValueError:
            return deny(f"通行证 {code} 的有效期数据异常，请联系门禁管理员", entry)
        if now < start:
            return deny(f"通行证 {code} 尚未到生效时间（{entry['有效开始']}），门禁暂不开放", entry)
        if now > end:
            return deny(f"通行证 {code} 已超过有效截止时间 {entry['有效截止']}，门禁已关闭", entry)

        reason = f"通行证在有效期内（至 {entry['有效截止']}），{point or entry.get('门禁点')} 放行"
        log_row = self._write_log(entry, "放行", reason, allowed=True, point=point)
        return {"allowed": True, "message": reason, "log": log_row}

    # ---------- 内部工具 ----------

    def _write_log(
        self,
        pass_row: dict[str, Any] | None,
        result: str,
        reason: str,
        *,
        allowed: bool,
        point: str | None = None,
    ) -> dict[str, Any]:
        logs = store.rows(LOG_MODULE)
        log_id = max((int(row.get("id", 0)) for row in logs), default=0) + 1
        log_entry = {
            "id": log_id,
            "status": "正常" if allowed else "异常",
            "pending": False,
            "abnormal": not allowed,
            "通行证号": (pass_row or {}).get("通行证号", ""),
            "访客姓名": (pass_row or {}).get("访客姓名", ""),
            "门禁点": point or (pass_row or {}).get("门禁点") or "东门访客通道",
            "刷卡时间": datetime.now().strftime(TIME_FMT),
            "结果": result,
            "说明": reason,
        }
        logs.append(log_entry)
        return log_entry

    def _decorate(self, row: dict[str, Any]) -> dict[str, Any]:
        """在不改动存储字段的前提下，补一个按当前时刻计算的通行状态。"""
        if row.get("核销时间"):
            row["通行证状态"] = "已核销"
        else:
            try:
                now = datetime.now().replace(second=0, microsecond=0)
                start = datetime.strptime(str(row["有效开始"]), TIME_FMT)
                end = datetime.strptime(str(row["有效截止"]), TIME_FMT)
                if now < start:
                    row["通行证状态"] = "未生效"
                elif now > end:
                    row["通行证状态"] = "已过期"
                else:
                    row["通行证状态"] = "通行中"
            except (KeyError, ValueError):
                row["通行证状态"] = row.get("status", "未知")
        return row
