# -*- coding: utf-8 -*-
"""
llm.py — lớp gọi model. GreenNode MaaS tương thích OpenAI nên dùng chung một client.

Ba biến môi trường (đặt trong .env, KHÔNG commit):
    LLM_BASE_URL   ví dụ https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1
    LLM_API_KEY
    LLM_MODEL      tên model đã xác nhận modelStatus = ENABLED

MockLLM cho phép chạy và test TOÀN BỘ đường ống mà không cần mạng, không tốn token —
dùng khi phát triển và trong CI.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def load_dotenv(path=".env") -> list[str]:
    """
    Nạp file .env vào os.environ. Trả về DANH SÁCH TÊN BIẾN đã nạp (không bao giờ trả giá trị).

    Tự viết thay vì phụ thuộc gói ngoài: chỉ vài dòng, và tránh thêm dependency
    vào image. Biến đã có sẵn trong môi trường thì KHÔNG bị ghi đè —
    môi trường thật (AgentBase Runtime tự tiêm biến) luôn thắng file .env.
    """
    f = Path(path)
    if not f.exists():
        return []
    loaded = []
    for line in f.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v
        loaded.append(k)
    return loaded


# Tên biến có thể khác nhau tuỳ tài liệu/phiên làm việc — chấp nhận các biến thể
# thông dụng thay vì bắt người dùng đổi tên file .env đang chạy tốt.
ALIASES = {
    "base_url": ("LLM_BASE_URL", "BASE_URL", "GREENNODE_BASE_URL", "MAAS_BASE_URL", "OPENAI_BASE_URL"),
    "api_key":  ("LLM_API_KEY", "API_KEY", "GREENNODE_API_KEY", "MAAS_API_KEY", "AIP_API_KEY", "OPENAI_API_KEY"),
    "model":    ("LLM_MODEL", "MODEL", "GREENNODE_MODEL", "MAAS_MODEL"),
}


def _pick(kind):
    """
    Trả về (giá trị, tên biến đã dùng). Không in giá trị ra đâu cả.

    LUÔN .strip() giá trị. Lý do có thật, gặp ngày 29/8: file .env viết
    "KEY = value" thì bộ nạp Python tự bỏ khoảng trắng, nhưng `docker --env-file`
    GIỮ NGUYÊN dấu cách → khoá API thành " vn-..." → 401 Unauthorized.
    Chạy ở máy thì tốt, vào container thì hỏng — kiểu lỗi mất nhiều thời gian nhất.
    Cấu hình trên AgentBase Runtime cũng dán tay, nên rủi ro y hệt.
    """
    for name in ALIASES[kind]:
        v = os.environ.get(name)
        if v and v.strip():
            return v.strip(), name
    return None, None


class LLMError(RuntimeError):
    pass


class OpenAICompatLLM:
    def __init__(self, base_url=None, api_key=None, model=None, timeout=60):
        load_dotenv()
        bu, self.src_base = _pick("base_url")
        ak, self.src_key = _pick("api_key")
        md, self.src_model = _pick("model")
        self.base_url = base_url or bu
        self.api_key = api_key or ak
        self.model = model or md
        self.timeout = timeout
        if not (self.base_url and self.api_key and self.model):
            thieu = [k for k, v in (("base_url", self.base_url), ("api_key", self.api_key),
                                    ("model", self.model)) if not v]
            raise LLMError(
                f"Thiếu cấu hình: {', '.join(thieu)}.\n"
                f"Đặt trong .env một trong các tên sau:\n"
                + "\n".join(f"  {k}: {' hoặc '.join(ALIASES[k])}" for k in thieu)
                + "\nHoặc chạy python check_env.py để xem file .env đang có tên biến gì."
            )
        try:
            from openai import OpenAI
        except ImportError as e:
            raise LLMError("Chưa cài gói openai: pip install openai") from e
        self._client = OpenAI(base_url=self.base_url, api_key=self.api_key, timeout=timeout)

    def chat(self, messages, tools=None, tool_choice="auto"):
        kwargs = {"model": self.model, "messages": messages, "temperature": 0.2}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        resp = self._client.chat.completions.create(**kwargs)
        m = resp.choices[0].message
        usage = getattr(resp, "usage", None)
        return {
            "content": m.content or "",
            "tool_calls": [
                {"id": tc.id, "name": tc.function.name,
                 "arguments": _safe_json(tc.function.arguments)}
                for tc in (m.tool_calls or [])
            ],
            "usage": {
                "prompt_tokens": getattr(usage, "prompt_tokens", None),
                "completion_tokens": getattr(usage, "completion_tokens", None),
            } if usage else {},
        }


def _safe_json(s):
    try:
        return json.loads(s) if isinstance(s, str) else (s or {})
    except json.JSONDecodeError:
        return {}


class MockLLM:
    """
    Giả lập model: chọn tool bằng từ khoá, rồi dựng câu trả lời từ ĐÚNG số của tool.
    Không thay thế model thật, nhưng đủ để kiểm đường ống + guard + phân quyền
    mà không cần mạng.
    """

    def __init__(self, model="mock"):
        self.model = model

    def chat(self, messages, tools=None, tool_choice="auto"):
        user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user = (m.get("content") or "").lower()
                break

        # lượt 2: đã có kết quả tool → viết câu trả lời
        if any(m.get("role") == "tool" for m in messages):
            payload = _safe_json(next(m["content"] for m in reversed(messages)
                                      if m.get("role") == "tool"))
            return {"content": _render(payload), "tool_calls": [], "usage": {}}

        # lượt 1: chọn tool
        eid = _first_eid(user)
        if any(k in user for k in ("nếu", "giả sử", "tăng lương", "p50", "thị trường", "kpi lên")):
            sc = "kpi_recovery" if "kpi" in user else ("raise_pct" if "%" in user else "to_p50")
            args = {"employee_id": eid or "E001881", "scenario": sc}
            if sc == "kpi_recovery":
                args["value"] = 85
            elif sc == "raise_pct":
                args["value"] = 0.1
            return _call("simulate_intervention", args)
        if any(k in user for k in ("nên làm gì", "xử lý", "hành động", "giữ chân")):
            return _call("suggest_actions", {"employee_id": eid or "E001881"})
        if any(k in user for k in ("vì sao", "tại sao", "sao ", "lý do")) and eid:
            return _call("explain_employee_risk", {"employee_id": eid})
        return _call("list_team_risk", {"limit": 5})


def _call(name, args):
    return {"content": "", "usage": {},
            "tool_calls": [{"id": "mock_1", "name": name, "arguments": args}]}


def _first_eid(text: str):
    import re
    m = re.search(r"e\d{6}", text or "", re.IGNORECASE)
    return m.group(0).upper() if m else None


def _render(p: dict) -> str:
    """Dựng câu trả lời CHỈ từ số có trong payload — mô phỏng model ngoan."""
    if p.get("error") == "OUT_OF_SCOPE":
        return ("Truy vấn này nằm ngoài phạm vi dữ liệu của anh/chị. RetAIn chỉ trả lời trên "
                "nhánh tổ chức gắn với tài khoản đang đăng nhập. Nếu cần thông tin đơn vị khác, "
                f"đề nghị liên hệ HRBP phụ trách khối đó.\nTruy vấn: {p.get('audit_id','')}")
    if p.get("status") == "EXCLUDED":
        return (f"Nhân sự {p.get('employee_id')} bị loại khỏi danh sách giữ chân theo quy tắc "
                f"{p.get('reason')}. Không đưa ra khuyến nghị giữ chân cho trường hợp này.\n"
                f"Truy vấn: {p.get('audit_id','')}")
    if "items" in p:
        lines = [f"Trong phạm vi của anh/chị, kỳ {p['snapshot_date']}: {p['n_flagged']} người "
                 f"cần lưu ý ({p['n_high']} High, {p['n_medium']} Medium) trên tổng "
                 f"{p['scope_headcount']} nhân sự."]
        for i, it in enumerate(p["items"], 1):
            lines.append(f"{i}. {it['full_name']} ({it['employee_id']}) — {it['score']}/100, "
                         f"{it['band']}. {it['top_factor']}")
        if p.get("n_excluded"):
            lines.append(f"{p['n_excluded']} người bị loại theo quy tắc từ 2 thư cảnh cáo trong 12 tháng.")
        lines.append(f"Nguồn: fact_flight_risk_score @ {p['snapshot_date']} · Truy vấn: {p['audit_id']}")
        return "\n".join(lines)
    if "factors" in p:
        lines = [f"{p['full_name']} ({p['employee_id']}) — {p['score']}/100, mức {p['band']}, "
                 f"kỳ {p['snapshot_date']}."]
        for f in p["factors"]:
            lines.append(f"- {f['factor']}: mức {f['risk_value']}, trọng số dùng "
                         f"{round(f['weight_used']*100)}%. {f['reason']}")
        if p.get("missing_features"):
            lines.append(f"Thiếu dữ liệu: {p['missing_features']}; trọng số đã được chuẩn hoá lại.")
        lines.append(f"Nguồn: fact_flight_risk_score @ {p['snapshot_date']} · Truy vấn: {p['audit_id']}")
        return "\n".join(lines)
    if "scenario_label" in p:
        return (f"Giả định: {p['scenario_label']} — {p['full_name']} ({p['employee_id']}).\n"
                f"Điểm rủi ro {p['score_before']} → {p['score_after']}, giảm {p['score_delta']} điểm. "
                f"Mức {p['band_before']} → {p['band_after']}.\n"
                f"Phần giảm đến từ: {p['delta_by_factor']}.\n"
                f"{p['disclaimer']}\nTruy vấn: {p['audit_id']}")
    if "P1" in p:
        draft = " (playbook đang là bản nháp, chờ HRBP duyệt)" if p.get("playbook_is_draft") else ""
        return (f"{p['full_name']} ({p['employee_id']}) — {p['score']}/100, mức {p['band']}. "
                f"Yếu tố trội: {p['top_factor_reason']}\n"
                f"P1 (trong 2 tuần): {p['P1']}\nP2 (trong quý): {p['P2']}\n"
                f"P3 (sửa gốc): {p['P3']}{draft}\nTruy vấn: {p['audit_id']}")
    return json.dumps(p, ensure_ascii=False)


def make_llm(mock: bool = False):
    return MockLLM() if mock else OpenAICompatLLM()
