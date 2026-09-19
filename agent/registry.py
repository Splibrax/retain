# -*- coding: utf-8 -*-
"""
registry.py — khai báo tool cho LLM + điều phối gọi tool.

ĐÂY LÀ CHỐT AN TOÀN QUAN TRỌNG NHẤT CỦA CẢ AGENT:

    Schema đưa cho LLM KHÔNG CÓ tham số phạm vi (dept_code / scope / actor).
    LLM không thể yêu cầu dữ liệu đơn vị khác, vì nó không có ô nào để điền vào.
    `actor` được tiêm ở dispatch(), lấy từ danh tính đã xác thực ở entrypoint.

Nếu ai đó thêm dept_code vào TOOL_SCHEMAS, bài test test_registry_khong_lo_tham_so_pham_vi
sẽ đỏ. Đừng tắt bài test đó.
"""
from __future__ import annotations

from . import tools

# ── Schema theo chuẩn OpenAI function-calling (GreenNode MaaS tương thích) ──
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_team_risk",
            "description": (
                "Liệt kê nhân sự trong phạm vi quản lý của người đang hỏi. Mặc định lấy "
                "nhóm mức Cao + Trung bình, xếp theo điểm rủi ro giảm dần. Dùng khi người "
                "dùng hỏi 'ai đang muốn đi', 'team mình thế nào', 'có ai đáng lo không'. "
                "Có thể LỌC theo mức (band) và SẮP XẾP theo một yếu tố (sort_by): chỉ truyền "
                "khi người dùng nêu rõ một mức ('những người mức Cao') hoặc hỏi theo một yếu "
                "tố ('ai KPI thấp nhất', 'lương thấp hơn thị trường nhiều nhất'); xếp theo "
                "yếu tố mà không nêu mức thì xét cả phạm vi, mọi mức. Hỏi chung chung thì "
                "KHÔNG truyền hai tham số này. Mỗi dòng kết quả kèm giá trị của "
                "trường dùng để xếp (sort_value, sort_value_text). KHÔNG dùng để tra một "
                "người cụ thể — trừ khi chỉ có tên chưa có mã: khi đó gọi với limit 20, "
                "không band, không sort_by, để lấy mã rồi gọi công cụ khác cho người đó."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": (
                            "Số người muốn xem, mặc định 5, tối đa 20. CHỈ truyền khi người "
                            "dùng nói rõ số người ('top 3', '10 người'); câu 'ai … nhất' không "
                            "nêu số lượng thì KHÔNG truyền. Ngoại lệ duy nhất: tra mã từ tên."
                        ),
                    },
                    "band": {
                        "type": "string",
                        "enum": list(tools.BAND_INPUT),
                        "description": (
                            "Chỉ lấy người ở đúng mức này. Chỉ nhận: Cao / Trung bình / Thấp. "
                            "Không truyền nếu người dùng không nêu mức."
                        ),
                    },
                    "sort_by": {
                        "type": "string",
                        "enum": list(tools.SORT_FIELDS),
                        "description": (
                            "Xếp theo: score = điểm rủi ro cao nhất trước (mặc định); "
                            "salary_gap = lương thấp hơn P50 thị trường nhiều nhất trước; "
                            "kpi = điểm KPI thấp nhất trước; "
                            "freeze = bị dừng xét điều chỉnh lương lâu nhất trước; "
                            "promo = lâu chưa điều chuyển/bổ nhiệm nhất trước; "
                            "tenure = thâm niên dài nhất trước."
                        ),
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explain_employee_risk",
            "description": (
                "Giải thích vì sao một nhân sự cụ thể bị chấm điểm rủi ro cao, theo các "
                "yếu tố có trọng số. Dùng khi người dùng hỏi 'vì sao', 'lý do', 'sao "
                "bạn ấy bị chấm cao', và khi hỏi lương, KPI, đơn vị, người quản lý của MỘT "
                "người cụ thể (theo tên, mã, hoặc 'bạn ấy'). Mọi câu hỏi về một người phải "
                "gọi ít nhất một công cụ về người đó trong lượt này, không dùng lại số của "
                "lượt trước. Chỉ nhận mã nhân viên; nếu chỉ có tên thì lấy mã từ câu trả lời "
                "trước hoặc gọi list_team_risk để tìm, đừng hỏi lại người dùng."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "employee_id": {"type": "string", "description": "Mã nhân viên, ví dụ E001881."}
                },
                "required": ["employee_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_actions",
            "description": (
                "Gợi ý việc cần làm với một nhân sự theo 3 tầng P1 (2 tuần) / P2 (trong "
                "quý) / P3 (sửa gốc). Dùng khi người dùng hỏi 'nên làm gì', 'xử lý thế nào'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "employee_id": {"type": "string", "description": "Mã nhân viên."}
                },
                "required": ["employee_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "simulate_intervention",
            "description": (
                "Tính lại điểm rủi ro NẾU thực hiện một phương án. Dùng khi người dùng "
                "hỏi 'nếu tăng lương thì sao', 'đưa về mức thị trường thì còn bao nhiêu', "
                "'cải thiện KPI thì thế nào'. Kết quả là giả định, không phải dự báo."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "employee_id": {"type": "string"},
                    "scenario": {
                        "type": "string",
                        "enum": ["raise_pct", "to_p50", "kpi_recovery", "promotion"],
                        "description": (
                            "raise_pct = tăng lương theo %; to_p50 = đưa lương về đúng "
                            "trung vị thị trường; kpi_recovery = KPI phục hồi lên mức mục tiêu; "
                            "promotion = điều chuyển / bổ nhiệm trong kỳ tới (không tốn ngân sách lương)."
                        ),
                    },
                    "value": {
                        "type": "number",
                        "description": (
                            "Với raise_pct: tỉ lệ tăng, ví dụ 0.1 cho 10%. "
                            "Với kpi_recovery: điểm KPI mục tiêu 0-100. "
                            "Với to_p50 và promotion: bỏ trống."
                        ),
                    },
                },
                "required": ["employee_id", "scenario"],
            },
        },
    },
]

