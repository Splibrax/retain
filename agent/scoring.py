# -*- coding: utf-8 -*-
"""
scoring.py — NGUỒN SỰ THẬT DUY NHẤT của mô hình chấm điểm.

Trước file này, logic chấm điểm có BA bản sao: generate_facts.py, flight_risk_score.py,
và agent/tools.py (kèm comment "bản sao chính xác của engine" — một lời hứa không có gì
bảo đảm). Đổi trọng số mà sót một bản là có ba nguồn số khác nhau, và không có gì báo lỗi.

Giờ cả ba đều import từ đây. Đổi trọng số = sửa đúng một dòng bên dưới.

Luận giải vì sao mỗi yếu tố có trọng số như vậy: xem TRONG_SO.md.
"""
from __future__ import annotations

# ── Trọng số ────────────────────────────────────────────────────────────────
# Ba nhóm tín hiệu:
#   đãi ngộ  = lương (20) + đóng băng (20) = 40  ← nhóm nặng nhất
#   phát triển nghề nghiệp = thăng tiến (25)
#   gắn kết  = KPI (25)
#   nền thống kê = cửa sổ thâm niên (10)
WEIGHTS = {
    "salary":    0.20,
    "kpi":       0.25,
    "promo":     0.25,
    "freeze":    0.20,
    "seniority": 0.10,
}

# Thứ tự trình bày, cố định để mọi nơi hiện giống nhau.
FACTOR_ORDER = ("salary", "kpi", "promo", "freeze", "seniority")

FACTOR_VI = {
    "salary":    "khoảng cách lương so với P50 thị trường",
    "kpi":       "điểm KPI",
    "promo":     "thời gian chưa đổi vai / thăng cấp",
    "freeze":    "thời gian đóng băng lương",
    "seniority": "cửa sổ rủi ro theo thâm niên",
}

# ── Ngưỡng band ─────────────────────────────────────────────────────────────
#
# Đây là con số SẢN PHẨM, không phải con số kỹ thuật: nó quyết định "bao nhiêu
# người cán bộ quản lý phải để mắt tháng này". Chọn bằng phân bố thật, không
# bằng cảm giác — xem bảng CHỌN NGƯỠNG mà flight_risk_score.py in ra.
#
# Đo trên 1.285 nhân sự kỳ 12/2025:
#     ngưỡng 33 → 107 người (8,3%)   quá nhiều, danh sách sẽ bị bỏ qua
#     ngưỡng 38 →  42 người (3,3%)   ← chọn mức này
#     ngưỡng 45 →  11 người (0,9%)   quá ít, bỏ sót nhóm cần theo dõi sớm
#
# Ngưỡng Cao giữ 66: nhóm "cần can thiệp ngay", cố ý rất hẹp.
BAND_HIGH_AT = 66
BAND_MEDIUM_AT = 38

BAND_VI = {"High": "Cao", "Medium": "Trung bình", "Low": "Thấp", "": ""}

# ── Hằng số quy đổi từng yếu tố về thang 0–1 ────────────────────────────────
SALARY_GAP_SATURATION = 0.60      # thiếu 60% so với P50 → rủi ro tối đa
KPI_NO_RISK_AT = 70               # KPI ≥ 70 → rủi ro 0
KPI_SPAN = 60                     # KPI ≤ 10 → rủi ro 1,0
FREEZE_SATURATION_MONTHS = 24     # 24 tháng không điều chỉnh → rủi ro tối đa
# Đình trệ thăng tiến KHÔNG tính tuyến tính từ 0.
#
# Bản đầu dùng min(1, tháng/48): người vừa được thăng chức 12 tháng trước đã mang
# sẵn 0,25 rủi ro. Sai bản chất — 12 tháng chưa đổi vai là chuyện bình thường,
# không phải tín hiệu gì cả. Hậu quả đo được: nhóm Trung bình phình lên 159/1.127
# người (14%), tức là bảo cán bộ quản lý "để mắt tới 26 người" — không dùng được.
#
# Giờ rủi ro chỉ BẮT ĐẦU tính sau 24 tháng và bão hoà ở 60 tháng:
#   ≤24 tháng → 0,00   |   42 tháng → 0,50   |   ≥60 tháng → 1,00
PROMO_RISK_STARTS_AT = 24
PROMO_SATURATION_MONTHS = 60
SENIORITY_OUT_OF_WINDOW = 0.30    # sàn: ngoài cửa sổ vẫn còn rủi ro nền


