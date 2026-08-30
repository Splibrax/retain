# -*- coding: utf-8 -*-
"""
demo_numbers.py — in ra đúng những con số cần để cập nhật README, mockup giao diện
và kịch bản demo sau khi đổi trọng số.

Không gọi LLM, không tốn token. Chạy: python demo_numbers.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from agent import store, tools   # noqa: E402


def dong(t=""):
    print(t)


for aid in ("A001", "A002", "A003"):
    a = tools.build_actor(aid)
    r = tools.list_team_risk(a, limit=10)
    dong(f"===== {aid} · {a.actor_name} · {a.role} · {len(a.scope)} đơn vị =====")
    if r.get("error"):
        dong(f"  {r['error']}")
        dong()
        continue
    dong(f"kỳ {r['snapshot_date']} · {r['n_flagged']} cần lưu ý "
         f"({r['n_high']} Cao, {r['n_medium']} Trung bình) / {r['scope_headcount']} nhân sự "
         f"· {r['n_excluded']} bị loại")
    for i, it in enumerate(r["items"], 1):
        dong(f"  {i}. {it['score']:6.2f} {it['band_vi']:<11} {it['employee_id']}  "
             f"{it['full_name']:<24} | {it['top_factor']}")
    dong()

dong("===== PHÂN RÃ YẾU TỐ =====")
a1 = tools.build_actor("A001")
for eid in ("E001881", "E001889", "E001890"):
    r = tools.explain_employee_risk(a1, eid)
    if r.get("error"):
        dong(f"{eid}: {r['error']} — A001 KHÔNG nhìn thấy người này")
        continue
    dong(f"{eid} {r['full_name']} — {r['score']}/100 · {r['band_vi']}")
    for f in r["factors"]:
        dong(f"   {f['factor']:<10} rủi ro {f['risk_value']:.4f}  trọng số {f['weight_used']*100:.0f}%"
             f"   | {f['reason']}")
    dong()

dong("===== MÔ PHỎNG: HAI ĐÒN BẨY =====")
for eid in ("E001881", "E001889"):
    for sc in ("to_p50", "promotion", "kpi_recovery"):
        try:
            s = tools.simulate_intervention(a1, eid, sc, 85 if sc == "kpi_recovery" else None)
        except tools.ScenarioError as e:
            dong(f"{eid} {sc:14} lỗi: {e}")
            continue
        if s.get("error"):
            dong(f"{eid} {sc:14} {s['error']}")
            continue
        dong(f"{eid} {sc:14} {s['score_before']:6.2f} -> {s['score_after']:6.2f} "
             f"(giảm {s['score_delta']:6.2f})  {s['band_before_vi']} -> {s['band_after_vi']:<11} "
             f"lever={s['salary_lever_available']}  {s['delta_by_factor']}")
    dong()

dong("===== KHUYẾN NGHỊ (yếu tố trội → playbook) =====")
for eid in ("E001881", "E001889"):
    r = tools.suggest_actions(a1, eid)
    if r.get("error") or r.get("status") == "EXCLUDED":
        dong(f"{eid}: {r.get('error') or r.get('reason')}")
        continue
    dong(f"{eid} — yếu tố trội: {r['top_factor']} | {r['top_factor_reason']}")
    for k in ("P1", "P2", "P3"):
        dong(f"   {k}: {(r[k] or '(trống)')[:110]}")
    dong()

dong("===== CHẶN CHÉO =====")
a2 = tools.build_actor("A002")
d = tools.explain_employee_risk(a2, "E001881")
dong(f"A002 hỏi E001881 -> {d.get('error', 'KHÔNG BỊ CHẶN — kiểm lại phân quyền')}")
dong(f"A002 phạm vi: {len(a2.scope)} đơn vị")
r2 = tools.list_team_risk(a2, limit=5)
dong(f"A002 tự xem team mình: {r2['n_flagged']} cần lưu ý / {r2['scope_headcount']} nhân sự")
