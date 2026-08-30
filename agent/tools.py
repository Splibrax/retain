# -*- coding: utf-8 -*-
"""
tools.py — các tool agent gọi được (BLUEPRINT §6).

QUY ƯỚC SỐNG CÒN: không tool nào nhận dept_code / dept_scope từ LLM.
Scope đến từ `actor`, được resolve MỘT LẦN ở entrypoint trước khi LLM tham gia.
Vi phạm quy ước này = lỗ hổng bảo mật, không phải lỗi style.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from . import scoring, store
from .scope import resolve_scope

# Trọng số và công thức KHÔNG còn được chép lại ở đây. Trước đây file này giữ một
# "bản sao chính xác" của engine — và bản sao thì luôn có ngày lệch khỏi bản gốc.
# Giờ dùng chung agent/scoring.py với flight_risk_score.py và generate_facts.py.
WEIGHTS = scoring.WEIGHTS
BAND_VI = scoring.BAND_VI

MAX_LIST = 20          # BLUEPRINT §6 T1 — hard cap, LLM xin nhiều hơn cũng không cho
AUDIT_LOG: list[dict] = []


# ─────────────────────────────────────────────────────────── actor & audit ──
@dataclass(frozen=True)
class Actor:
    actor_id: str
    actor_name: str
    role: str                       # "LM" | "HRBP"
    scope_code: str
    scope: frozenset = field(repr=False, default=frozenset())

    @property
    def sees_money(self) -> bool:
        """BLUEPRINT §5.3b — chỉ HRBP được thấy con số tiền."""
        return self.role == "HRBP"


def build_actor(actor_id: str) -> Actor:
    """Resolve danh tính → scope. Gọi MỘT LẦN ở entrypoint, trước khi LLM chạy."""
    a = store.load_actors().get(actor_id)
    if not a:
        # Danh tính không hợp lệ → actor không thấy gì. Fail closed.
        return Actor(actor_id or "?", "?", "NONE", "", frozenset())
    return Actor(
        actor_id=a["actor_id"],
        actor_name=a["actor_name"],
        role=a["role"],
        scope_code=a["dept_scope_code"],
        scope=resolve_scope(a["dept_scope_code"]),
    )


def _audit(actor: Actor, tool: str, target=None, n_rows=0, denied=False, reason=""):
    aid = uuid.uuid4().hex[:8]
    AUDIT_LOG.append({
        "audit_id": aid, "ts": time.time(),
        "actor_id": actor.actor_id, "actor_role": actor.role,
        "scope_code": actor.scope_code, "tool_called": tool,
        "target_employee_id": target, "n_rows_returned": n_rows,
        "was_denied": denied, "deny_reason": reason,
    })
    return aid


def _deny(actor: Actor, tool: str, target=None, reason="OUT_OF_SCOPE"):
    """
    BLUEPRINT §8 R4 — MỘT thông điệp duy nhất cho mọi trường hợp.
    Không phân biệt "không tồn tại" với "không được xem": phân biệt là rò rỉ.
    """
    return {"error": reason, "audit_id": _audit(actor, tool, target, 0, True, reason)}


def _find(employee_id: str, snapshot: str):
    for r in store.load_scores():
        if r["employee_id"] == employee_id and r["snapshot_date"] == snapshot:
            return r
    return None


# ─────────────────────────────────────────────────────────────── T1 ─────────
def list_team_risk(actor: Actor, as_of: str = "latest",
                   bands=("High", "Medium"), limit: int = 10) -> dict:
    snap = store.latest_snapshot() if as_of == "latest" else as_of
    limit = max(1, min(int(limit), MAX_LIST))

    pool = [r for r in store.rows_for(snap, actor.scope)]
    excluded = sum(1 for r in pool if r["is_excluded_from_risk_list"])
    elig = [r for r in pool
            if not r["is_excluded_from_risk_list"]
            and r["flight_risk_band"] in bands
            and r["flight_risk_score"] is not None]
    elig.sort(key=lambda r: -r["flight_risk_score"])
    top = elig[:limit]

    items = [{
        "employee_id": r["employee_id"],
        "full_name": store.display_name(r["employee_id"]),
        "score": r["flight_risk_score"],
        "band": r["flight_risk_band"],
        "band_vi": BAND_VI.get(r["flight_risk_band"], r["flight_risk_band"]),
        "top_factor": _top_factor_reason(r),
    } for r in top]

    return {
        "snapshot_date": snap,
        "scope_headcount": len(pool),
        "n_flagged": len(elig),
        "n_high": sum(1 for r in elig if r["flight_risk_band"] == "High"),
        "n_medium": sum(1 for r in elig if r["flight_risk_band"] == "Medium"),
        "n_excluded": excluded,
        # Nêu rõ QUY TẮC loại trừ. Thiếu dòng này model sẽ tự bịa lý do
        # ("do dữ liệu không đủ điều kiện") — sai bản chất và mất uy tín với hội đồng.
        "exclusion_rule": ("Bị loại theo quy tắc cứng: có từ 2 thư cảnh cáo trong 12 tháng gần nhất"
                           if excluded else ""),
        "items": items,
        "status": "ok" if items else "no_risk",
        "audit_id": _audit(actor, "list_team_risk", None, len(items)),
    }


def _comps_of(r) -> dict:
    """
    Quy đổi một dòng dữ liệu về các yếu tố rủi ro.

    months_since_last_move có thể KHÔNG tồn tại nếu dữ liệu được sinh bằng bản
    engine cũ — khi đó yếu tố 'promo' vắng mặt và trọng số được chia lại cho bốn
    yếu tố còn lại, đúng cơ chế xử lý thiếu dữ liệu. Agent vẫn chạy, không sập.
    """
    return scoring.components(
        gap_pct=r["salary_gap_to_p50_pct"],
        kpi_score=r["kpi_score"],
        freeze_months=r["pay_freeze_months"],
        seniority_flag=r["seniority_risk_window_flag"],
        months_since_move=r.get("months_since_last_move"),
    )


def _score(comps: dict):
    return scoring.renormalize(comps)


def _band(score):
    return scoring.band(score)


def _top_factor_reason(r) -> str:
    """Yếu tố đóng góp lớn nhất = mức rủi ro × trọng số thực dùng."""
    comps = _comps_of(r)
    _, w = _score(comps)
    top = scoring.top_factor(comps, w)
    return r.get(f"reason_{top}", "") if top else ""


# ─────────────────────────────────────────────────────────────── T2 ─────────
def explain_employee_risk(actor: Actor, employee_id: str, as_of: str = "latest") -> dict:
    snap = store.latest_snapshot() if as_of == "latest" else as_of
    r = _find(employee_id, snap)
    if r is None or r["dept_code"] not in actor.scope:
        return _deny(actor, "explain_employee_risk", employee_id)

    comps = _comps_of(r)
    _, w = _score(comps)
    factors = [{
        "factor": k,
        "factor_vi": scoring.FACTOR_VI[k],
        "risk_value": round(comps[k], 4),
        "weight_used": round(w[k], 4),
        "reason": r.get(f"reason_{k}", ""),
    } for k in scoring.FACTOR_ORDER if k in comps]

    return {
        "employee_id": employee_id,
        "full_name": store.display_name(employee_id),
        "snapshot_date": snap,
        "score": r["flight_risk_score"],
        "band": r["flight_risk_band"],
        "band_vi": BAND_VI.get(r["flight_risk_band"], r["flight_risk_band"]),
        "factors": factors,
        "missing_features": r["missing_features"],
        "is_excluded": r["is_excluded_from_risk_list"],
        "exclusion_reason": r["exclusion_reason"],
        "audit_id": _audit(actor, "explain_employee_risk", employee_id, 1),
    }


# ─────────────────────────────────────────────────────────────── T3 ─────────
def suggest_actions(actor: Actor, employee_id: str, as_of: str = "latest") -> dict:
    """
    BLUEPRINT §6 T3 + §9.3 — playbook P1/P2/P3, tra theo yếu tố trội.
    Nội dung playbook do HRBP viết (data/playbook.csv), KHÔNG do LLM nghĩ ra.
    """
    snap = store.latest_snapshot() if as_of == "latest" else as_of
    r = _find(employee_id, snap)
    if r is None or r["dept_code"] not in actor.scope:
        return _deny(actor, "suggest_actions", employee_id)

    if r["is_excluded_from_risk_list"]:
        return {
            "status": "EXCLUDED",
            "reason": r["exclusion_reason"],
            "employee_id": employee_id,
            "message": ("Nhân sự này bị loại khỏi danh sách giữ chân theo quy tắc "
                        "≥2 thư cảnh cáo trong 12 tháng. Không đưa ra khuyến nghị giữ chân."),
            "audit_id": _audit(actor, "suggest_actions", employee_id, 0, True, "EXCLUDED"),
        }

    comps = _comps_of(r)
    _, w = _score(comps)
    top = scoring.top_factor(comps, w)

    pb = store.load_playbook()
    plays = pb.get(top, {})
    return {
        "employee_id": employee_id,
        "full_name": store.display_name(employee_id),
        # snapshot_date BẮT BUỘC có: mọi câu trả lời đều dẫn kỳ dữ liệu, thiếu nó
        # thì guard coi ngày tháng là số bịa và bắt viết lại (tốn gấp đôi token).
        "snapshot_date": snap,
        "score": r["flight_risk_score"],
        "band": r["flight_risk_band"],
        "band_vi": BAND_VI.get(r["flight_risk_band"], r["flight_risk_band"]),
        "top_factor": top,
        "top_factor_reason": r.get(f"reason_{top}", ""),
        "P1": plays.get("P1", ""),
        "P2": plays.get("P2", ""),
        "P3": plays.get("P3", ""),
        "playbook_is_draft": store.playbook_is_draft(),
        "audit_id": _audit(actor, "suggest_actions", employee_id, 1),
    }


# ─────────────────────────────────────────────────────────────── T6 ─────────
class ScenarioError(ValueError):
    pass


def simulate_intervention(actor: Actor, employee_id: str, scenario: str,
                          value: float | None = None, as_of: str = "latest") -> dict:
    """
    BLUEPRINT §6 T6 — chạy lại ĐÚNG hàm chấm điểm với đầu vào giả định.
    Không mô hình mới, không ước lượng. Cùng giả định → luôn cùng kết quả.
    """
    snap = store.latest_snapshot() if as_of == "latest" else as_of
    r = _find(employee_id, snap)
    if r is None or r["dept_code"] not in actor.scope:
        return _deny(actor, "simulate_intervention", employee_id)

    if r["is_excluded_from_risk_list"]:
        return {"status": "EXCLUDED", "reason": r["exclusion_reason"],
                "employee_id": employee_id,
                "audit_id": _audit(actor, "simulate_intervention", employee_id, 0,
                                   True, "EXCLUDED")}

    gap, kpi = r["salary_gap_to_p50_pct"], r["kpi_score"]
    freeze, sen = r["pay_freeze_months"], r["seniority_risk_window_flag"]
    move = r.get("months_since_last_move")
    salary_lever = None      # to_p50: đòn bẩy lương còn dùng được hay đã cạn

    if scenario == "raise_pct":
        if value is None:
            raise ScenarioError("raise_pct cần value, ví dụ 0.10 cho 10%")
        # R-riêng T6: giảm lương không phải công cụ giữ người
        if value <= 0:
            raise ScenarioError("Chỉ mô phỏng tăng lương (value > 0)")
        if value > 0.5:
            raise ScenarioError("Ngoài dải hợp lý (tối đa 50%)")
        if gap is None:
            raise ScenarioError("Thiếu dữ liệu lương, không mô phỏng được")
        gap = (1 + gap) * (1 + value) - 1
        freeze = 0
        label = f"Tăng lương {value*100:.0f}%"

    elif scenario == "to_p50":
        if gap is None:
            raise ScenarioError("Thiếu dữ liệu lương, không mô phỏng được")
        if gap >= 0:
            # Người này đã ở trên P50 — KHÔNG có khoảng cách nào để đóng.
            #
            # Bản trước đặt thẳng gap = 0, nghĩa là mô phỏng GIẢM lương người ta
            # về đúng trung vị rồi gọi đó là phương án giữ chân. Điểm vẫn giảm
            # (vì chuỗi đóng băng bị phá) nên nhìn qua tưởng hợp lý. Đó là loại
            # lỗi mà hội đồng bắt được là hỏng cả bài.
            #
            # Không có hành động lương nào xảy ra ⇒ chuỗi đóng băng cũng không
            # được phá ⇒ điểm không đổi. Đúng bản chất: đòn bẩy này đã cạn.
            salary_lever = False
            label = "Đưa lương về P50 — không áp dụng được, người này đã ở trên P50"
        else:
            gap, freeze = 0.0, 0
            salary_lever = True
            label = "Đưa lương về đúng P50 thị trường"

    elif scenario == "kpi_recovery":
        if value is None:
            raise ScenarioError("kpi_recovery cần value là điểm KPI mục tiêu")
        if not (0 <= value <= 100):
            raise ScenarioError("Điểm KPI mục tiêu phải trong 0–100")
        kpi = float(value)
        label = f"KPI phục hồi lên {value:.0f}/100"

    elif scenario == "promotion":
        # Đổi vai / thăng cấp: đồng hồ "chưa được đổi vai" về 0.
        # Đây là phương án KHÔNG tốn ngân sách lương, và với người đã được trả
        # trên P50 thì thường là phương án duy nhất còn tác dụng.
        if move is None:
            raise ScenarioError("Thiếu dữ liệu lịch sử đổi vai, không mô phỏng được")
        move = 0
        label = "Đổi vai / thăng cấp trong kỳ tới"

    else:
        raise ScenarioError(f"Kịch bản không hợp lệ: {scenario}")

    new_comps = scoring.components(gap, kpi, freeze, sen, move)
    new_score, _ = _score(new_comps)
    old_score = r["flight_risk_score"]

    old_comps = _comps_of(r)
    _, ow = _score(old_comps)
    contrib = {}
    for k in old_comps:
        before = 100 * ow.get(k, 0) * old_comps[k]
        after = 100 * ow.get(k, 0) * new_comps.get(k, old_comps[k])
        if round(before - after, 2) != 0:
            contrib[k] = round(before - after, 2)

    return {
        "employee_id": employee_id,
        "full_name": store.display_name(employee_id),
        "snapshot_date": snap,
        "scenario": scenario,
        "scenario_label": label,
        "score_before": old_score,
        "score_after": new_score,
        "score_delta": round(old_score - new_score, 2),
        "band_before": r["flight_risk_band"],
        "band_before_vi": BAND_VI.get(r["flight_risk_band"], r["flight_risk_band"]),
        "band_after": _band(new_score),
        "band_after_vi": BAND_VI.get(_band(new_score), ""),
        "delta_by_factor": contrib,
        # Với to_p50: False nghĩa là người này đã ở trên P50, tiền không còn là
        # đòn bẩy — đây chính là con số HRBP cần trước khi duyệt ngân sách giữ người.
        "salary_lever_available": salary_lever,
        "cost_mil_vnd": estimate_cost(actor, employee_id, scenario, value),
        "is_deterministic": True,
        # BLUEPRINT §8 R9 — nhãn cứng, không phụ thuộc LLM tự nhớ
        "disclaimer": ("Kết quả tính lại theo giả định, KHÔNG phải dự báo người này sẽ ở lại. "
                       "Điểm thấp hơn nghĩa là các yếu tố quan sát được đã cải thiện."),
        "audit_id": _audit(actor, "simulate_intervention", employee_id, 1),
    }


def estimate_cost(actor: Actor, employee_id: str, scenario: str, value=None):
    """
    Chi phí phương án, triệu đồng/năm.
    BLUEPRINT §5.3b: chỉ HRBP thấy tiền; và KỂ CẢ HRBP cũng không bao giờ
    thấy lương tuyệt đối — chỉ thấy chi phí của một phương án cụ thể.

    TODO(29/8): cần fact_salary_snapshot + dim_market_benchmark để tính thật.
    Chưa có thì trả None — KHÔNG đoán, không trả số giả.
    """
    if not actor.sees_money:
        return None
    return None