def components(gap_pct=None, kpi_score=None, freeze_months=None,
               seniority_flag=None, months_since_move=None) -> dict:
    """
    Quy từng yếu tố về thang 0–1. Yếu tố nào KHÔNG có dữ liệu thì KHÔNG có mặt
    trong dict trả về — để renormalize() chia lại trọng số, thay vì coi thiếu = 0.
    Thiếu dữ liệu và không có rủi ro là hai chuyện khác nhau.
    """
    c = {}
    if gap_pct is not None:
        c["salary"] = min(1.0, max(0.0, -gap_pct) / SALARY_GAP_SATURATION)
    if kpi_score is not None:
        c["kpi"] = min(1.0, max(0.0, (KPI_NO_RISK_AT - kpi_score) / KPI_SPAN))
    if months_since_move is not None:
        span = PROMO_SATURATION_MONTHS - PROMO_RISK_STARTS_AT
        c["promo"] = min(1.0, max(0.0, (months_since_move - PROMO_RISK_STARTS_AT) / span))
    if freeze_months is not None:
        c["freeze"] = min(1.0, max(0.0, freeze_months) / FREEZE_SATURATION_MONTHS)
    if seniority_flag is not None:
        c["seniority"] = 1.0 if seniority_flag else SENIORITY_OUT_OF_WINDOW
    return c


def renormalize(comps: dict):
    """(điểm 0–100, trọng số thực dùng). Trả (None, {}) nếu không có yếu tố nào."""
    avail = sum(WEIGHTS[k] for k in comps)
    if avail == 0:
        return None, {}
    w = {k: WEIGHTS[k] / avail for k in comps}
    return round(100 * sum(w[k] * comps[k] for k in comps), 2), w


def band(score) -> str:
    if score is None:
        return ""
    return "High" if score >= BAND_HIGH_AT else ("Medium" if score >= BAND_MEDIUM_AT else "Low")


def top_factor(comps: dict, weights: dict) -> str | None:
    """Yếu tố đóng góp nhiều nhất = mức rủi ro × trọng số THỰC DÙNG."""
    if not comps:
        return None
    return max(comps, key=lambda k: comps[k] * weights.get(k, 0))


# ── Bất biến thiết kế ───────────────────────────────────────────────────────
def check_invariants() -> dict:
    """
    Hai tính chất phải luôn đúng. Đây không phải khẩu hiệu marketing — chúng
    kiểm được bằng máy, và có bài test canh riêng.

    (1) KHÔNG cặp yếu tố nào đủ đẩy một người lên mức Cao.
        Phải có ít nhất BA yếu tố cùng xấu. Đây là câu trả lời trực tiếp cho
        cáo buộc "mô hình chỉ đang xếp hạng người thiếu lương".

    (2) Người KHÔNG thiếu lương vẫn phải có thể lên mức Cao.
        Mô hình cũ (lương 40%) làm điều này bất khả thi về mặt số học:
        điểm tối đa khi không thiếu lương là 60 < 66. Nghĩa là "mức Cao" chỉ là
        cách gọi khác của "thiếu lương nặng" — một vòng luẩn quẩn, không phải phát hiện.
    """
    ws = sorted(WEIGHTS.values(), reverse=True)
    top2 = 100 * (ws[0] + ws[1])
    without_salary = 100 * (1 - WEIGHTS["salary"])
    # trần thực tế: cửa sổ thâm niên có sàn 0,3 nên 70% trọng số của nó gần như
    # không bao giờ đạt được với người ngoài cửa sổ
    realistic_without_salary = without_salary - 100 * WEIGHTS["seniority"] * (1 - SENIORITY_OUT_OF_WINDOW)
    return {
        "top_two_weights": round(top2, 2),
        "pair_can_reach_high": top2 >= BAND_HIGH_AT,
        "max_without_salary": round(without_salary, 2),
        "realistic_max_without_salary": round(realistic_without_salary, 2),
        "well_paid_can_reach_high": realistic_without_salary >= BAND_HIGH_AT,
        "weights_sum_to_one": abs(sum(WEIGHTS.values()) - 1.0) < 1e-9,
    }


def _self_check():
    inv = check_invariants()
    assert inv["weights_sum_to_one"], f"tổng trọng số phải bằng 1: {WEIGHTS}"
    assert not inv["pair_can_reach_high"], (
        f"Hai yếu tố nặng nhất cộng lại = {inv['top_two_weights']} ≥ {BAND_HIGH_AT}. "
        "Như vậy chỉ cần hai yếu tố xấu là bị gắn cờ mức Cao — mô hình quá dễ kích hoạt.")
    assert inv["well_paid_can_reach_high"], (
        f"Người không thiếu lương chỉ đạt tối đa {inv['realistic_max_without_salary']} "
        f"< {BAND_HIGH_AT}. Trọng số lương quá cao — mô hình đang định nghĩa "
        "'rủi ro cao' = 'thiếu lương', và mọi kết luận về lương sẽ là vòng luẩn quẩn.")


_self_check()
