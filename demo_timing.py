# -*- coding: utf-8 -*-
"""
demo_timing.py — đo ĐÚNG ba câu hỏi của kịch bản demo, trên ĐÚNG đường sẽ diễn.

BÀI HỌC NGÀY 1/9 — VÌ SAO PHẢI CÓ --url:
bản đầu của file này gọi thẳng runtime.answer() trong máy, tức là
    python → GreenNode MaaS
Nhưng lúc demo, đường đi là
    trình duyệt → container AgentBase trên cloud → MaaS
Khác hẳn: thêm một chặng mạng, và nếu endpoint đã thu về 0 bản chạy thì còn
thêm cả thời gian khởi động nguội. Đo một đường rồi diễn trên đường khác là
kiểu sai tệ nhất, vì con số ra vẫn trông hợp lý.

    # đo đường THẬT (mặc định — dùng cái này)
    python demo_timing.py --url https://<endpoint>/

    # đo đường trong máy, để so xem chặng container tốn bao nhiêu
    python demo_timing.py --local

    python demo_timing.py --url <...> --runs 5
    python demo_timing.py --url <...> --warmup-only     # chỉ hâm nóng, không đo

HÂM NÓNG: trước khi đo, gọi /health cho đến khi endpoint trả lời, rồi mới bấm
giờ. Nếu không, vòng 1 đo cả thời gian dựng container — con số vô nghĩa cho một
buổi demo mà anh đã hâm nóng từ trước.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Ép UTF-8 cho đầu ra ──────────────────────────────────────────────────────
# Windows mặc định mã hoá đầu ra ĐÃ CHUYỂN HƯỚNG bằng cp1252 (ống dẫn, ghi ra
# file). In thẳng ra màn hình thì không sao, nhưng
#     python run_eval.py | Select-String "C03"
#     python run_eval.py > ket_qua.txt
# là vỡ ngay ở chữ "Bộ" — UnicodeEncodeError, không chạy được dòng nào.
#
# Sửa ở đây chứ không bắt người dùng nhớ đặt PYTHONIOENCODING: một công cụ chỉ
# chạy được khi in thẳng ra màn hình thì không dùng để ghi log lúc 24/9 được.
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:      # noqa: BLE001 — môi trường lạ thì thôi, không chặn
            pass


from agent import store, tools          # noqa: E402

BUDGET_S = 90          # slide 4 có 90 giây cho cả ba câu
WARMUP_TIMEOUT = 180   # container nguội có thể mất vài phút để dựng


# ══════════════════════════════════════════════════════════════════════════
def demo_script(actor_id: str, snap: str):
    """Dựng đúng ba câu của kịch bản, tên người lấy từ dữ liệu hiện tại."""
    actor = tools.build_actor(actor_id)
    rows = sorted(store.rows_for(snap, actor.scope),
                  key=lambda r: -float(r["flight_risk_score"]))
    if len(rows) < 2:
        raise SystemExit(f"Actor {actor_id} có ít hơn 2 người — không dựng được kịch bản.")

    underpaid = next((r for r in rows if float(r["salary_gap_to_p50_pct"]) < -0.2), rows[0])
    well_paid = next((r for r in rows
                      if float(r["salary_gap_to_p50_pct"]) >= 0
                      and r["flight_risk_band"] == "High"), None)
    if well_paid is None:
        print("⚠ Không tìm thấy người 'lương tốt mà vẫn rủi ro cao' trong phạm vi "
              f"{actor_id}. Dùng người rủi ro cao thứ hai — cảnh tương phản của demo "
              "sẽ KHÔNG đúng như kịch bản.\n")
        well_paid = rows[1]

    n1 = store.display_name(underpaid["employee_id"])
    n2 = store.display_name(well_paid["employee_id"])
    return [
        ("Câu 1 — mở màn", "Đội tôi ai đang rủi ro cao nhất?", False),
        ("Câu 2 — đòn bẩy tiền", f"Nếu đưa lương {n1} về P50 thì sao?", False),
        ("Câu 3 — đòn bẩy ngược", f"Còn {n2}?", True),   # True = cần lịch sử
    ]


# ══════════════════════════════════════════════════════════════════════════
# Gọi qua HTTP — đúng đường trình duyệt sẽ đi
# ══════════════════════════════════════════════════════════════════════════
def _post_chat(base: str, actor_id: str, text: str, history):
    body = json.dumps({"message": text, "history": history},
                      ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        base.rstrip("/") + "/chat", data=body, method="POST",
        headers={"Content-Type": "application/json; charset=utf-8",
                 "X-Actor-Id": actor_id},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode("utf-8"))


def warmup(base: str) -> float:
    """
    Gọi /health đến khi endpoint trả lời. Trả về số giây phải chờ.

    Con số này CHÍNH LÀ thứ đáng sợ nhất cho buổi demo: nó là thời gian dựng
    container từ 0 bản chạy. Nếu nó lớn, phải hâm nóng trước khi lên sân khấu,
    hoặc đặt min replicas = 1.
    """
    print(f"  hâm nóng {base} ", end="", flush=True)
    t0 = time.time()
    last = None
    while time.time() - t0 < WARMUP_TIMEOUT:
        try:
            with urllib.request.urlopen(base.rstrip("/") + "/health", timeout=30) as r:
                data = json.loads(r.read().decode("utf-8"))
            dt = time.time() - t0
            print(f"→ {dt:.0f}s · mode={data.get('mode')} · build={data.get('build', 'KHÔNG CÓ NHÃN')}")
            if data.get("mode") != "real":
                raise SystemExit(
                    f"\n  ✗ /health trả mode={data.get('mode')!r}, KHÔNG phải 'real'.\n"
                    "    Agent đang chạy MockLLM — vẫn trả lời trôi chảy nhưng SAI hoàn toàn.\n"
                    "    Sửa biến môi trường trên runtime rồi deploy lại."
                )
            return dt
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
        except Exception as e:                       # noqa: BLE001
            last = f"{type(e).__name__}"
        print(".", end="", flush=True)
        time.sleep(3)
    raise SystemExit(f"\n  ✗ Endpoint không trả lời sau {WARMUP_TIMEOUT}s (lỗi cuối: {last}).")


# ══════════════════════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=None,
                    help="Địa chỉ endpoint trên cloud. Không có thì phải dùng --local.")
    ap.add_argument("--local", action="store_true",
                    help="Gọi thẳng trong máy, KHÔNG qua container. Chỉ để so sánh.")
    ap.add_argument("--actor", default="A001")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--warmup-only", action="store_true",
                    help="Chỉ hâm nóng endpoint rồi thoát — chạy lệnh này lúc T−30.")
    args = ap.parse_args()

    if not args.url and not args.local:
        raise SystemExit(
            "Phải chọn một đường đo:\n"
            "  --url https://<endpoint>/   ← đường THẬT, dùng cái này\n"
            "  --local                     ← chỉ để so sánh, KHÔNG phải đường sẽ demo"
        )
    if args.url and args.local:
        raise SystemExit("Chọn một trong hai, không phải cả hai.")

    warm = 0.0
    if args.url:
        warm = warmup(args.url)
        if args.warmup_only:
            print(f"\n  ✓ Endpoint đã nóng. Giữ tab mở, gọi lại lệnh này sau ~10 phút "
                  "nếu chưa đến lượt diễn.")
            return
        llm = None
    else:
        if os.environ.get("RETAIN_MOCK") == "1":
            raise SystemExit("RETAIN_MOCK=1 — đo độ trễ bằng MockLLM là vô nghĩa.")
        from agent import runtime                    # noqa: PLC0415
        from agent.llm import make_llm               # noqa: PLC0415
        llm = make_llm(mock=False)

    snap = store.latest_snapshot()
    script = demo_script(args.actor, snap)
    duong = f"HTTP → {args.url}" if args.url else "trong máy (KHÔNG qua container)"

    print(f"\nĐo kịch bản demo — actor {args.actor}, snapshot {snap}, {args.runs} vòng")
    print(f"Đường đo: {duong}")
    print("=" * 74)
    for label, q, _ in script:
        print(f"  {label}: {q}")
    print()

    times = {label: [] for label, _, _ in script}
    calls = {label: [] for label, _, _ in script}
    toks = {label: [] for label, _, _ in script}
    # TÁCH prompt / completion. Token tổng che mất điều quan trọng nhất: thời
    # gian sinh chữ tỉ lệ với phần COMPLETION, không phải với tổng. Ngày 1/9,
    # tổng của câu 2 nhích lên sau khi rút gọn lời nhắc — không tách thì không
    # biết là do model viết dài hơn hay do lời nhắc dài hơn.
    outs = {label: [] for label, _, _ in script}

    for run in range(1, args.runs + 1):
        history = []
        print(f"  vòng {run}: ", end="", flush=True)
        for label, q, needs_history in script:
            t0 = time.time()
            if args.url:
                res = _post_chat(args.url, args.actor, q, history if needs_history else None)
            else:
                from agent import runtime             # noqa: PLC0415
                res = runtime.answer(llm, args.actor, q, history if needs_history else None)
            dt = time.time() - t0

            times[label].append(dt)
            calls[label].append(len(res.get("tool_calls") or []))
            u = res.get("usage") or {}
            toks[label].append(u.get("prompt", 0) + u.get("completion", 0))
            outs[label].append(u.get("completion", 0))

            history.append({"role": "user", "content": q})
            history.append({"role": "assistant", "content": res.get("answer", "")})
            print(f"{dt:.0f}s ", end="", flush=True)
        print()

    print("\n" + "=" * 74)
    print(f"  {'':22} {'trung vị':>10} {'nhanh nhất':>11} {'CHẬM NHẤT':>11} "
          f"{'công cụ':>8} {'tổng tok':>9} {'MODEL VIẾT':>11}")
    med_total = worst_total = 0.0
    for label, _, _ in script:
        t = times[label]
        med = statistics.median(t)
        med_total += med
        worst_total += max(t)
        out_med = statistics.median(outs[label])
        print(f"  {label:22} {med:9.0f}s {min(t):10.0f}s {max(t):10.0f}s "
              f"{statistics.median(calls[label]):8.0f} {statistics.median(toks[label]):9,.0f} "
              f"{out_med:11,.0f}")

    print("  " + "-" * 70)
    print(f"  {'CẢ BA CÂU':22} {med_total:9.0f}s {'':10} {worst_total:10.0f}s")

    # Kịch bản thật chỉ gõ câu 2 và 3 — câu 1 đã chạy sẵn từ slide 3.
    on_stage_med = statistics.median(times[script[1][0]]) + statistics.median(times[script[2][0]])
    on_stage_worst = max(times[script[1][0]]) + max(times[script[2][0]])
    print(f"  {'CHỈ CÂU 2 + 3 (gõ thật)':22} {on_stage_med:9.0f}s {'':10} {on_stage_worst:10.0f}s")

    # Tốc độ sinh chữ — con số nói lên mọi thứ về việc rút ngắn có ăn hay không.
    all_out = [v for label, _, _ in script for v in outs[label]]
    all_t = [v for label, _, _ in script for v in times[label]]
    if sum(all_out):
        print(f"\n  Tốc độ sinh chữ: ~{sum(all_out) / sum(all_t):.0f} token/giây. "
              f"Muốn nhanh hơn thì phải VIẾT NGẮN HƠN — không có cách nào khác.")

    print()
    if args.url and warm > 10:
        print(f"  ⚠ Hâm nóng mất {warm:.0f}s — endpoint đang thu về 0 bản chạy.")
        print("    Trên sân khấu, câu hỏi đầu tiên sẽ phải chờ chừng đó NẾU chưa hâm nóng.")
        print("    Chạy `--warmup-only` lúc T−30 và T−10, hoặc đặt min replicas = 1.")

    if on_stage_worst <= BUDGET_S * 0.6:
        print(f"  ✓ Câu 2+3 lần chậm nhất {on_stage_worst:.0f}s / {BUDGET_S}s — còn dư "
              "thời gian để nói.")
    elif on_stage_worst <= BUDGET_S:
        print(f"  ⚠ Câu 2+3 lần chậm nhất {on_stage_worst:.0f}s / {BUDGET_S}s — VỪA ĐỦ, "
              "không có biên.")
        print("    Bấm Enter TRƯỚC khi nói, và tập nói chèn vào lúc đang chờ.")
    else:
        print(f"  ✗ Chỉ hai câu đã {on_stage_worst:.0f}s, vượt {BUDGET_S}s. Bỏ tiếp một câu, "
              "hoặc dùng video.")

    print("\n  LƯU Ý: đo trên mạng hiện tại. Mạng hội trường thường chậm hơn —")
    print("  chạy lại NGAY TẠI CHỖ ngày 24/9 và sửa các mốc giờ trong bảng điều phối.")


if __name__ == "__main__":
    main()
