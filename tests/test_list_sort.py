# -*- coding: utf-8 -*-
"""
Kiểm thử list_team_risk mở rộng band / sort_by (nhánh v7-sort).

Bốn điều bài này canh:
  1. Không kèm tham số mới → kết quả GIỐNG HỆT master (so với file vàng).
  2. Lọc/sắp xếp vẫn đi qua scope của actor — không thấy ai ngoài đơn vị mình.
  3. Giá trị lạ → lỗi rõ ràng, không đoán.
  4. Mỗi dòng mang giá trị của trường dùng để xếp, và guard truy được số đó.

FILE VÀNG tests/golden_list_team_risk_master.json được sinh từ list_team_risk của
master e568923 TRƯỚC khi thêm band/sort_by (6 actor × 6 kiểu gọi, bỏ audit_id).
Nó gắn với bộ dữ liệu hiện tại: sinh lại data/ thì file vàng phải sinh lại từ
master tương ứng — đừng sửa tay cho bài test xanh.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("RETAIN_DATA_DIR", os.path.join(ROOT, "data"))

import pytest                                                    # noqa: E402
from agent import guard, prompt, registry, scoring, store, tools  # noqa: E402
from agent.llm import _render                                     # noqa: E402

with open(os.path.join(ROOT, "tests", "golden_list_team_risk_master.json"), encoding="utf-8") as _f:
    GOLDEN = json.load(_f)

ACTORS = ["A001", "A002", "A003", "A004", "A005"]
BANDS_VI = ["Cao", "Trung bình", "Thấp"]
BAND_EN = {"Cao": "High", "Trung bình": "Medium", "Thấp": "Low"}
SORTS = ["score", "salary_gap", "kpi", "freeze", "promo", "tenure"]

# Chiều sắp KỲ VỌNG, viết tay độc lập với tools._SORTS: True = giá trị lớn lên đầu.
DESC = {"score": True, "salary_gap": False, "kpi": False,
        "freeze": True, "promo": True, "tenure": True}
COL = {"score": "flight_risk_score", "salary_gap": "salary_gap_to_p50_pct",
       "kpi": "kpi_score", "freeze": "pay_freeze_months",
       "promo": "months_since_last_move", "tenure": "tenure_months"}


def _scrub(o):
    if isinstance(o, dict):
        return {k: _scrub(v) for k, v in o.items() if k != "audit_id"}
    if isinstance(o, list):
        return [_scrub(v) for v in o]
    return o


def _roundtrip(o):
    return json.loads(json.dumps(o, ensure_ascii=False))


def _scope_rows(actor_id):
    a = tools.build_actor(actor_id)
    return [r for r in store.rows_for(store.latest_snapshot(), a.scope)]


def _eligible(actor_id):
    """Người có thể lên danh sách: chưa bị loại theo quy tắc cứng và có điểm."""
    return [r for r in _scope_rows(actor_id)
            if not r["is_excluded_from_risk_list"] and r["flight_risk_score"] is not None]


# ══════════════════════════════════════════════════════════════════════════
# 1. Không tham số mới → giống hệt master
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("key", sorted(GOLDEN["cases"]))
def test_khong_tham_so_moi_thi_giong_het_master(key):
    actor_id = key.split("|")[0]
    case = GOLDEN["cases"][key]
    kw = dict(case["kwargs"])
    if "bands" in kw:
        kw["bands"] = tuple(kw["bands"])
    got = _roundtrip(_scrub(tools.list_team_risk(tools.build_actor(actor_id), **kw)))
    assert got == case["result"], f"{key}: khác master"


def test_file_vang_co_du_lieu_that():
    """Chặn file vàng rỗng làm bài trên xanh giả."""
    assert len(GOLDEN["cases"]) == 36
    assert sum(len(c["result"]["items"]) for c in GOLDEN["cases"].values()) > 100
    assert GOLDEN["_meta"]["snapshot_moi_nhat"] == store.latest_snapshot(), \
        "dữ liệu đã đổi kỳ — file vàng lấy từ master cũ, phải sinh lại"


def test_dispatch_khong_tham_so_moi_cung_giong_het_master():
    a = tools.build_actor("A001")
    for args in ({}, {"limit": 5}):
        got = _roundtrip(_scrub(registry.dispatch(a, "list_team_risk", args)))
        assert got == GOLDEN["cases"]["A001|mac_dinh"]["result"], args


def test_mac_dinh_khong_co_khoa_moi():
    res = tools.list_team_risk(tools.build_actor("A001"))
    moi = {"band_filter", "population_vi", "sort_by", "sort_order_vi", "sort_unit",
           "n_matching", "n_missing_sort_value"}
    assert not (moi & set(res))
    assert not any({"sort_value", "sort_value_text"} & set(i) for i in res["items"])


def test_sort_by_score_ro_rang_van_ra_cung_thu_tu_mac_dinh():
    a = tools.build_actor("A003")
    base = tools.list_team_risk(a, limit=20)
    ext = tools.list_team_risk(a, sort_by="score", limit=20)
    assert [i["employee_id"] for i in ext["items"]] == [i["employee_id"] for i in base["items"]]
    assert ext["n_matching"] == base["n_flagged"], "score mặc định vẫn xét nhóm Cao + Trung bình"
    assert ext["population_vi"] == "mức Cao + Trung bình"


def test_hai_lan_goi_cung_ket_qua():
    a = tools.build_actor("A003")
    r1 = _scrub(tools.list_team_risk(a, band="Trung bình", sort_by="kpi", limit=20))
    r2 = _scrub(tools.list_team_risk(a, band="Trung bình", sort_by="kpi", limit=20))
    assert r1 == r2


# ══════════════════════════════════════════════════════════════════════════
# 2. Sắp xếp đúng chiều, đúng người đứng đầu
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("actor_id", ["A001", "A003"])
@pytest.mark.parametrize("sort_by", SORTS)
def test_sap_xep_dung_chieu_va_nguoi_dung_dau(actor_id, sort_by):
    a = tools.build_actor(actor_id)
    res = tools.list_team_risk(a, sort_by=sort_by, limit=20)
    assert res["items"], "phải có người"
    col = COL[sort_by]
    by_id = {r["employee_id"]: r for r in _scope_rows(actor_id)}
    vals = [by_id[i["employee_id"]][col] for i in res["items"]]
    assert vals == sorted(vals, reverse=DESC[sort_by]), f"{sort_by}: sai chiều {vals}"

    # Người đứng đầu phải là cực trị THẬT của tập đang xét, tính độc lập từ CSV.
    if sort_by == "score":
        pop = [r for r in _eligible(actor_id) if r["flight_risk_band"] in ("High", "Medium")]
    else:
        pop = _eligible(actor_id)
    best = (max if DESC[sort_by] else min)(r[col] for r in pop)
    assert vals[0] == best
    assert res["n_matching"] == len(pop)


@pytest.mark.parametrize("sort_by", SORTS[1:])
def test_xep_theo_yeu_to_xet_ca_pham_vi_khong_chi_nhom_gan_co(sort_by):
    """
    Ca có thật trên A001: nếu chỉ xét nhóm Cao + Trung bình thì người thấp lương
    thứ hai là -26,7%, nhưng cả đội có người mức Thấp thấp hơn (-33,5%).
    """
    res = tools.list_team_risk(tools.build_actor("A001"), sort_by=sort_by, limit=20)
    assert res["population_vi"] == "ở mọi mức"
    assert res["n_matching"] == len(_eligible("A001"))
    assert res["n_matching"] > res["n_flagged"]


def test_a001_luong_thap_thu_hai_la_nguoi_muc_thap():
    res = tools.list_team_risk(tools.build_actor("A001"), sort_by="salary_gap", limit=3)
    gaps = [i["sort_value"] for i in res["items"]]
    assert gaps == sorted(gaps)
    assert res["items"][1]["band"] == "Low", \
        "người thấp lương thứ hai của A001 nằm ở mức Thấp — chỉ thấy khi xét cả đội"


def test_sort_value_dung_don_vi_hien_thi():
    a = tools.build_actor("A001")
    by_id = {r["employee_id"]: r for r in _scope_rows("A001")}
    for it in tools.list_team_risk(a, sort_by="salary_gap", limit=5)["items"]:
        raw = by_id[it["employee_id"]]["salary_gap_to_p50_pct"]
        assert it["sort_value"] == round(raw * 100, 1)       # phân số → %
    for it in tools.list_team_risk(a, sort_by="kpi", limit=5)["items"]:
        assert it["sort_value"] == by_id[it["employee_id"]]["kpi_score"]


def test_dong_thieu_gia_tri_xuong_cuoi_khong_bi_coi_la_0():
    rows = [
        {"employee_id": "X1", "flight_risk_score": 50.0, "kpi_score": None},
        {"employee_id": "X2", "flight_risk_score": 10.0, "kpi_score": 30.0},
        {"employee_id": "X3", "flight_risk_score": 20.0, "kpi_score": 30.0},
        {"employee_id": "X4", "flight_risk_score": 90.0, "kpi_score": 5.0},
    ]
    got = [r["employee_id"] for r in tools._sort_rows(rows, "kpi")]
    # X4 (5) đầu; X3 và X2 hoà 30 → điểm rủi ro cao hơn (X3) đứng trước; thiếu dữ liệu cuối
    assert got == ["X4", "X3", "X2", "X1"]
    assert tools._sort_text(rows[0], "kpi") == "Không có dữ liệu"
    assert tools._sort_value(rows[0], "kpi") is None


# ══════════════════════════════════════════════════════════════════════════
# 3. Lọc theo mức — đúng ngưỡng hiện có
# ══════════════════════════════════════════════════════════════════════════
def test_nguong_band_giu_nguyen_66_va_38():
    """Việc thêm bộ lọc không được đụng tới ngưỡng — chỉ đọc lại mức đã ghi sẵn."""
    assert scoring.BAND_HIGH_AT == 66 and scoring.BAND_MEDIUM_AT == 38


@pytest.mark.parametrize("actor_id", ["A001", "A003"])
@pytest.mark.parametrize("band", BANDS_VI)
def test_loc_band_dung_muc_va_dung_nguong(actor_id, band):
    a = tools.build_actor(actor_id)
    res = tools.list_team_risk(a, band=band, limit=20)
    pop = [r for r in _eligible(actor_id) if r["flight_risk_band"] == BAND_EN[band]]
    assert res["n_matching"] == len(pop)
    assert res["band_filter"] == band and res["population_vi"] == f"mức {band}"
    for it in res["items"]:
        assert it["band_vi"] == band
        s = it["score"]
        if band == "Cao":
            assert s >= 66
        elif band == "Trung bình":
            assert 38 <= s < 66
        else:
            assert s < 38
        assert scoring.band(s) == BAND_EN[band]      # khớp hàm chấm mức gốc
    scores = [i["score"] for i in res["items"]]
    assert scores == sorted(scores, reverse=True), "band một mình vẫn xếp theo điểm giảm dần"


@pytest.mark.parametrize("actor_id", ["A001", "A002", "A003", "A004", "A005"])
def test_ba_muc_cong_lai_bang_ca_pham_vi_va_cao_tb_bang_n_flagged(actor_id):
    a = tools.build_actor(actor_id)
    n = {b: tools.list_team_risk(a, band=b)["n_matching"] for b in BANDS_VI}
    assert sum(n.values()) == len(_eligible(actor_id))
    assert n["Cao"] + n["Trung bình"] == tools.list_team_risk(a)["n_flagged"]


def test_band_ket_hop_sort_by():
    a = tools.build_actor("A003")
    res = tools.list_team_risk(a, band="Trung bình", sort_by="kpi", limit=20)
    assert {i["band_vi"] for i in res["items"]} == {"Trung bình"}
    kpis = [i["sort_value"] for i in res["items"]]
    assert kpis == sorted(kpis)


@pytest.mark.parametrize("sort_by", [None] + SORTS)
@pytest.mark.parametrize("band", [None] + BANDS_VI)
@pytest.mark.parametrize("actor_id", ["A001", "A003"])
def test_nguoi_bi_loai_theo_quy_tac_cung_khong_bao_gio_len_danh_sach(actor_id, band, sort_by):
    a = tools.build_actor(actor_id)
    excluded = {r["employee_id"] for r in _scope_rows(actor_id) if r["is_excluded_from_risk_list"]}
    assert excluded, "cần dữ liệu có người bị loại để bài test này có nghĩa"
    res = tools.list_team_risk(a, band=band, sort_by=sort_by, limit=20)
    assert not ({i["employee_id"] for i in res["items"]} & excluded)


# ══════════════════════════════════════════════════════════════════════════
# 4. Phạm vi actor — lọc/sắp xếp KHÔNG được mở rộng scope
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("actor_id", ACTORS)
@pytest.mark.parametrize("sort_by", [None] + SORTS)
@pytest.mark.parametrize("band", [None] + BANDS_VI)
def test_moi_to_hop_deu_nam_trong_scope(actor_id, band, sort_by):
    a = tools.build_actor(actor_id)
    inside = {r["employee_id"] for r in _scope_rows(actor_id)}
    res = tools.list_team_risk(a, band=band, sort_by=sort_by, limit=20)
    ids = {i["employee_id"] for i in res["items"]}
    assert ids <= inside, f"{actor_id} thấy người ngoài scope: {sorted(ids - inside)[:3]}"
    assert res["scope_headcount"] == len(inside)
    if "n_matching" in res:
        assert res["n_matching"] <= len(inside)


def test_A002_xep_theo_salary_gap_khong_thay_nhan_su_ngoai_1_don_vi_cua_minh():
    a2 = tools.build_actor("A002")
    assert len(a2.scope) == 1, "A002 chỉ có đúng 1 đơn vị"
    snap = store.latest_snapshot()
    inside = {r["employee_id"] for r in store.rows_for(snap, a2.scope)}

    # Người thấp lương NHẤT TOÀN NGÂN HÀNG (ngoài đơn vị A002) — phải KHÔNG xuất hiện.
    outside = [r for r in store.load_scores()
               if r["snapshot_date"] == snap and r["employment_status"] == "Active"
               and r["employee_id"] not in inside and r["salary_gap_to_p50_pct"] is not None
               and not r["is_excluded_from_risk_list"]]
    lowest_outside = min(outside, key=lambda r: r["salary_gap_to_p50_pct"])

    res = tools.list_team_risk(a2, sort_by="salary_gap", limit=20)
    ids = {i["employee_id"] for i in res["items"]}
    assert ids and ids <= inside
    assert lowest_outside["employee_id"] not in ids
    # Người thấp lương nhất của A002 là cực trị TRONG đơn vị, không phải toàn ngân hàng.
    in_scope_min = min(r["salary_gap_to_p50_pct"] for r in _eligible("A002"))
    assert res["items"][0]["sort_value"] == round(in_scope_min * 100, 1)
    assert lowest_outside["salary_gap_to_p50_pct"] <= in_scope_min, \
        "dữ liệu không còn phân biệt được trong/ngoài scope — bài test mất tác dụng"
    # Cả 20 dòng đều thuộc ĐÚNG MỘT đơn vị của A002.
    assert {i["dept_name"] for i in res["items"]} == {store.dept_name(next(iter(a2.scope)))}


def test_tham_so_pham_vi_van_bi_vut_khi_co_band_sort_by():
    a2 = tools.build_actor("A002")
    r = registry.dispatch(a2, "list_team_risk",
                          {"sort_by": "salary_gap", "band": "Cao", "dept_code": "01CN000028"})
    assert r["_dropped_params"] == ["dept_code"]
    assert r["scope_headcount"] == 67
    inside = {x["employee_id"] for x in _scope_rows("A002")}
    assert {i["employee_id"] for i in r["items"]} <= inside


def test_actor_khong_hop_le_van_khong_thay_gi_khi_co_tham_so_moi():
    a = tools.build_actor("A999")
    res = tools.list_team_risk(a, band="Cao", sort_by="salary_gap")
    assert res["items"] == [] and res["scope_headcount"] == 0
    assert res["status"] == "no_match"


# ══════════════════════════════════════════════════════════════════════════
# 5. Giá trị lạ → lỗi rõ ràng, không đoán
# ══════════════════════════════════════════════════════════════════════════
BAD_BANDS = ["High", "Medium", "Low", "cao", "CAO", "Cao ", "Trung Bình", "Tất cả", "", 1, ["Cao"]]
BAD_SORTS = ["salary", "gap", "SCORE", "Score", "risk", "kpi ", "", "luong", 5, ["kpi"]]


@pytest.mark.parametrize("bad", BAD_BANDS)
def test_band_la_bi_tu_choi_ro_rang(bad):
    a = tools.build_actor("A001")
    n = len(tools.AUDIT_LOG)
    with pytest.raises(tools.InvalidParam) as e:
        tools.list_team_risk(a, band=bad)
    for v in BANDS_VI:
        assert v in str(e.value), "thông báo phải nêu các giá trị được phép"
    assert len(tools.AUDIT_LOG) == n, "giá trị lạ dừng TRƯỚC khi chạm dữ liệu"

    r = registry.dispatch(a, "list_team_risk", {"band": bad})
    assert r["error"] == "INVALID_PARAM" and "items" not in r
    assert all(v in r["message"] for v in BANDS_VI)


@pytest.mark.parametrize("bad", BAD_SORTS)
def test_sort_by_la_bi_tu_choi_ro_rang(bad):
    a = tools.build_actor("A001")
    with pytest.raises(tools.InvalidParam) as e:
        tools.list_team_risk(a, sort_by=bad)
    for v in SORTS:
        assert v in str(e.value)
    r = registry.dispatch(a, "list_team_risk", {"sort_by": bad})
    assert r["error"] == "INVALID_PARAM" and "items" not in r


def test_mot_tham_so_hop_le_mot_tham_so_la_van_bi_tu_choi():
    a = tools.build_actor("A001")
    r = registry.dispatch(a, "list_team_risk", {"band": "Cao", "sort_by": "luong"})
    assert r["error"] == "INVALID_PARAM"


# ══════════════════════════════════════════════════════════════════════════
# 6. Mỗi dòng mang giá trị trường xếp, và guard truy được số đó
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("sort_by", SORTS[1:])
def test_moi_dong_co_sort_value_va_sort_value_text(sort_by):
    res = tools.list_team_risk(tools.build_actor("A003"), sort_by=sort_by, limit=20)
    assert res["sort_by"] == sort_by and res["sort_order_vi"] and res["sort_unit"]
    for it in res["items"]:
        assert "sort_value" in it and it["sort_value"] is not None
        text = it["sort_value_text"]
        assert text
        if it["sort_value"] != 0:
            # con số dùng để xếp phải NHÌN THẤY được trong chuỗi
            assert f"{abs(it['sort_value']):g}" in text, (sort_by, it["sort_value"], text)


def test_sort_by_score_moi_dong_co_sort_value_bang_diem_khong_them_chuoi():
    res = tools.list_team_risk(tools.build_actor("A001"), band="Cao", limit=5)
    for it in res["items"]:
        assert it["sort_value"] == it["score"]
        assert "sort_value_text" not in it


@pytest.mark.parametrize("sort_by", SORTS[1:])
def test_guard_kiem_duoc_so_cua_truong_xep(sort_by):
    """Câu dựng từ sort_value_text (kiểu chấm hoặc kiểu phẩy) phải qua guard; số bịa phải bị bắt."""
    res = tools.list_team_risk(tools.build_actor("A001"), sort_by=sort_by, limit=5)
    sach = "\n".join(f"| {i['full_name']} | {i['employee_id']} | {i['score']} | "
                     f"{i['band_vi']} | {i['sort_value_text']} |" for i in res["items"])
    assert guard.check_numbers(sach, [res]) == []
    # model hay viết số kiểu Việt: 48.0 → 48,0
    phay = re.sub(r"(\d)\.(\d)", r"\1,\2", sach)
    assert guard.check_numbers(phay, [res]) == []
    # phép thử ngược: thêm một con số bịa thì guard phải bắt
    assert 77.7 in guard.check_numbers(sach + "\nTỉ lệ nghỉ việc dự kiến 77,7%.", [res])


def test_guard_khong_bao_oan_luong_am():
    """sort_value là số ÂM (-48.0), câu văn viết dương ("48,0%") — phải qua."""
    res = tools.list_team_risk(tools.build_actor("A001"), sort_by="salary_gap", limit=1)
    v = res["items"][0]["sort_value"]
    assert v < 0
    assert guard.check_numbers(f"Lương thấp hơn P50 thị trường {abs(v)}%".replace(".", ","), [res]) == []


# ══════════════════════════════════════════════════════════════════════════
# 7. Schema và prompt để model biết khi nào dùng band / sort_by
# ══════════════════════════════════════════════════════════════════════════
def _schema(name):
    return next(t["function"] for t in registry.TOOL_SCHEMAS if t["function"]["name"] == name)


def test_schema_list_team_risk_co_band_va_sort_by_dung_danh_sach():
    props = _schema("list_team_risk")["parameters"]["properties"]
    assert props["band"]["enum"] == ["Cao", "Trung bình", "Thấp"]
    assert props["sort_by"]["enum"] == ["score", "salary_gap", "kpi", "freeze", "promo", "tenure"]
    assert "mặc định 5" in props["limit"]["description"], "mô tả cũ ghi 10 trong khi code mặc định 5"
    assert _schema("list_team_risk")["parameters"]["required"] == []


def test_khong_them_tool_moi():
    assert [t["function"]["name"] for t in registry.TOOL_SCHEMAS] == [
        "list_team_risk", "explain_employee_risk", "suggest_actions", "simulate_intervention"]


def test_prompt_dan_dung_ba_va_bang_5_cot():
    p = prompt.SYSTEM_PROMPT
    assert "| Tên | Mã NV | Điểm/100 | Mức | Lý do chính |" in p
    assert "KHÔNG dùng danh sách đánh số" in p
    assert "từ 2 người trở lên" in p
    for v in SORTS[1:]:
        assert v in p, f"prompt chưa nói khi nào dùng sort_by={v}"
    for v in BANDS_VI:
        assert f'"{v}"' in p, f"prompt chưa nói khi nào dùng band={v}"
    for k in ("n_matching", "population_vi", "sort_value_text", "INVALID_PARAM", "no_match"):
        assert k in p, f"prompt chưa nhắc tới {k}"


# ══════════════════════════════════════════════════════════════════════════
# 8. Câu dựng tự động (fallback/mock) cũng theo quy tắc bảng 5 cột
# ══════════════════════════════════════════════════════════════════════════
HEADER = "| Tên | Mã NV | Điểm/100 | Mức | Lý do chính |"


@pytest.mark.parametrize("kw", [dict(), dict(sort_by="kpi"), dict(band="Cao"),
                                dict(band="Thấp", sort_by="promo")])
def test_render_tu_2_nguoi_tro_len_la_bang_5_cot_khong_danh_sach_danh_so(kw):
    res = tools.list_team_risk(tools.build_actor("A003"), limit=4, **kw)
    assert len(res["items"]) >= 2
    text = _render(res)
    assert HEADER in text
    rows = [ln for ln in text.splitlines() if ln.startswith("|") and "---" not in ln][1:]
    assert len(rows) == len(res["items"])
    assert all(ln.count("|") == 6 for ln in rows), "mỗi dòng đúng 5 cột"
    assert not re.search(r"^\s*\d+[.)]\s", text, re.M), "không được có danh sách đánh số"
    assert guard.check_numbers(text, [res]) == []


def test_render_mot_nguoi_thi_viet_thanh_cau_khong_dung_bang():
    res = tools.list_team_risk(tools.build_actor("A003"), limit=1, sort_by="kpi")
    text = _render(res)
    assert HEADER not in text
    assert res["items"][0]["employee_id"] in text


# ══════════════════════════════════════════════════════════════════════════
# 9. Bộ chấm eval mới (expect_args / table) và ba case A36–A38
# ══════════════════════════════════════════════════════════════════════════
def test_check_table_format_bat_dung_loi():
    from run_eval import check_table_format
    bang = ("Mở đầu.\n| Tên | Mã NV | Điểm/100 | Mức | Lý do chính |\n|---|---|---|---|---|\n"
            "| A | E000001 | 50 | Cao | x |\n| B | E000002 | 40 | Trung bình | y |\n")
    assert check_table_format(bang) == ""
    danh_so = "1. A (E000001) — 50/100\n2. B (E000002) — 40/100\n"
    assert "không có bảng" in check_table_format(danh_so)
    lai = bang + "1. thêm một dòng đánh số\n"
    assert "danh sách" in check_table_format(lai)
    gach = bang + "- gạch đầu dòng\n"
    assert "danh sách" in check_table_format(gach)
    thieu_cot = "| Tên | Mã NV | Điểm/100 | Mức |\n|--|--|--|--|\n| A | E000001 | 5 | Cao |\n| B | E000002 | 4 | Thấp |\n"
    assert "không có bảng" in check_table_format(thieu_cot)
    # dưới 2 người thì không áp quy tắc
    assert check_table_format("Mai Hữu Tuấn (E001881) — 67.01/100, mức Cao.") == ""


def test_ba_case_moi_dung_gia_tri_hop_le():
    from evalset.cases import NGHIEP_VU
    cases = {c["id"]: c for c in NGHIEP_VU}
    assert len({c["id"] for c in NGHIEP_VU}) == len(NGHIEP_VU), "id trùng"
    expect = {"A36": {"sort_by": "salary_gap"}, "A37": {"band": "Cao"}, "A38": {"sort_by": "kpi"}}
    asks = {"A36": "ai có khoảng cách lương thị trường thấp nhất?",
            "A37": "liệt kê những người mức Cao",
            "A38": "ai KPI thấp nhất team tôi?"}
    for cid, args in expect.items():
        c = cases[cid]
        assert c["ask"] == asks[cid]
        assert c["expect"] == ["list_team_risk"]
        assert c["expect_args"] == {"list_team_risk": args}
        assert c["table"] is True
        # giá trị kỳ vọng phải là giá trị tool CHẤP NHẬN — tránh case không thể đạt
        for k, v in args.items():
            assert v in (tools.BAND_INPUT if k == "band" else tools.SORT_FIELDS)
        assert tools.build_actor(c["actor"]).scope, "actor của case phải có scope"
