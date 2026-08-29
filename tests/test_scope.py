# -*- coding: utf-8 -*-
"""
5 bài kiểm thử bắt buộc của BLUEPRINT §7 + kiểm thử chặn chéo đơn vị.
Đây là bộ test hội đồng sẽ hỏi tới. Không được để đỏ.
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("RETAIN_DATA_DIR",
                      os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))

from agent.scope import resolve_scope, load_hierarchy, LEVELS  # noqa: E402
from agent import store, tools                                  # noqa: E402

LVL1_CN = "01CN000025"      # Ngân hàng Đối tác Chiến lược (61 dòng hierarchy)
LEAF = "01CN000015"         # node lá
MID_ORPHAN = "01CN000057"   # node cấp trung gian, cũng là lowest_code


# ── Test 1 ──────────────────────────────────────────────────────────────────
def test_lvl1_tra_ve_toan_bo_cay_con():
    scope = resolve_scope(LVL1_CN)
    assert len(scope) >= 61, f"lvl1 phải trả >=61 đơn vị, được {len(scope)}"
    assert LVL1_CN in scope


# ── Test 2 ──────────────────────────────────────────────────────────────────
def test_node_la_chi_tra_ve_chinh_no():
    scope = resolve_scope(LEAF)
    assert scope == {LEAF}, f"node lá phải trả đúng 1 đơn vị, được {sorted(scope)}"


# ── Test 3 ── 8 dept_code "mồ côi" (BLUEPRINT §5.4) ─────────────────────────
def test_dept_code_mo_coi_khong_bi_rot():
    """
    8 mã trong fact table nằm ở cấp trung gian, không phải lowest_code.
    Nếu resolve_scope chỉ match lowest_code thì 23 nhân sự này biến mất
    khỏi scope của cấp trên → HRBP mất người thật.
    """
    chains = load_hierarchy()
    lowest = {c[-1] for c in chains}
    snap = store.latest_snapshot()
    fact_depts = {r["dept_code"] for r in store.load_scores()
                  if r["snapshot_date"] == snap}
    orphans = fact_depts - lowest
    assert orphans, "Bộ dữ liệu phải còn mã mồ côi để bài test này có nghĩa"

    scope_lvl1 = resolve_scope(LVL1_CN)
    scope_qt = resolve_scope("01QT000018")
    for o in orphans:
        assert o in scope_lvl1 or o in scope_qt, \
            f"Mã mồ côi {o} rơi khỏi mọi scope cấp 1 — sẽ mất người"


def test_node_trung_gian_nam_trong_scope_cua_cha():
    assert MID_ORPHAN in resolve_scope(LVL1_CN)
    assert MID_ORPHAN in resolve_scope(MID_ORPHAN)


# ── Test 4 ── FAIL CLOSED ───────────────────────────────────────────────────
def test_ma_khong_ton_tai_tra_ve_rong_khong_phai_tat_ca():
    assert resolve_scope("MA_KHONG_TON_TAI") == frozenset()
    assert resolve_scope("") == frozenset()
    assert resolve_scope(None) == frozenset()


def test_actor_khong_hop_le_khong_thay_gi():
    a = tools.build_actor("A999")          # mã đơn vị không tồn tại
    assert a.scope == frozenset()
    res = tools.list_team_risk(a)
    assert res["scope_headcount"] == 0 and res["status"] == "no_risk"

    b = tools.build_actor("KHONG_CO_ACTOR_NAY")
    assert b.scope == frozenset() and b.role == "NONE"


# ── Test 5 ── chặn chéo đơn vị (cảnh demo số 4) ─────────────────────────────
def test_lm_don_vi_khac_khong_xem_duoc_nhan_su_ngoai_scope():
    a001 = tools.build_actor("A001")       # thấy E001881
    a002 = tools.build_actor("A002")       # KHÔNG được thấy E001881

    ok = tools.explain_employee_risk(a001, "E001881")
    assert "error" not in ok and ok["score"] is not None

    denied = tools.explain_employee_risk(a002, "E001881")
    assert denied.get("error") == "OUT_OF_SCOPE"
    # R4: không lộ tên, mã, hay sự tồn tại
    assert "full_name" not in denied and "score" not in denied and "band" not in denied


def test_mo_phong_cung_bi_chan_theo_scope():
    a002 = tools.build_actor("A002")
    r = tools.simulate_intervention(a002, "E001881", "to_p50")
    assert r.get("error") == "OUT_OF_SCOPE"


def test_hai_scope_khong_giao_nhau():
    s1 = resolve_scope("01CN000025")
    s2 = resolve_scope("01QT000018")
    assert not (s1 & s2), "Hai khối cấp 1 không được chồng lấn đơn vị"
