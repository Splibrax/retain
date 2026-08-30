# -*- coding: utf-8 -*-
"""
Kiểm thử bản tin email.

Trọng tâm không phải "HTML có đẹp không" mà là hai câu hỏi hội đồng sẽ hỏi:
  1. Đổi kênh có làm rò rỉ phân quyền không?
  2. Email bị chuyển tiếp lung tung thì lộ được gì?
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("RETAIN_DATA_DIR",
                      os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))

from agent import digest, digest_email, store     # noqa: E402
from agent.scope import resolve_scope             # noqa: E402

EID_RE = re.compile(r"E\d{6}")


# ── phân quyền ──────────────────────────────────────────────────────────────
def test_hai_hrbp_khac_khoi_ra_so_khac_nhau():
    """A003 (66 đơn vị) và A004 (20 đơn vị) không được nhìn thấy cùng một bức tranh."""
    a, b = digest.build_digest("A003"), digest.build_digest("A004")
    assert a["scope_units"] != b["scope_units"]
    assert a["headcount"] != b["headcount"]
    assert {u["dept_code"] for u in a["units"]}.isdisjoint({u["dept_code"] for u in b["units"]})


def test_moi_don_vi_trong_ban_tin_deu_nam_trong_pham_vi():
    """
    Canh lỗ hổng: không đơn vị nào lọt vào bản tin mà nằm ngoài scope đã resolve.
    Nếu bài này đỏ thì kênh email đang rò dữ liệu — dừng deploy.
    """
    for aid, actor in store.load_actors().items():
        d = digest.build_digest(aid)
        if d.get("error"):
            continue
        scope = resolve_scope(actor["dept_scope_code"])
        for u in d["units"]:
            assert u["dept_code"] in scope, f"{aid} lọt đơn vị {u['dept_code']} ngoài phạm vi"


def test_ma_don_vi_khong_ton_tai_thi_khong_gui_gi():
    """A999 — fail closed. Không có scope thì không có bản tin, không phải bản tin rỗng."""
    d = digest.build_digest("A999")
    assert d["error"] == "EMPTY_SCOPE"
    assert "units" not in d
    html = digest_email.render_html(d)
    assert not EID_RE.search(html)
    assert "nhân sự" not in html.replace("người dùng", "")   # không rò con số nào


def test_actor_khong_ton_tai():
    assert digest.build_digest("KHONG_CO_ACTOR_NAY")["error"] == "UNKNOWN_ACTOR"


# ── rò rỉ nội dung ──────────────────────────────────────────────────────────
def test_ban_tin_khong_chua_ma_nhan_vien():
    """
    Email bị chuyển tiếp, in ra, chiếu lên màn hình họp. Bản tin chỉ được có
    số tổng hợp — muốn biết ai thì phải mở app, nơi có ghi log.
    """
    for aid in ("A001", "A003", "A004"):
        html = digest_email.render_html(digest.build_digest(aid))
        assert not EID_RE.search(html), f"bản tin {aid} lộ mã nhân viên"


def test_ban_tin_khong_chua_ten_ca_nhan():
    names = {e.get("full_name") for e in store.load_employees().values() if e.get("full_name")}
    if not names:
        return                       # không có dim_employee thì không có gì để rò
    html = digest_email.render_html(digest.build_digest("A003"))
    for n in names:
        assert n not in html, f"bản tin lộ tên {n}"


def test_ban_tin_khong_chua_luong():
    html = digest_email.render_html(digest.build_digest("A003")).lower()
    for cam in ("base_salary", "vnd", "triệu đồng"):
        assert cam not in html


# ── tính đúng của số liệu ───────────────────────────────────────────────────
def test_tong_khop_va_khong_am():
    d = digest.build_digest("A003")
    assert d["n_flagged"] == d["n_high"] + d["n_medium"]
    assert d["n_flagged"] <= d["headcount"]
    assert all(u["n_flagged"] <= u["headcount"] for u in d["units"])
    assert d["n_units_flagged"] >= len(d["units"])


def test_ca_dai_dang_khong_vuot_qua_so_ca_cao():
    d = digest.build_digest("A003")
    assert 0 <= d["n_persistent_high"] <= d["n_high"]


def test_chay_lai_ra_dung_so_cu():
    """Tính điểm phải kiểm toán được — chạy hai lần phải ra y hệt."""
    a = digest.build_digest("A003")
    b = digest.build_digest("A003")
    assert a == b


def test_ky_dau_tien_khong_bia_ra_muc_thay_doi():
    snaps = sorted({r["snapshot_date"] for r in store.load_scores()})
    d = digest.build_digest("A003", snapshot=snaps[0])
    assert d["prev_snapshot_date"] is None
    assert d["d_high"] is None and d["d_flagged"] is None
    assert "kỳ đầu tiên" in digest_email.render_html(d)


# ── guard vẫn áp cho đoạn nhận xét ───────────────────────────────────────────
class _BiaSo:
    """Model bịa ra một con số không có trong dữ liệu."""
    def chat(self, messages, tools=None, tool_choice="auto"):
        return {"content": "Kỳ này có 999 người cần lưu ý, tăng mạnh so với trước.",
                "tool_calls": [], "usage": {}}


class _NgoanNgoan:
    def __init__(self, p):
        self.p = p

    def chat(self, messages, tools=None, tool_choice="auto"):
        return {"content": f"Trong kỳ, {self.p['n_flagged']} nhân sự cần lưu ý, "
                           f"trong đó {self.p['n_high']} ở mức Cao.",
                "tool_calls": [], "usage": {}}


def test_guard_chan_doan_nhan_xet_bia_so():
    p = digest.build_digest("A003")
    out = digest.narrative(_BiaSo(), p)
    assert out["guard_ok"] is False
    assert out["text"] is None                     # bỏ hẳn, không đưa vào mail
    assert digest_email.render_html(p, out["text"]).count("999") == 0


def test_doan_nhan_xet_dung_so_that_thi_qua():
    p = digest.build_digest("A003")
    out = digest.narrative(_NgoanNgoan(p), p)
    assert out["guard_ok"] is True
    assert str(p["n_flagged"]) in digest_email.render_html(p, out["text"])


class _Hong:
    def chat(self, *a, **k):
        raise RuntimeError("mất mạng")


def test_mat_mang_thi_ban_tin_van_ra():
    """Model hỏng không được kéo theo cả bản tin — số liệu vốn không cần model."""
    p = digest.build_digest("A003")
    out = digest.narrative(_Hong(), p)
    assert out["text"] is None and out["error"]
    html = digest_email.render_html(p, out["text"])
    assert str(p["n_flagged"]) in html


# ── tiêu đề mail ────────────────────────────────────────────────────────────
def test_tieu_de_co_so_lieu():
    s = digest_email.subject_line(digest.build_digest("A003"))
    assert "RetAIn" in s and "cần lưu ý" in s
