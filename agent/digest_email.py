# -*- coding: utf-8 -*-
"""
digest_email.py — dựng HTML cho bản tin.

Viết theo lối email chứ không theo lối web. Outlook trên Windows render bằng
engine của Word: không có flexbox, không có grid, bỏ qua phần lớn <style> ở head,
không tải được font ngoài. Nên ở đây dùng bảng lồng bảng, CSS viết thẳng vào
thuộc tính style, và font hệ thống. Xấu mã nhưng hiện đúng ở nơi nó cần hiện đúng.
"""
from __future__ import annotations

RED = "#E4002B"
RED_DARK = "#A8001F"
INK = "#14161A"
INK_2 = "#565C66"
INK_3 = "#8A9099"
LINE = "#E5DFDB"
GROUND = "#F6F3F1"
CRIT = "#C0392B"
WARN = "#B26A00"
GOOD = "#1F7A5C"

FONT = "'Segoe UI',Roboto,Helvetica,Arial,sans-serif"

MONTH_VI = {1: "Tháng 1", 2: "Tháng 2", 3: "Tháng 3", 4: "Tháng 4", 5: "Tháng 5",
            6: "Tháng 6", 7: "Tháng 7", 8: "Tháng 8", 9: "Tháng 9", 10: "Tháng 10",
            11: "Tháng 11", 12: "Tháng 12"}


def _period(snapshot: str) -> str:
    try:
        y, m, _ = snapshot.split("-")
        return f"{MONTH_VI[int(m)]}/{y}"
    except Exception:
        return snapshot


def _delta(v, invert_good=True) -> str:
    """
    Hiển thị mức thay đổi so với kỳ trước. Tăng số ca là xấu → đỏ.
    Không có kỳ trước thì không bịa ra mũi tên.
    """
    if v is None:
        return f'<span style="color:{INK_3};font-size:12px">kỳ đầu tiên</span>'
    if v == 0:
        return f'<span style="color:{INK_3};font-size:12px">không đổi</span>'
    up = v > 0
    color = (CRIT if up else GOOD) if invert_good else (GOOD if up else CRIT)
    return (f'<span style="color:{color};font-size:12px;font-weight:600">'
            f'{"▲" if up else "▼"} {abs(v)} so với kỳ trước</span>')


def _stat(label: str, value, sub: str = "", color: str = INK) -> str:
    return (
        f'<td width="33%" valign="top" style="padding:14px 12px;background:{GROUND};'
        f'border:1px solid {LINE};border-radius:8px">'
        f'<div style="font-size:11px;letter-spacing:.06em;text-transform:uppercase;'
        f'color:{INK_3};font-family:{FONT}">{label}</div>'
        f'<div style="font-size:30px;line-height:1.15;font-weight:600;color:{color};'
        f'font-family:{FONT};padding-top:2px">{value}</div>'
        f'<div style="font-family:{FONT};padding-top:3px">{sub}</div></td>'
    )


