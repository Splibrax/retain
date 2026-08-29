# -*- coding: utf-8 -*-
"""Kiểm thử lớp agent: registry (chốt an toàn), guard (R6/R9), runtime (thứ tự bước)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("RETAIN_DATA_DIR",
                      os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))

from agent import guard, registry, runtime, tools     # noqa: E402
from agent.llm import MockLLM                          # noqa: E402


# ── registry: chốt an toàn quan trọng nhất ──────────────────────────────────
def test_schema_khong_lo_tham_so_pham_vi():
    """
    LLM không được có ô nào để yêu cầu dữ liệu đơn vị khác.
    Bài test này canh lỗ hổng phân quyền — đừng tắt.
    """
    for t in registry.TOOL_SCHEMAS:
        props = set(t["function"]["parameters"]["properties"])
        leak = props & registry.FORBIDDEN_PARAMS
        assert not leak, f"{t['function']['name']} lộ tham số phạm vi: {leak}"


def test_dispatch_vut_bo_tham_so_pham_vi_neu_llm_co_truyen():
    a = tools.build_actor("A002")      # chỉ thấy 1 đơn vị
    r = registry.dispatch(a, "list_team_risk",
                          {"limit": 3, "dept_code": "01CN000028", "scope": "*"})
    assert r["_dropped_params"] == ["dept_code", "scope"]
    assert r["scope_headcount"] == 67, "Phải vẫn chỉ thấy đơn vị của chính mình"


def test_dispatch_tool_khong_ton_tai():
    a = tools.build_actor("A001")
    assert registry.dispatch(a, "xoa_du_lieu", {})["error"] == "UNKNOWN_TOOL"


# ── guard ───────────────────────────────────────────────────────────────────
def test_guard_bat_so_bia():
    res = [tools.list_team_risk(tools.build_actor("A001"), limit=5)]
    r = guard.verify("Có 12 người rủi ro, tỷ lệ nghỉ 37,5%.", res)
    assert r["ok"] is False and 37.5 in r["unverified_numbers"]


def test_guard_khong_bao_nham_so_that():
    a = tools.build_actor("A001")
    res = [tools.explain_employee_risk(a, "E001881")]
    txt = ("E001881 — 85,78/100, mức High. Lương thấp hơn P50 thị trường 50,7%, "
           "KPI 12,1/100, đóng băng lương 24 tháng.")
    assert guard.verify(txt, res)["ok"] is True


def test_guard_bat_hua_hen_nhung_bo_qua_phu_dinh():
    assert guard.check_phrases("Chắc chắn sẽ giữ được bạn ấy.")
    assert not guard.check_phrases("Đây là giả định, KHÔNG phải dự báo người này sẽ ở lại.")
    assert not guard.check_phrases("Việc này không đảm bảo giữ được người.")


# ── runtime ─────────────────────────────────────────────────────────────────
def test_runtime_actor_khong_hop_le_khong_goi_tool():
    r = runtime.answer(MockLLM(), "A999", "Team mình có ai muốn đi không?")
    assert r["tool_calls"] == []
    assert "không xác định được phạm vi" in r["answer"].lower()


def test_runtime_chan_cheo_don_vi_qua_ca_duong_ong():
    """Cảnh demo số 4, chạy hết đường ống chứ không chỉ gọi tool trực tiếp."""
    r = runtime.answer(MockLLM(), "A002", "Sao bạn E001881 lại bị chấm cao thế?")
    ans = r["answer"].lower()
    assert "ngoài phạm vi" in ans
    # bỏ dòng "Truy vấn: <hex>" ra trước khi soi — mã audit là hex, có thể chứa chữ số bất kỳ
    body = ans.split("truy vấn:")[0]
    for leak in ("85,78", "85.78", "e001881", "high"):
        assert leak not in body, f"Câu từ chối làm lộ: {leak}"


def test_runtime_tra_loi_dat_guard_cho_ca_4_canh():
    llm = MockLLM()
    scenes = [
        ("A001", "Team mình tháng này có ai đang có dấu hiệu muốn đi không?"),
        ("A001", "Sao bạn E001881 lại bị chấm cao thế?"),
        ("A001", "Giờ mình nên làm gì với bạn ấy?"),
        ("A001", "Nếu kéo lương bạn ấy về đúng mức thị trường thì rủi ro còn bao nhiêu?"),
    ]
    for actor, q in scenes:
        r = runtime.answer(llm, actor, q)
        assert r["verified"], f"Guard đỏ ở câu: {q} → {r['guard_report']}"
        assert r["tool_calls"], f"Không gọi tool nào cho: {q}"


def test_runtime_ghi_audit_id():
    r = runtime.answer(MockLLM(), "A001", "Team mình có ai muốn đi không?")
    assert r["audit_ids"] and all(a for a in r["audit_ids"])
