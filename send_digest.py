# -*- coding: utf-8 -*-
"""
send_digest.py — chạy bản tin định kỳ.

Dùng:
    python send_digest.py --actor A003                    # xuất ra file HTML, mở bằng trình duyệt
    python send_digest.py --all --out out/                 # tất cả tài khoản trong dim_actor
    python send_digest.py --actor A003 --narrative         # kèm đoạn nhận xét do model viết
    python send_digest.py --actor A003 --send hrbp@msb.com # gửi thật qua SMTP

Gửi thật cần 4 biến môi trường (đặt trong .env):
    SMTP_HOST  SMTP_PORT  SMTP_USER  SMTP_PASSWORD
Thiếu bất kỳ biến nào thì lệnh --send dừng lại và báo, KHÔNG im lặng bỏ qua.

Vì sao tách khỏi main.py: bản tin chạy theo lịch (mỗi tháng một lần), không chạy
theo request. Nhét vào web server thì phải nuôi thêm một scheduler bên trong
container — thêm một thứ có thể hỏng mà không đổi lấy gì.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from agent import digest, digest_email, store  # noqa: E402


def build(actor_id: str, with_narrative: bool, app_url: str):
    payload = digest.build_digest(actor_id)
    text, usage = None, {}
    if with_narrative and not payload.get("error"):
        from agent.llm import make_llm
        n = digest.narrative(make_llm(mock=os.environ.get("RETAIN_MOCK") == "1"), payload)
        if n.get("error"):
            print(f"   ! không gọi được model: {n['error']} — bản tin vẫn ra, không có đoạn nhận xét")
        elif n["guard_ok"] is False:
            print(f"   ! guard chặn đoạn nhận xét: {n['guard_detail']} — bỏ đoạn này")
        text, usage = n["text"], n.get("usage") or {}
    return payload, digest_email.render_html(payload, text, app_url), usage


def smtp_send(to_addr: str, subject: str, html: str) -> None:
    import smtplib
    from email.message import EmailMessage

    need = ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD")
    missing = [k for k in need if not os.environ.get(k)]
    if missing:
        raise SystemExit(f"Thiếu biến môi trường để gửi mail: {', '.join(missing)}")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.environ.get("SMTP_FROM") or os.environ["SMTP_USER"]
    msg["To"] = to_addr
    msg.set_content("Bản tin RetAIn ở dạng HTML. Vui lòng mở bằng ứng dụng thư hỗ trợ HTML.")
    msg.add_alternative(html, subtype="html")

    port = int(os.environ["SMTP_PORT"])
    cls = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP
    with cls(os.environ["SMTP_HOST"], port, timeout=30) as s:
        if port != 465:
            s.starttls()
        s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        s.send_message(msg)


def main():
    ap = argparse.ArgumentParser(description="Bản tin giữ người định kỳ của RetAIn")
    ap.add_argument("--actor", help="mã tài khoản, ví dụ A003")
    ap.add_argument("--all", action="store_true", help="dựng cho mọi tài khoản trong dim_actor")
    ap.add_argument("--out", default="out", help="thư mục xuất file HTML")
    ap.add_argument("--narrative", action="store_true", help="kèm đoạn nhận xét do model viết")
    ap.add_argument("--send", metavar="EMAIL", help="gửi thật tới địa chỉ này qua SMTP")
    ap.add_argument("--app-url", default=os.environ.get("RETAIN_APP_URL", ""),
                    help="link mở RetAIn, hiện thành nút trong mail")
    a = ap.parse_args()

    if not a.actor and not a.all:
        ap.error("cần --actor hoặc --all")

    from agent.llm import load_dotenv
    load_dotenv()

    actors = list(store.load_actors()) if a.all else [a.actor]
    outdir = Path(a.out)
    outdir.mkdir(parents=True, exist_ok=True)
    total_in = total_out = 0

    for aid in actors:
        payload, html, usage = build(aid, a.narrative, a.app_url)
        subject = digest_email.subject_line(payload)
        path = outdir / f"digest_{aid}.html"
        path.write_text(html, encoding="utf-8")

        total_in += usage.get("prompt_tokens") or 0
        total_out += usage.get("completion_tokens") or 0

        if payload.get("error"):
            print(f"{aid}: {payload['error']} — không có gì để gửi (fail-closed)")
        else:
            print(f"{aid}: {payload['n_flagged']} cần lưu ý / {payload['headcount']} nhân sự "
                  f"({payload['n_high']} Cao) · {payload['scope_units']} đơn vị → {path}")

        if a.send:
            if payload.get("error"):
                print("   bỏ qua gửi mail vì bản tin lỗi")
            else:
                smtp_send(a.send, subject, html)
                print(f"   đã gửi tới {a.send}")

    if a.narrative:
        print(f"\nToken cho đoạn nhận xét: {total_in} vào + {total_out} ra "
              f"(toàn bộ số liệu tính tại chỗ, 0 token)")


if __name__ == "__main__":
    main()