def render_html(p: dict, narrative_text: str | None = None, app_url: str = "") -> str:
    """p là payload từ digest.build_digest()."""
    if p.get("error"):
        return _error_html(p)

    period = _period(p["snapshot_date"])
    pct = f'{p["n_flagged"] * 100 / p["headcount"]:.1f}'.replace(".", ",") if p["headcount"] else "0"

    # ── khối nhận xét (chỉ hiện khi guard cho qua) ──
    narr = ""
    if narrative_text:
        narr = (
            f'<tr><td style="padding:0 28px 4px">'
            f'<div style="border-left:3px solid {RED};padding:2px 0 2px 14px;'
            f'font-family:{FONT};font-size:14.5px;line-height:1.6;color:{INK}">'
            f'{narrative_text}</div></td></tr>'
        )

    # ── bảng đơn vị ──
    rows = []
    for i, u in enumerate(p["units"]):
        bg = "#FFFFFF" if i % 2 == 0 else GROUND
        hi = (f'<span style="color:{CRIT};font-weight:600">{u["n_high"]}</span>'
              if u["n_high"] else f'<span style="color:{INK_3}">0</span>')
        d = u["delta"]
        dtxt = ("—" if d == 0 else
                f'<span style="color:{CRIT if d > 0 else GOOD}">{"+" if d > 0 else ""}{d}</span>')
        rows.append(
            f'<tr style="background:{bg}">'
            f'<td style="padding:9px 12px;border-bottom:1px solid {LINE};font-family:{FONT};'
            f'font-size:13.5px;color:{INK}">{u["short"]}'
            f'<div style="font-size:11.5px;color:{INK_3};padding-top:1px">{u["name"]}</div></td>'
            f'<td align="right" style="padding:9px 8px;border-bottom:1px solid {LINE};'
            f'font-family:{FONT};font-size:13.5px;color:{INK_2}">{u["headcount"]}</td>'
            f'<td align="right" style="padding:9px 8px;border-bottom:1px solid {LINE};'
            f'font-family:{FONT};font-size:13.5px">{hi}</td>'
            f'<td align="right" style="padding:9px 8px;border-bottom:1px solid {LINE};'
            f'font-family:{FONT};font-size:13.5px;color:{INK}">{u["n_flagged"]}</td>'
            f'<td align="right" style="padding:9px 12px;border-bottom:1px solid {LINE};'
            f'font-family:{FONT};font-size:13.5px">{dtxt}</td></tr>'
        )
    unit_rows = "".join(rows) or (
        f'<tr><td colspan="5" style="padding:16px 12px;font-family:{FONT};font-size:13.5px;'
        f'color:{INK_3}">Không có đơn vị nào có nhân sự cần lưu ý trong kỳ này.</td></tr>')

    # ── dòng ca dai dẳng: con số EXCO cần nhất ──
    persist = ""
    if p.get("n_persistent_high"):
        persist = (
            f'<tr><td style="padding:4px 28px 18px">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
            f'<tr><td style="padding:12px 14px;background:#FCEDEF;border:1px solid #F3C9CF;'
            f'border-radius:8px;font-family:{FONT};font-size:13.5px;line-height:1.55;color:{INK}">'
            f'<b style="color:{RED}">{p["n_persistent_high"]} người</b> đã ở mức rủi ro Cao '
            f'trong cả ba kỳ gần nhất. Cảnh báo đã có từ trước, chưa có thay đổi trong dữ liệu.'
            f'</td></tr></table></td></tr>'
        )

    cta = ""
    if app_url:
        cta = (
            f'<tr><td align="center" style="padding:4px 28px 24px">'
            f'<a href="{app_url}" style="display:inline-block;background:{RED};color:#ffffff;'
            f'text-decoration:none;font-family:{FONT};font-size:14px;font-weight:600;'
            f'padding:11px 26px;border-radius:8px">Mở RetAIn để xem chi tiết</a></td></tr>'
        )

    return f"""<div style="margin:0;padding:0;background:{GROUND}">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
       style="background:{GROUND};padding:24px 12px">
<tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0"
       style="width:600px;max-width:100%;background:#FFFFFF;border:1px solid {LINE};border-radius:12px;overflow:hidden">

  <tr><td style="background:{RED};padding:18px 28px">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
      <td style="font-family:{FONT};color:#ffffff;font-size:19px;font-weight:700;letter-spacing:-.01em">
        RetAIn</td>
      <td align="right" style="font-family:{FONT};color:#ffffff;font-size:12.5px;opacity:.9">
        Bản tin giữ người · {period}</td>
    </tr></table>
  </td></tr>

  <tr><td style="padding:24px 28px 6px;font-family:{FONT}">
    <div style="font-size:12px;color:{INK_3};letter-spacing:.05em;text-transform:uppercase">
      Gửi {p["actor_name"]} · phạm vi {p["scope_units"]} đơn vị · {p["headcount"]} nhân sự</div>
    <div style="font-size:21px;font-weight:600;color:{INK};padding-top:6px;line-height:1.35">
      {p["n_flagged"]} người cần lưu ý trong kỳ {period}</div>
    <div style="font-size:13.5px;color:{INK_2};padding-top:4px">
      Chiếm {pct}% nhân sự trong phạm vi của anh/chị.</div>
  </td></tr>

  {narr}

  <tr><td style="padding:16px 28px 6px">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="6" border="0"><tr>
      {_stat("Mức Cao", p["n_high"], _delta(p["d_high"]), CRIT)}
      {_stat("Mức Trung bình", p["n_medium"], "", WARN)}
      {_stat("Đơn vị có ca", p["n_units_flagged"], _delta(p["d_flagged"]), INK)}
    </tr></table>
  </td></tr>

  {persist}

  <tr><td style="padding:14px 28px 6px;font-family:{FONT}">
    <div style="font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:{INK_3};
                padding-bottom:8px">Đơn vị cần chú ý trước</div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
           style="border:1px solid {LINE};border-radius:8px;border-collapse:separate">
      <tr style="background:{GROUND}">
        <th align="left" style="padding:8px 12px;font-family:{FONT};font-size:11px;
            letter-spacing:.05em;text-transform:uppercase;color:{INK_3};font-weight:600;
            border-bottom:1px solid {LINE}">Đơn vị</th>
        <th align="right" style="padding:8px;font-family:{FONT};font-size:11px;
            text-transform:uppercase;color:{INK_3};font-weight:600;border-bottom:1px solid {LINE}">HC</th>
        <th align="right" style="padding:8px;font-family:{FONT};font-size:11px;
            text-transform:uppercase;color:{INK_3};font-weight:600;border-bottom:1px solid {LINE}">Cao</th>
        <th align="right" style="padding:8px;font-family:{FONT};font-size:11px;
            text-transform:uppercase;color:{INK_3};font-weight:600;border-bottom:1px solid {LINE}">Cần lưu ý</th>
        <th align="right" style="padding:8px 12px;font-family:{FONT};font-size:11px;
            text-transform:uppercase;color:{INK_3};font-weight:600;border-bottom:1px solid {LINE}">Δ</th>
      </tr>
      {unit_rows}
    </table>
    <div style="font-size:12.5px;color:{INK_2};padding-top:10px;line-height:1.55">
      Yếu tố xuất hiện nhiều nhất trong kỳ: <b style="color:{INK}">{p.get("top_factor_vi") or "—"}</b>
      ({p.get("top_factor_count", 0)}/{p["n_flagged"]} trường hợp).
    </div>
  </td></tr>

  {cta}

  <tr><td style="padding:16px 28px 22px;border-top:1px solid {LINE};font-family:{FONT};
                 font-size:11.5px;color:{INK_3};line-height:1.65">
    <b style="color:{INK_2}">Bản tin này không nêu tên cá nhân.</b> Danh sách cụ thể chỉ xem được
    trong RetAIn, nơi phạm vi dữ liệu bị giới hạn theo tài khoản đăng nhập và mọi truy vấn đều
    được ghi nhật ký.<br><br>
    Nguồn: fact_flight_risk_score @ {p["snapshot_date"]}
    {"· so sánh với kỳ " + p["prev_snapshot_date"] if p.get("prev_snapshot_date") else ""}
    · {p["n_excluded"]} nhân sự bị loại theo quy tắc từ 2 thư cảnh cáo trong 12 tháng.<br>
    Điểm rủi ro là tín hiệu để rà soát sớm, không phải kết luận về cá nhân
    và không phải căn cứ cho bất kỳ quyết định nhân sự nào.
    {"<br>Playbook khuyến nghị đang là bản nháp, chờ HRBP duyệt." if p.get("playbook_is_draft") else ""}
  </td></tr>

</table>
</td></tr></table></div>"""


def _error_html(p: dict) -> str:
    msg = {
        "UNKNOWN_ACTOR": "Tài khoản không tồn tại trong danh mục người dùng.",
        "EMPTY_SCOPE": "Tài khoản không gắn với đơn vị hợp lệ nào — không có dữ liệu nào được trả về.",
    }.get(p.get("error"), "Không dựng được bản tin.")
    return (f'<div style="font-family:{FONT};padding:24px;color:{INK}">'
            f'<b>Không gửi bản tin cho {p.get("actor_id")}.</b><br>{msg}</div>')


def subject_line(p: dict) -> str:
    if p.get("error"):
        return f'RetAIn — không dựng được bản tin cho {p.get("actor_id")}'
    s = f'RetAIn {_period(p["snapshot_date"])} — {p["n_flagged"]} người cần lưu ý'
    if p.get("n_high"):
        s += f', {p["n_high"]} mức Cao'
    return s
