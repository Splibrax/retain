# -*- coding: utf-8 -*-
"""
demo_smoke.py — chạy 4 cảnh demo (BLUEPRINT §14) bằng CLI, CHƯA cần LLM.

Mục đích: chứng minh phần logic + phân quyền đã đúng trước khi nối AI vào.
Chạy:  python3 demo_smoke.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("RETAIN_DATA_DIR",
                      os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))

from agent import store, tools  # noqa: E402

LINE = "─" * 78


def h(t):
    print(f"\n{LINE}\n{t}\n{LINE}")


def main():
    snap = store.latest_snapshot()
    print(f"Kỳ dữ liệu gần nhất: {snap}")

    # ── Cảnh 1 — Phát hiện ──────────────────────────────────────────────
    a001 = tools.build_actor("A001")
    h(f'CẢNH 1 · PHÁT HIỆN — {a001.actor_name} ({a001.role}), scope {a001.scope_code}'
      f' → {len(a001.scope)} đơn vị\n"Team mình tháng này có ai đang có dấu hiệu muốn đi không?"')
    r = tools.list_team_risk(a001, limit=5)
    print(f"  Phạm vi: {r['scope_headcount']} nhân sự → {r['n_flagged']} cần lưu ý "
          f"({r['n_high']} High, {r['n_medium']} Medium) · loại trừ {r['n_excluded']}")
    for i, it in enumerate(r["items"], 1):
        print(f"   {i}. {it['full_name']:<12} {it['score']:>6.2f}/100  {it['band']:<7} {it['top_factor']}")
    print(f"  audit_id={r['audit_id']}")

    # ── Cảnh 2 — Giải thích ─────────────────────────────────────────────
    target = r["items"][0]["employee_id"] if r["items"] else "E001881"
    h(f'CẢNH 2 · GIẢI THÍCH\n"Sao bạn {target} lại bị chấm cao thế?"')
    e = tools.explain_employee_risk(a001, target)
    print(f"  {e['full_name']} — {e['score']}/100, band {e['band']}")
    print(f"  {'Yếu tố':<12}{'Mức rủi ro':>12}{'Trọng số':>11}   Diễn giải")
    for f in e["factors"]:
        print(f"  {f['factor']:<12}{f['risk_value']:>12.4f}{f['weight_used']*100:>10.0f}%   {f['reason']}")
    print(f"  missing_features: '{e['missing_features']}' · audit_id={e['audit_id']}")

    # ── Cảnh 3 — Mô phỏng ───────────────────────────────────────────────
    h(f'CẢNH 3 · THỬ PHƯƠNG ÁN  ⭐\n"Nếu kéo lương bạn ấy về đúng thị trường thì rủi ro còn bao nhiêu?"')
    for sc, val in (("to_p50", None), ("raise_pct", 0.10), ("kpi_recovery", 85)):
        s = tools.simulate_intervention(a001, target, sc, val)
        arrow = f"{s['score_before']:.2f} → {s['score_after']:.2f}"
        print(f"  {s['scenario_label']:<34} {arrow:<18} giảm {s['score_delta']:>5.2f} điểm"
              f"   ({s['band_before']} → {s['band_after']})")
        print(f"     phần giảm đến từ: {s['delta_by_factor']}")
    print(f"\n  ⚠️  {s['disclaimer']}")

    # ── Cảnh 4 — Chặn chéo đơn vị ───────────────────────────────────────
    a002 = tools.build_actor("A002")
    h(f'CẢNH 4 · CHẶN — {a002.actor_name} ({a002.role}), scope {a002.scope_code}'
      f' → {len(a002.scope)} đơn vị\n"Bên team anh Minh có bạn nào đang lung lay không, để anh còn liệu?"')
    d = tools.explain_employee_risk(a002, target)
    print(f"  Kết quả: {d}")
    print("  → Không lộ tên, không lộ điểm, không xác nhận người đó có tồn tại.")

    d2 = tools.simulate_intervention(a002, target, "to_p50")
    print(f"  Thử lách bằng mô phỏng: {d2['error']} (chặn ở cùng một tầng)")

    # ── Audit log ───────────────────────────────────────────────────────
    h("AUDIT LOG — bằng chứng cho câu hỏi governance")
    print(f"  {'audit_id':<10}{'actor':<7}{'role':<7}{'tool':<26}{'rows':>5}  denied")
    for a in tools.AUDIT_LOG:
        print(f"  {a['audit_id']:<10}{a['actor_id']:<7}{a['actor_role']:<7}"
              f"{a['tool_called']:<26}{a['n_rows_returned']:>5}  {a['was_denied']}")

    # ── So sánh scope các actor ─────────────────────────────────────────
    h("KIỂM TRA PHÂN QUYỀN — mỗi actor thấy bao nhiêu")
    for aid in ("A001", "A002", "A003", "A004", "A005", "A999"):
        a = tools.build_actor(aid)
        n = sum(1 for _ in store.rows_for(snap, a.scope))
        sees = "có" if any(x["employee_id"] == target
                           for x in store.rows_for(snap, a.scope)) else "KHÔNG"
        print(f"  {aid} {a.role:<5} scope={a.scope_code:<14} "
              f"{len(a.scope):>3} đơn vị · {n:>5} nhân sự · thấy {target}: {sees}")


if __name__ == "__main__":
    main()
