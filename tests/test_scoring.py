# -*- coding: utf-8 -*-
"""
Kiểm thử mô hình chấm điểm — canh hai bất biến thiết kế.

Đây không phải test về code, mà về CHẤT LƯỢNG MÔ HÌNH. Nếu ai đó chỉnh trọng số
mà làm hỏng một trong hai tính chất dưới đây, bài test phải đỏ trước khi bộ dữ
liệu mới kịp ra đời.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("RETAIN_DATA_DIR",
                      os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))

from agent import scoring, tools     # noqa: E402


# ── bất biến ────────────────────────────────────────────────────────────────
def test_trong_so_cong_lai_bang_1():
    assert abs(sum(scoring.WEIGHTS.values()) - 1.0) < 1e-9


def test_khong_cap_yeu_to_nao_du_len_muc_cao():
    """
    Phải cần ÍT NHẤT BA yếu tố cùng xấu mới lên được mức Cao.
    Mô hình cũ chỉ cần hai (lương 40 + KPI 30 = 70 > 66) — nghĩa là chỉ cần
    thiếu lương nặng và KPI kém là bị gắn cờ, không cần bằng chứng nào khác.
    """
    ws = sorted(scoring.WEIGHTS.values(), reverse=True)
    assert 100 * (ws[0] + ws[1]) < scoring.BAND_HIGH_AT


def test_nguoi_luong_tot_van_len_duoc_muc_cao():
    """
    Bài test quan trọng nhất trong file này.

    Mô hình cũ đặt lương 40% ⇒ điểm tối đa khi KHÔNG thiếu lương là 60 < 66.
    Người được trả lương tốt không bao giờ chạm được mức Cao — nên "mức Cao"
    chỉ là cách gọi khác của "thiếu lương nặng", và mọi kết luận của mô hình
    về lương đều là vòng luẩn quẩn.
    """
    c = scoring.components(gap_pct=0.10, kpi_score=15, freeze_months=24,
                           seniority_flag=False, months_since_move=60)
    s, _ = scoring.renormalize(c)
    assert c["salary"] == 0.0, "người trên P50 phải có rủi ro lương bằng 0"
    assert scoring.band(s) == "High", f"chỉ đạt {s}, không lên nổi mức Cao"


def test_mot_yeu_to_don_le_khong_bao_gio_du():
    for k in scoring.WEIGHTS:
        assert 100 * scoring.WEIGHTS[k] < scoring.BAND_HIGH_AT


# ── một nguồn sự thật ───────────────────────────────────────────────────────
def test_agent_dung_chung_trong_so_voi_engine():
    """
    Trước đây tools.py giữ 'bản sao chính xác' của công thức engine. Bản sao là
    chỗ trọng số đi lạc mà không ai biết. Giờ phải là cùng một object.
    """
    assert tools.WEIGHTS is scoring.WEIGHTS


# ── thiếu dữ liệu ───────────────────────────────────────────────────────────
def test_thieu_du_lieu_thi_chia_lai_trong_so():
    c = scoring.components(gap_pct=None, kpi_score=40, freeze_months=None,
                           seniority_flag=True, months_since_move=None)
    s, w = scoring.renormalize(c)
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert set(w) == {"kpi", "seniority"}


def test_thieu_lich_su_doi_vai_khong_bi_coi_la_vua_thang_chuc():
    """
    None (không biết) phải khác 0 (vừa mới đổi vai). Coi None là 0 là hạ điểm
    rủi ro của người mình không có dữ liệu — im lặng và sai hướng.
    """
    khong_biet = scoring.components(gap_pct=-0.3, kpi_score=40, freeze_months=6,
                                    seniority_flag=False, months_since_move=None)
    vua_thang = scoring.components(gap_pct=-0.3, kpi_score=40, freeze_months=6,
                                   seniority_flag=False, months_since_move=0)
    assert "promo" not in khong_biet
    assert vua_thang["promo"] == 0.0


# ── mô phỏng không được cắt lương ai ────────────────────────────────────────
class _Row(dict):
    pass


def test_to_p50_khong_bao_gio_giam_luong_nguoi_dang_tren_p50():
    """
    Bản đầu đặt thẳng gap = 0 cho mọi người, kể cả người đang ở +8% so với P50 —
    tức là mô phỏng GIẢM lương rồi gọi đó là phương án giữ chân. Điểm vẫn giảm
    (do chuỗi đóng băng bị phá) nên nhìn qua tưởng hợp lý.
    """
    tren_p50 = scoring.components(gap_pct=0.08, kpi_score=30, freeze_months=24,
                                  seniority_flag=False, months_since_move=59)
    ve_p50 = scoring.components(gap_pct=0.0, kpi_score=30, freeze_months=24,
                                seniority_flag=False, months_since_move=59)
    # hai trạng thái này phải cho cùng rủi ro lương — "về P50" không được là một
    # thay đổi có lợi cho điểm số của người vốn đã ở trên P50
    assert tren_p50["salary"] == ve_p50["salary"] == 0.0
