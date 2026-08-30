# -*- coding: utf-8 -*-
"""Kiểm thử T1 / T2 / T6 — tiêu chí D2, D3, D11 của BLUEPRINT §13."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("RETAIN_DATA_DIR",
                      os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))

import pytest                                    # noqa: E402
from agent import scoring, store, tools                   # noqa: E402


def _du_lieu_dung_engine_hien_tai() -> bool:
    """
    False nghĩa là fact_flight_risk_score.csv được sinh bằng bản engine cũ.
    Khi đó score_before (đọc từ CSV) và score_after (tính lại bằng code hiện tại)
    dùng hai bộ trọng số khác nhau — mọi so sánh trước/sau đều vô nghĩa.
    Chạy lại: python generate_facts.py && python flight_risk_score.py
    """
    rows = store.load_scores()
    return bool(rows) and rows[0].get("months_since_last_move") is not None


def test_snapshot_la_ngay_dau_thang():
    """BLUEPRINT §5.1 — đừng hardcode ngày cuối tháng."""
    assert store.latest_snapshot() == "2025-12-01"


def test_T1_diem_tinh_lai_khop_voi_engine():
    """
    D3: điểm agent đọc phải khớp tuyệt đối với điểm engine đã ghi trong CSV.
    Agent KHÔNG được tính lại ra số khác.
    """
    if not _du_lieu_dung_engine_hien_tai():
        pytest.skip(
            "fact_flight_risk_score.csv được sinh bằng engine CŨ (chưa có cột "
            "months_since_last_move). Chạy lại: python generate_facts.py && "
            "python flight_risk_score.py — rồi bài test này sẽ tự chạy lại."
        )
    snap = store.latest_snapshot()
    checked = 0
    for r in store.load_scores():
        if r["snapshot_date"] != snap or r["flight_risk_score"] is None:
            continue
        comps = tools._comps_of(r)
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

    # Thứ tự yếu tố phải luôn theo scoring.FACTOR_ORDER — người đọc thấy cùng
    # một trật tự ở mọi câu trả lời. KHÔNG ghi cứng số 4 hay 5: thêm một yếu tố
    # vào mô hình không được làm đỏ một bài test về thứ tự trình bày.
    present = [f["factor"] for f in res["factors"]]
    assert present == [k for k in scoring.FACTOR_ORDER if k in present]

    # Dữ liệu sinh bằng engine hiện tại thì phải đủ cả 5 yếu tố.
    if store.load_scores()[0].get("months_since_last_move") is not None:
        assert len(present) == len(scoring.FACTOR_ORDER), present


# ── T6 ──────────────────────────────────────────────────────────────────────
def test_T6_chay_hai_lan_ra_cung_mot_so():
    """D11 — deterministic. Cùng giả định luôn ra cùng kết quả."""
    a = tools.build_actor("A003")
    r1 = tools.simulate_intervention(a, "E001881", "to_p50")
    r2 = tools.simulate_intervention(a, "E001881", "to_p50")
    assert r1["score_after"] == r2["score_after"]
    assert r1["is_deterministic"] is True


def test_T6_to_p50_dua_thanh_phan_luong_ve_0_va_pha_dong_bang():
    """
    D11 — với người ĐANG thiếu lương, to_p50 phải chạm CẢ hai yếu tố: đóng lại
    khoảng cách lương, và phá chuỗi đóng băng (vì có một hành động lương xảy ra).
    """
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


def test_T6_to_p50_khong_lam_gi_voi_nguoi_da_tren_p50():
    """
    Người đã ở trên P50 thì đòn bẩy lương đã CẠN — không phải yếu.

    Bản trước đặt gap = 0 cho mọi người, tức mô phỏng CẮT lương người đang ở
    trên trung vị rồi gọi đó là phương án giữ chân; điểm vẫn giảm (do chuỗi
    đóng băng bị phá) nên nhìn qua tưởng hợp lý.
    """
    snap = store.latest_snapshot()
    a = tools.build_actor("A003")
    tren_p50 = [r for r in store.rows_for(snap, a.scope)
                if (r["salary_gap_to_p50_pct"] or 0) >= 0
                and not r["is_excluded_from_risk_list"]]
    if not tren_p50:
        pytest.skip("bộ dữ liệu không có ai ở trên P50")
    if not _du_lieu_dung_engine_hien_tai():
        pytest.skip("dữ liệu sinh bằng engine cũ — chạy lại generate_facts.py + flight_risk_score.py")

    r = tools.simulate_intervention(a, tren_p50[0]["employee_id"], "to_p50")
    assert r["salary_lever_available"] is False
    assert r["score_after"] == r["score_before"], "không được giảm điểm bằng cách cắt lương"
    assert r["delta_by_factor"] == {}


def test_T6_promotion_khong_dung_toi_yeu_to_luong():
    """Đổi vai là đòn bẩy KHÔNG tốn ngân sách lương — nó không được chạm vào lương."""
    if not _du_lieu_dung_engine_hien_tai():
        pytest.skip("dữ liệu sinh bằng engine cũ — chạy lại generate_facts.py + flight_risk_score.py")
    a = tools.build_actor("A003")
    r = tools.simulate_intervention(a, "E001881", "promotion")
    assert "salary" not in r["delta_by_factor"]
    assert "freeze" not in r["delta_by_factor"]
    assert set(r["delta_by_factor"]) <= {"promo"}


# ── chất lượng dữ liệu hiển thị ─────────────────────────────────────────────
KINH_NGU = ("Ông ", "Bà ", "Anh ", "Chị ", "Cô ", "Bác ", "Quý ", "Chú ", "Em ")


def test_ten_nhan_su_khong_chua_kinh_ngu():
    """
    "Ông Trung Dương", "Quý cô Lâm Dương" — faker vi_VN nhét kính ngữ vào trường
    tên. Kính ngữ là cách xưng hô, không phải một phần của tên, và không bao giờ
    nằm trong full_name của HRIS. Hội đồng người Việt nhìn thấy là nghi ngờ cả
    bộ dữ liệu.
    """
    emps = store.load_employees()
    if not emps:
        pytest.skip("không có dim_employee.csv")
    xau = [e["full_name"] for e in emps.values()
           if e.get("full_name", "").startswith(KINH_NGU)]
    assert not xau, f"{len(xau)} tên còn kính ngữ, ví dụ: {xau[:5]}"


def test_ten_nhan_su_dung_thu_tu_ho_truoc():
    """
    Tiếng Việt là HỌ + ĐỆM + TÊN. "Anh Hoàng Nguyễn" là tên đọc theo lối phương
    Tây — họ bị đẩy xuống cuối. Kiểm bằng cách soi từ ĐẦU tiên: nó phải là một họ.
    """
    HO_PHO_BIEN = {"Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Phan", "Vũ",
                   "Võ", "Đặng", "Bùi", "Đỗ", "Hồ", "Ngô", "Dương", "Lý", "Đinh",
                   "Trịnh", "Đoàn", "Lương", "Mai", "Tô", "Chu", "Lâm", "Cao",
                   "Hà", "Kiều", "Thái", "Vương", "Đào"}
    emps = store.load_employees()
    if not emps:
        pytest.skip("không có dim_employee.csv")
    ten = [e["full_name"] for e in emps.values() if e.get("full_name")]
    dung = sum(1 for n in ten if n.split()[0] in HO_PHO_BIEN)
    assert dung / len(ten) > 0.95, f"chỉ {dung}/{len(ten)} tên bắt đầu bằng họ"
