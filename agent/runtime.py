# -*- coding: utf-8 -*-
"""
runtime.py — vòng điều phối agent Kiểu 2 (multi-step), BLUEPRINT §4.3.

Thứ tự BẮT BUỘC, không được đổi:

    1. Xác thực danh tính        → build_actor()
    2. Resolve phạm vi dữ liệu   → actor.scope        ★ LLM CHƯA THAM GIA
    3. LLM chọn tool             (schema không có tham số phạm vi)
    4. Tool chạy SQL đã lọc theo scope của bước 2
    5. LLM diễn đạt kết quả
    6. Hậu kiểm số + từ ngữ (guard) — sai thì viết lại MỘT lần
    7. Ghi audit, trả lời

Bước 2 xảy ra TRƯỚC bước 3. Đó là lý do người hỏi không "hỏi khéo" sang đơn vị khác được.
"""
from __future__ import annotations

import json

from . import guard, registry, tools
from .prompt import build_messages

MAX_TOOL_ROUNDS = 3      # chặn vòng lặp vô hạn nếu model cứ gọi tool


def answer(llm, actor_id: str, user_text: str, history=None) -> dict:
    # ── B1+B2: danh tính → phạm vi. Trước mọi thứ khác. ──────────────────
    actor = tools.build_actor(actor_id)

    if not actor.scope:
        return {
            "answer": ("Không xác định được phạm vi dữ liệu của tài khoản đang đăng nhập. "
                       "RetAIn không trả lời khi chưa xác định được phạm vi."),
            "actor": actor.actor_id, "role": actor.role,
            "tool_calls": [], "verified": True, "usage": {},
        }

    messages = build_messages(user_text, history)
    tool_results, called, usage_total = [], [], {"prompt": 0, "completion": 0}

    # ── B3+B4: LLM chọn tool → chạy tool ────────────────────────────────
    for _ in range(MAX_TOOL_ROUNDS):
        out = llm.chat(messages, tools=registry.TOOL_SCHEMAS)
        _acc(usage_total, out.get("usage"))

        if not out["tool_calls"]:
            break

        messages.append({
            "role": "assistant", "content": out["content"] or None,
            "tool_calls": [{"id": tc["id"], "type": "function",
                            "function": {"name": tc["name"],
                                         "arguments": json.dumps(tc["arguments"], ensure_ascii=False)}}
                           for tc in out["tool_calls"]],
        })

        seen_calls = set()
        for tc in out["tool_calls"]:
            sig = (registry.normalize_tool_name(tc["name"]),
                   json.dumps(tc["arguments"], sort_keys=True, ensure_ascii=False))
            if sig in seen_calls:      # model gọi trùng → bỏ qua, đỡ tốn token
                continue
            seen_calls.add(sig)
            result = registry.dispatch(actor, tc["name"], tc["arguments"])   # ← actor tiêm ở đây
            tool_results.append(result)
            called.append({"name": tc["name"], "arguments": tc["arguments"],
                           "dropped_params": result.get("_dropped_params", [])})
            messages.append({"role": "tool", "tool_call_id": tc["id"],
                             "content": json.dumps(result, ensure_ascii=False, default=str)})

    # ── B5: diễn đạt ────────────────────────────────────────────────────
    final = out["content"]
    if not final:
        out = llm.chat(messages)
        _acc(usage_total, out.get("usage"))
        final = out["content"]

    # ── B6: hậu kiểm, viết lại một lần nếu sai ──────────────────────────
    report = guard.verify(final, tool_results)
    first_draft_report = dict(report)      # giữ lại để biết CÁI GÌ đã kích hoạt
    retried = False
    if not report["ok"]:
        retried = True
        messages.append({"role": "assistant", "content": final})
        messages.append({"role": "user", "content": guard.correction_prompt(report)})
        out2 = llm.chat(messages)
        _acc(usage_total, out2.get("usage"))
        candidate = out2["content"]
        report2 = guard.verify(candidate, tool_results)
        if report2["ok"]:
            final, report = candidate, report2
        else:
            # Vẫn sai → KHÔNG đưa câu bịa ra ngoài. Trả bản dựng từ template.
            final = _fallback(tool_results)
            report = guard.verify(final, tool_results)

    return {
        "answer": final,
        "actor": actor.actor_id, "role": actor.role, "scope_size": len(actor.scope),
        "tool_calls": called,
        "verified": report["ok"],
        "guard_report": report,
        "first_draft_report": first_draft_report,
        "retried": retried,
        "usage": usage_total,
        "audit_ids": [r.get("audit_id") for r in tool_results if r.get("audit_id")],
    }


def _fallback(tool_results) -> str:
    """Khi model không chịu tuân thủ: dựng câu trả lời máy móc từ chính kết quả tool."""
    from .llm import _render
    if not tool_results:
        return "Chưa có dữ liệu cho câu hỏi này."
    return (_render(tool_results[-1])
            + "\n(Câu trả lời được dựng tự động từ dữ liệu gốc do bản diễn đạt không đạt kiểm tra.)")


def _acc(total, usage):
    if not usage:
        return
    total["prompt"] += usage.get("prompt_tokens") or 0
    total["completion"] += usage.get("completion_tokens") or 0
