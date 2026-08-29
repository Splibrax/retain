# -*- coding: utf-8 -*-
"""Kiểm thử T1 / T2 / T6 — tiêu chí D2, D3, D11 của BLUEPRINT §13."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("RETAIN_DATA_DIR",
                      os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))

import pytest                                    # noqa: E402
from agent import store, tools                   # noqa: E402


def test_snapshot_la_ngay_dau_thang():
    """BLUEPRINT §5.1 — đừng hardcode ngày cuối tháng."""
    assert store.latest_snapshot() == "2025-12-01"


def test_T1_diem_tinh_lai_khop_voi_engine():
    """
    D3: điểm agent đọc phải khớp tuyệt đối với điểm engine đã ghi trong CSV.
    Agent KHÔNG được tính lại ra số khác.
    """
    snap = store.latest_snapshot()
    checked = 0
    for r in store.load_scores():
        if r["snapshot_date"] != snap or r["flight_risk_score"] is None:
            continue
        comps = tools._components(r["salary_gap_to_p50_pct"], r["kpi_score"],
                                  r["pay_freeze_months"], r["seniority_risk_window_flag"])
        s, _ = tools._score(comps)
        assert abs(s - r["flight_risk_score"]) < 0.02, \
            f"{r['employee_id']}: agent {s} vs engine {r['flight_risk_score']}"
        checked += 1
    assert checked > 1000


def test_T1_hard_cap_20_dong():
    a = tools.build_actor("A003")
    res = tools.list_team_risk(a, limit=999)
    assert len(res["items"]) <= tools.MAX_LIST


def test_T1_loai_tru_nguoi_bi_exclusion():
    a = tools.build_actor("A003")
    res = tools.list_team_risk(a, bands=("High", "Medium", "Low"), limit=20)
    ids = {i["employee_id"] for i in res["items"]}
    snap = store.latest_snapshot()
    excluded = {r["employee_id"] for r in store.load_scores()
                if r["snapshot_date"] == snap and r["is_excluded_from_risk_list"]}
    assert not (ids & excluded), "Người ≥2 cảnh cáo không được lọt vào danh sách"


def test_T2_trong_so_cong_lai_bang_1():
    a = tools.build_actor("A003")
    res = tools.explain_employee_risk(a, "E001881")
    assert abs(sum(f["weight_used"] for f in res["factors"]) - 1.0) < 1e-6
    assert len(res["factors"]) == 4


# ── T6 ──────────────────────────────────────────────────────────────────────
def test_T6_chay_hai_lan_ra_cung_mot_so():
    """D11 — deterministic. Cùng giả định luôn ra cùng kết quả."""
    a = tools.build_actor("A003")
    r1 = tools.simulate_intervention(a, "E001881", "to_p50")
    r2 = tools.simulate_intervention(a, "E001881", "to_p50")
    assert r1["score_after"] == r2["score_after"]
    assert r1["is_deterministic"] is True


def test_T6_to_p50_dua_thanh_phan_luong_ve_0_va_pha_dong_bang():
    """D11 — to_p50 phải chạm CẢ salary (40%) lẫn freeze (20%)."""
    a = tools.build_actor("A003")
    r = tools.simulate_intervention(a, "E001881", "to_p50")
    assert r["score_after"] < r["score_before"]
    assert "salary" in r["delta_by_factor"]
    assert "freeze" in r["delta_by_factor"], "Tăng lương phải reset pay freeze"


def test_T6_tu_choi_giam_luong_va_muc_phi_ly():
    a = tools.build_actor("A003")
    for bad in (-0.1, 0, 0.8):
        with pytest.raises(tools.ScenarioError):
            tools.simulate_intervention(a, "E001881", "raise_pct", bad)


def test_T6_kpi_recovery_khong_dung_toi_yeu_to_luong():
    a = tools.build_actor("A003")
    r = tools.simulate_intervention(a, "E001881", "kpi_recovery", 85)
    assert "salary" not in r["delta_by_factor"]
    assert r["score_after"] < r["score_before"]


def test_T6_luon_co_nhan_canh_bao():
    """R9 — nhãn cứng trong code, không phụ thuộc LLM tự nhớ."""
    a = tools.build_actor("A003")
    r = tools.simulate_intervention(a, "E001881", "to_p50")
    assert "KHÔNG phải dự báo" in r["disclaimer"]


def test_T6_LM_khong_thay_tien_HRBP_thay_truong_tien():
    """§5.3b — phân tầng theo vai."""
    lm = tools.build_actor("A001")
    hrbp = tools.build_actor("A003")
    assert lm.sees_money is False
    assert hrbp.sees_money is True


def test_audit_log_ghi_ca_truy_van_bi_tu_choi():
    tools.AUDIT_LOG.clear()
    a002 = tools.build_actor("A002")
    tools.explain_employee_risk(a002, "E001881")
    assert len(tools.AUDIT_LOG) == 1
    assert tools.AUDIT_LOG[0]["was_denied"] is True
    assert tools.AUDIT_LOG[0]["deny_reason"] == "OUT_OF_SCOPE"
