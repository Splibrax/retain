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
DEFAULT_LIMIT = 5      # số dòng mặc định của list_team_risk (xem docstring bên dưới)
AUDIT_LOG: list[dict] = []

# ── Lọc và sắp xếp cho list_team_risk ───────────────────────────────────────
# Người dùng gọi mức bằng tiếng Việt ("Cao"), dữ liệu lưu tiếng Anh ("High").
# Ngưỡng KHÔNG nằm ở đây: mức của mỗi dòng đã được scoring.band() ghi sẵn vào
# flight_risk_band (66 / 38), tool chỉ đọc lại — không tự tính lại ngưỡng.
BAND_INPUT = {"Cao": "High", "Trung bình": "Medium", "Thấp": "Low"}

# sort_by → cột dữ liệu, chiều sắp, cách gọi thứ tự, đơn vị của sort_value.
# desc=True: giá trị LỚN lên đầu. Với lương và KPI thì "xấu" là giá trị NHỎ, nên desc=False.
_SORTS = {
    "score":      dict(col="flight_risk_score", desc=True,
                       order_vi="điểm rủi ro cao nhất lên đầu", unit="điểm/100"),
    "salary_gap": dict(col="salary_gap_to_p50_pct", desc=False,
                       order_vi="thấp hơn P50 thị trường nhiều nhất lên đầu",
                       unit="% so với P50 (âm = thấp hơn P50)"),
    "kpi":        dict(col="kpi_score", desc=False,
                       order_vi="điểm KPI thấp nhất lên đầu", unit="điểm KPI/100"),
    "freeze":     dict(col="pay_freeze_months", desc=True,
                       order_vi="bị dừng xét điều chỉnh lương lâu nhất lên đầu", unit="tháng"),
    "promo":      dict(col="months_since_last_move", desc=True,
                       order_vi="lâu chưa điều chuyển/bổ nhiệm nhất lên đầu", unit="tháng"),
    "tenure":     dict(col="tenure_months", desc=True,
                       order_vi="thâm niên dài nhất lên đầu", unit="tháng"),
}
SORT_FIELDS = tuple(_SORTS)

# Câu lý do đã được pipeline tính sẵn trong CSV — dùng lại đúng chữ đó làm
# sort_value_text, không tự nghĩ câu mới (thâm niên không có cột lý do riêng).
_SORT_REASON_COL = {"salary_gap": "reason_salary", "kpi": "reason_kpi",
                    "freeze": "reason_freeze", "promo": "reason_promo"}


class InvalidParam(ValueError):
    """Tham số ngoài danh sách cho phép. registry.dispatch đổi thành INVALID_PARAM."""


def _parse_band(band):
    """None = không lọc. Giá trị lạ thì báo lỗi rõ ràng, KHÔNG đoán ý."""
    if band is None:
        return None
    if not isinstance(band, str) or band not in BAND_INPUT:
        raise InvalidParam(
            f"band = {band!r} không hợp lệ. Chỉ nhận đúng: {' / '.join(BAND_INPUT)}. "
            "Bỏ trống band để dùng mặc định (Cao + Trung bình).")
    return BAND_INPUT[band]


def _parse_sort(sort_by):
    if sort_by is None:
        return None
    if not isinstance(sort_by, str) or sort_by not in _SORTS:
        raise InvalidParam(
            f"sort_by = {sort_by!r} không hợp lệ. Chỉ nhận đúng: {' / '.join(SORT_FIELDS)}. "
            "Bỏ trống sort_by để xếp theo điểm rủi ro (score).")
    return sort_by


def _sort_rows(rows, name):
    """
    Sắp theo một yếu tố. Hoà thì điểm rủi ro cao hơn đứng trước, hoà nữa thì giữ
    thứ tự gốc của dữ liệu (sorted ổn định). Dòng THIẾU giá trị xuống cuối thay
    vì bị coi là 0 — thiếu dữ liệu và bằng 0 là hai chuyện khác nhau.
    """
    spec = _SORTS[name]

    def key(r):
        v = r.get(spec["col"])
        if v is None:
            return (1, 0, 0)
        return (0, -v if spec["desc"] else v, -r["flight_risk_score"])

    return sorted(rows, key=key)


