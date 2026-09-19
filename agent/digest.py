# -*- coding: utf-8 -*-
"""
digest.py — bản tin định kỳ gửi qua email (kênh ĐẨY).

Vì sao có file này: chatbot là mô hình KÉO — người dùng phải nhớ ra là có nó,
mở ra, và nghĩ câu hỏi. Cán bộ quản lý cấp cao sẽ không làm việc đó. Muốn chạm
tới tầng đó thì thông tin phải tự tìm đến họ, ở nơi họ vốn đã đọc: hộp thư.

Ba quyết định thiết kế, cố ý:

1. KHÔNG NÊU TÊN AI. Email bị chuyển tiếp, in ra, để mở trên màn hình họp.
   Bản tin chỉ có số tổng hợp cấp đơn vị. Muốn biết ai thì mở RetAIn — ở đó
   phạm vi được kiểm soát và mọi truy vấn đều được ghi log.

2. PHẠM VI ĐI QUA ĐÚNG resolve_scope() NHƯ KÊNH CHAT. Đổi kênh không được
   phép đổi quyền. Cùng một lõi, khác lớp vỏ.

3. TOÀN BỘ SỐ TÍNH TẠI CHỖ, 0 TOKEN. Model chỉ được mời vào để viết một đoạn
   nhận xét ngắn, và đoạn đó vẫn phải qua guard như mọi câu trả lời khác.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from . import store
from .scope import resolve_scope

# Nhãn tiếng Việt của 4 yếu tố — dùng chung cho cả email và đoạn nhận xét.
FACTOR_VI = {
    "salary": "khoảng cách lương so với thị trường",
    "kpi": "điểm KPI",
    "freeze": "thời gian bị dừng xét điều chỉnh lương",
    "seniority": "cửa sổ rủi ro theo thâm niên",
}

BAND_VI = {"High": "Cao", "Medium": "Trung bình", "Low": "Thấp"}


def _dept_names() -> dict:
    """
    dept_code → (tên đầy đủ, tên viết tắt, tên khối lvl1).
    Đọc từ dim_dept_hierarchy: mỗi chuỗi cho ta cả tên lẫn khối cha.
    """
    out = {}
    for chain in _hierarchy_rows():
        for lvl in ("lvl1", "lvl2", "lvl3", "lvl4", "lowest"):
            code = chain.get(f"{lvl}_code")
            if not code:
                continue
            out.setdefault(code, (
                chain.get(f"{lvl}_name") or code,
                chain.get(f"{lvl}_short") or code,
                chain.get("lvl1_name") or "",
            ))
    return out


def _hierarchy_rows():
    import csv
    import os
    path = os.path.join(store.DATA_DIR, "dim_dept_hierarchy.csv")
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _top_factor(row: dict) -> str:
    """
    Yếu tố đóng góp nhiều nhất vào điểm của một người.

    Đóng góp = mức rủi ro thành phần × trọng số THỰC DÙNG (không phải trọng số
    gốc — khi thiếu dữ liệu, engine đã chuẩn hoá lại trọng số).
    """
    best, best_val = None, -1.0
    for k in ("salary", "kpi", "freeze", "seniority"):
        try:
            v = float(row.get(f"risk_component_{k}") or 0) * float(row.get(f"weight_{k}_used") or 0)
        except (TypeError, ValueError):
            v = 0.0
        if v > best_val:
            best, best_val = k, v
    return best or "salary"


def _snapshots_desc() -> list[str]:
    return sorted({r["snapshot_date"] for r in store.load_scores()}, reverse=True)


def _bucket(scope: frozenset[str], snapshot: str) -> dict:
    """Đếm theo band + gom theo đơn vị cho MỘT kỳ."""
    n = {"High": 0, "Medium": 0, "Low": 0}
    excluded = 0
    by_unit = defaultdict(lambda: {"hc": 0, "high": 0, "medium": 0})
    high_ids, flagged_ids = set(), set()
    factors = Counter()

    for r in store.rows_for(snapshot, scope):
        band = r.get("flight_risk_band") or "Low"
        u = by_unit[r["dept_code"]]
        u["hc"] += 1
        if r["is_excluded_from_risk_list"]:
            excluded += 1
            continue
        n[band] = n.get(band, 0) + 1
        if band == "High":
            u["high"] += 1
            high_ids.add(r["employee_id"])
        elif band == "Medium":
            u["medium"] += 1
        if band in ("High", "Medium"):
            flagged_ids.add(r["employee_id"])
            factors[_top_factor(r)] += 1

    return {
        "n": n, "excluded": excluded, "by_unit": dict(by_unit),
        "high_ids": high_ids, "flagged_ids": flagged_ids, "factors": factors,
        "headcount": sum(u["hc"] for u in by_unit.values()),
    }


def build_digest(actor_id: str, snapshot: str | None = None, top_units: int = 5) -> dict:
    """
    Dựng toàn bộ số liệu cho bản tin. Không gọi LLM, không tốn token.

    Trả về dict — cùng hình dạng payload như các tool khác, để đoạn nhận xét
    của model đi qua ĐÚNG guard đang dùng cho kênh chat.
    """
    actor = store.load_actors().get(actor_id)
    if not actor:
        return {"error": "UNKNOWN_ACTOR", "actor_id": actor_id}

    scope = resolve_scope(actor.get("dept_scope_code", ""))
    if not scope:                       # fail closed — y hệt kênh chat
        return {"error": "EMPTY_SCOPE", "actor_id": actor_id,
                "actor_name": actor.get("actor_name", ""),
                "scope_code": actor.get("dept_scope_code", "")}

    snaps = _snapshots_desc()
    cur = snapshot or snaps[0]
    prev = next((s for s in snaps if s < cur), None)

    now = _bucket(scope, cur)
    was = _bucket(scope, prev) if prev else None
    names = _dept_names()

    # Ca dai dẳng: mức Cao ở cả 3 kỳ gần nhất. Đây là con số EXCO cần —
    # không phải "có bao nhiêu ca", mà "có bao nhiêu ca đã cảnh báo mà chưa ai xử lý".
    older = [s for s in snaps if s < (prev or cur)][:1]
    persistent = 0
    if was and older:
        two_ago = _bucket(scope, older[0])
        persistent = len(now["high_ids"] & was["high_ids"] & two_ago["high_ids"])

    # Đơn vị nóng nhất: ưu tiên số ca Cao, rồi tới tổng số ca cần lưu ý.
    units = []
    for code, u in now["by_unit"].items():
        flagged = u["high"] + u["medium"]
        if flagged == 0:
            continue
        prev_u = (was["by_unit"].get(code) if was else None) or {"high": 0, "medium": 0}
        units.append({
            "dept_code": code,
            "name": names.get(code, (code, code, ""))[0],
            "short": names.get(code, (code, code, ""))[1],
            "headcount": u["hc"],
            "n_high": u["high"],
            "n_medium": u["medium"],
            "n_flagged": flagged,
            "delta": flagged - (prev_u["high"] + prev_u["medium"]),
        })
    units.sort(key=lambda x: (-x["n_high"], -x["n_flagged"], x["name"]))

    top_factor = now["factors"].most_common(1)
    n_flagged = now["n"]["High"] + now["n"]["Medium"]
    prev_flagged = (was["n"]["High"] + was["n"]["Medium"]) if was else None

    return {
        "actor_id": actor_id,
        "actor_name": actor.get("actor_name", ""),
        "role": actor.get("role", ""),
        "scope_code": actor.get("dept_scope_code", ""),
        "scope_units": len(scope),
        "snapshot_date": cur,
        "prev_snapshot_date": prev,
        "headcount": now["headcount"],
        "n_high": now["n"]["High"],
        "n_medium": now["n"]["Medium"],
        "n_flagged": n_flagged,
        "n_excluded": now["excluded"],
        "d_high": (now["n"]["High"] - was["n"]["High"]) if was else None,
        "d_flagged": (n_flagged - prev_flagged) if was else None,
        "n_new_high": len(now["high_ids"] - was["high_ids"]) if was else None,
        "n_persistent_high": persistent,
        "top_factor": top_factor[0][0] if top_factor else None,
        "top_factor_vi": FACTOR_VI.get(top_factor[0][0]) if top_factor else None,
        "top_factor_count": top_factor[0][1] if top_factor else 0,
        "units": units[:top_units],
        "n_units_flagged": len(units),
        "playbook_is_draft": store.playbook_is_draft(),
    }


# ── đoạn nhận xét bằng ngôn ngữ tự nhiên (tuỳ chọn) ──────────────────────────

NARRATIVE_PROMPT = """Bạn viết một đoạn nhận xét ngắn mở đầu bản tin nhân sự định kỳ
gửi cho lãnh đạo cấp khối tại một ngân hàng Việt Nam.