# Tham số bị CẤM tuyệt đối trong schema — có mặt là lỗ hổng phân quyền.
FORBIDDEN_PARAMS = {
    "dept_code", "dept", "department", "scope", "scope_code", "dept_scope_code",
    "actor", "actor_id", "role", "org", "unit", "unit_code", "all_departments",
}

_DISPATCH = {
    "list_team_risk": tools.list_team_risk,
    "explain_employee_risk": tools.explain_employee_risk,
    "suggest_actions": tools.suggest_actions,
    "simulate_intervention": tools.simulate_intervention,
}


def normalize_tool_name(raw: str) -> str | None:
    """
    Làm sạch tên tool do model trả về.

    GLM (và nhiều model có chế độ suy luận) đôi khi để lọt thẻ nội bộ vào chính
    tên hàm, ví dụ quan sát thực tế ngày 29/8:
        "explain&lt&lt;think&gt2&gt;</think><tool_call>explain_employee_risk"
    Nếu không làm sạch, lời gọi đó thành UNKNOWN_TOOL và câu trả lời có thể hỏng
    ngay trên sân khấu. Cách xử lý: tìm tên tool hợp lệ nằm trong chuỗi rác.
    """
    if not raw:
        return None
    if raw in _DISPATCH:
        return raw
    hits = [k for k in _DISPATCH if k in raw]
    # chỉ nhận khi xác định được DUY NHẤT một tool — mơ hồ thì từ chối, không đoán
    return hits[0] if len(hits) == 1 else None


def dispatch(actor: tools.Actor, name: str, args: dict) -> dict:
    """
    Gọi tool. `actor` do RUNTIME tiêm vào, KHÔNG lấy từ args của LLM.
    Mọi khoá trong args trùng FORBIDDEN_PARAMS đều bị vứt bỏ trước khi gọi.
    """
    clean_name = normalize_tool_name(name)
    fn = _DISPATCH.get(clean_name) if clean_name else None
    if fn is None:
        return {"error": "UNKNOWN_TOOL", "tool": name}

    clean = {k: v for k, v in (args or {}).items() if k not in FORBIDDEN_PARAMS}
    dropped = sorted(set(args or {}) & FORBIDDEN_PARAMS)

    try:
        result = fn(actor, **clean)
    except tools.ScenarioError as e:
        return {"error": "INVALID_SCENARIO", "message": str(e)}
    except tools.InvalidParam as e:
        # Giá trị ngoài danh sách: báo rõ được phép những gì, không đoán ý model.
        return {"error": "INVALID_PARAM", "message": str(e)}
    except TypeError as e:
        return {"error": "BAD_ARGUMENTS", "message": str(e)}

    if dropped:
        # Ghi lại để soi: LLM đang cố truyền tham số phạm vi.
        result["_dropped_params"] = dropped
    return result