def _sort_value(r, name):
    """Giá trị theo ĐƠN VỊ HIỂN THỊ. Chênh lệch lương lưu dạng phân số (-0.48) → đổi ra % (-48.0)."""
    v = r.get(_SORTS[name]["col"])
    if v is None:
        return None
    return round(v * 100, 1) if name == "salary_gap" else v


def _sort_text(r, name):
    """
    Chuỗi có sẵn con số dùng để sắp xếp, để model chép nguyên và guard truy được.

    Vì sao cần cả chuỗi chứ không chỉ số: chênh lệch lương là số ÂM (-48.0) còn
    câu văn viết "thấp hơn 48,0%" — guard chỉ nạp -48.0 từ trường số, nên con số
    dương model viết ra sẽ bị bắt oan. Chuỗi thì mang sẵn "48.0" dương.
    """
    if r.get(_SORTS[name]["col"]) is None:
        return "Không có dữ liệu"
    if name == "tenure":
        return f"Thâm niên {r['tenure_months']} tháng"
    col = _SORT_REASON_COL.get(name)
    text = r.get(col) if col else None
    if text:
        return text
    return f"{_sort_value(r, name)} {_SORTS[name]['unit']}"


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
                   bands=("High", "Medium"), limit: int = DEFAULT_LIMIT,
                   band=None, sort_by=None) -> dict:
    """
    band    : None | "Cao" | "Trung bình" | "Thấp" — chỉ lấy người ở đúng mức đó.
    sort_by : None | "score" | "salary_gap" | "kpi" | "freeze" | "promo" | "tenure".
    Giá trị nào ngoài danh sách thì raise InvalidParam (dispatch → INVALID_PARAM).

    GỌI KHÔNG KÈM band / sort_by thì kết quả GIỐNG HỆT bản trước khi có hai tham số
    này — kể cả tập khoá của dict (tests/test_list_sort.py so với file vàng lấy từ
    master). Các trường mới (band_filter, sort_by, n_matching, sort_value...) chỉ
    xuất hiện khi có ít nhất một trong hai tham số.

    n_flagged / n_high / n_medium luôn nói về nhóm Cao + Trung bình, KHÔNG đổi theo
    bộ lọc; số người khớp bộ lọc là n_matching, nhóm đang xét ghi ở population_vi:
    có band → đúng mức đó; sort_by ≠ score mà không có band → cả phạm vi (mọi mức);
    còn lại → Cao + Trung bình như cũ.

    (bands= là tham số nội bộ cũ, vẫn giữ cho test; LLM chỉ được thấy band.)

    limit mặc định 5, KHÔNG phải 10 — hạ ngày 1/9 sau khi đo độ trễ.

    Thời gian trả lời tỉ lệ gần như tuyến tính với số chữ model phải viết ra, mà
    mỗi người trong danh sách là hai dòng chữ. Đo được: câu "đội tôi ai rủi ro cao
    nhất" mất 49 giây, gần như toàn bộ là thời gian sinh chữ.

    Cắt ở ĐÂY chứ không phải trong lời nhắc là có chủ ý: model không thể liệt kê
    7 người nếu payload chỉ có 5. Dặn trong lời nhắc là lời khuyên, cắt trong dữ
    liệu là ràng buộc.

    n_flagged / n_high / scope_headcount VẪN là số đầy đủ, nên câu mở đầu
    "7 người cần lưu ý trên tổng 149" không bị sai — chỉ phần liệt kê chi tiết
    là rút gọn.
    """
    # Kiểm tham số TRƯỚC khi đụng tới dữ liệu: giá trị lạ thì dừng, không đoán.
    want_band = _parse_band(band)
    sort_name = _parse_sort(sort_by)
    extended = band is not None or sort_by is not None

    snap = store.latest_snapshot() if as_of == "latest" else as_of
    limit = max(1, min(int(limit), MAX_LIST))

    pool = [r for r in store.rows_for(snap, actor.scope)]
    excluded = sum(1 for r in pool if r["is_excluded_from_risk_list"])
    elig = [r for r in pool
            if not r["is_excluded_from_risk_list"]
            and r["flight_risk_band"] in bands
            and r["flight_risk_score"] is not None]
    # Người khớp bộ lọc — ba trường hợp:
    #   có band                    → đúng mức đó
    #   xếp theo yếu tố (≠ score)  → CẢ phạm vi, mọi mức
    #   còn lại                    → elig (Cao + Trung bình) như cũ
    # Vì sao xếp theo yếu tố thì phải xét cả phạm vi: hỏi "ai KPI/lương thấp nhất
    # đội tôi" mà chỉ xét nhóm Cao + Trung bình thì người đứng thứ hai có thể SAI —
    # đo trên A001: chỉ trong nhóm gắn cờ, người thấp lương thứ hai là -26,7%,
    # nhưng cả đội có người mức Thấp thấp hơn (-33,5%).
    # Người bị loại theo quy tắc cứng không bao giờ lên danh sách, bất kể trường hợp nào.
    whole_scope = [r for r in pool
                   if not r["is_excluded_from_risk_list"]
                   and r["flight_risk_score"] is not None]
    if want_band:
        match = [r for r in whole_scope if r["flight_risk_band"] == want_band]
        population_vi = f"mức {band}"
    elif sort_name not in (None, "score"):
        match = whole_scope
        population_vi = "ở mọi mức"
    else:
        match = elig
        population_vi = "mức Cao + Trung bình"

    if sort_name in (None, "score"):
        match = sorted(match, key=lambda r: -r["flight_risk_score"])    # đúng như cũ
    else:
        match = _sort_rows(match, sort_name)
    top = match[:limit]

    items = [{
        "employee_id": r["employee_id"],
        "full_name": store.display_name(r["employee_id"]),
        # Tên ĐƠN VỊ, không phải người quản lý — dữ liệu không có org-chart.
        # Có trường này để khi được hỏi "ai quản lý người này", agent còn chỗ
        # chỉ tiếp thay vì dừng ở một câu từ chối cụt.
        "dept_name": store.dept_name(r["dept_code"]),
        "score": r["flight_risk_score"],
        "band": r["flight_risk_band"],
        "band_vi": BAND_VI.get(r["flight_risk_band"], r["flight_risk_band"]),
        "top_factor": _top_factor_reason(r),
    } for r in top]

    res = {
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

    if extended:
        name = sort_name or "score"
        spec = _SORTS[name]
        # Mỗi dòng mang giá trị của CHÍNH trường dùng để xếp — để guard truy được số
        # và để người đọc thấy vì sao người này đứng ở đó. Xếp theo score thì điểm
        # đã nằm sẵn trong "score", nên chỉ thêm chuỗi khi xếp theo yếu tố khác.
        for it, r in zip(items, top):
            it["sort_value"] = _sort_value(r, name)
            if name != "score":
                it["sort_value_text"] = _sort_text(r, name)
        res.update({
            "band_filter": band,                     # đúng chữ tiếng Việt đã lọc, hoặc None
            "population_vi": population_vi,          # đang xét nhóm nào — để câu mở đầu nói đúng
            "sort_by": name,
            "sort_order_vi": spec["order_vi"],
            "sort_unit": spec["unit"],
            "n_matching": len(match),                # số người khớp bộ lọc, TRƯỚC khi cắt limit
            "n_missing_sort_value": sum(1 for r in match if r.get(spec["col"]) is None),
        })
        if not items:
            res["status"] = "no_match"
    return res


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
        "dept_name": store.dept_name(r["dept_code"]),
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
            # (vì chuỗi dừng xét lương bị phá) nên nhìn qua tưởng hợp lý. Đó là loại
            # lỗi mà hội đồng bắt được là hỏng cả bài.
            #
            # Không có hành động lương nào xảy ra ⇒ chuỗi dừng xét lương cũng không
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
        # Điều chuyển / bổ nhiệm: đồng hồ "chưa được điều chuyển" về 0.
        # Đây là phương án KHÔNG tốn ngân sách lương, và với người đã được trả
        # trên P50 thì thường là phương án duy nhất còn tác dụng.
        if move is None:
            raise ScenarioError("Thiếu dữ liệu lịch sử điều chuyển/bổ nhiệm, không mô phỏng được")
        move = 0
        label = "Điều chuyển / bổ nhiệm trong kỳ tới"

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