Viết ĐÚNG 2 đến 3 câu, tiếng Việt, giọng điềm tĩnh, không kịch tính, không chào hỏi.
Nêu bức tranh chung và điều đáng chú ý nhất trong kỳ.

TUYỆT ĐỐI:
- Chỉ dùng con số có trong dữ liệu dưới đây. Không tự cộng trừ, không tính phần trăm,
  không ước lượng, không suy ra số mới.
- Không nêu tên người, không nêu mã nhân viên.
- Không hứa hẹn giữ được người, không kết luận về kỷ luật hay pháp lý.
- Không khuyên tăng lương một mức cụ thể.

Dữ liệu kỳ này:
{payload}"""


def narrative(llm, payload: dict) -> dict:
    """
    Mời model viết đoạn mở đầu. Vẫn phải qua guard — kênh khác không có nghĩa là
    luật khác. Guard trượt thì bỏ hẳn đoạn nhận xét: bản tin vẫn đầy đủ số liệu,
    chỉ thiếu một đoạn văn. Thà cụt còn hơn sai.
    """
    from . import guard

    import json
    facts = {k: v for k, v in payload.items() if k not in ("units",)}
    facts["units"] = [{k: u[k] for k in ("short", "n_high", "n_flagged", "headcount", "delta")}
                      for u in payload.get("units", [])]
    msg = NARRATIVE_PROMPT.format(payload=json.dumps(facts, ensure_ascii=False, indent=1))

    try:
        resp = llm.chat([{"role": "user", "content": msg}])
    except Exception as e:                       # mạng hỏng thì bản tin vẫn phải ra
        return {"text": None, "guard_ok": None, "error": str(e)[:200], "usage": {}}

    text = (resp.get("content") or "").strip()
    report = guard.verify(text, payload)
    return {
        "text": text if report["ok"] else None,
        "guard_ok": report["ok"],
        "guard_detail": report,
        "usage": resp.get("usage", {}),
    }
