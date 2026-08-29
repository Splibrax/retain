# -*- coding: utf-8 -*-
"""
guard.py — hậu kiểm câu trả lời của LLM (BLUEPRINT §8 R6, R7, R9).

R6 là rule khó nhất: "không được sinh số". Dặn trong prompt là chưa đủ —
mô hình nào cũng có lúc trôi. Ở đây kiểm bằng máy: MỌI con số trong câu trả lời
phải truy được về một giá trị có trong kết quả tool.

Cách xử lý tiếng Việt: "85,78" là số thập phân (dấu phẩy), "1.285" là hàng nghìn
(dấu chấm). Hai quy ước ngược với tiếng Anh nên phải tách bạch.
"""
from __future__ import annotations

import re

# số: 1.285  85,78  50.7  0,4  12
NUM_RE = re.compile(r"\d[\d.,]*")

# R9 — hứa hẹn giữ được người. Dùng regex vì "sẽ ở lại" trần trụi quá rộng:
# chính câu cảnh báo của hệ thống ("KHÔNG phải dự báo người này sẽ ở lại")
# cũng chứa nó. Bắt cụm mang tính CAM KẾT, và bỏ qua khi có phủ định đứng trước.
FORBIDDEN_RE = [
    re.compile(r"sẽ giữ (được|chân)", re.I),
    re.compile(r"(chắc chắn|đảm bảo|cam kết)\s*(sẽ\s*)?(giữ|ở lại)", re.I),
    re.compile(r"(chắc chắn|nhất định)\s*(sẽ\s*)?không nghỉ", re.I),
]

# R7 — không kết luận pháp lý / kỷ luật
LEGAL_RE = [
    re.compile(r"sa thải", re.I),
    re.compile(r"chấm dứt hợp đồng", re.I),
    re.compile(r"(đúng|trái|vi phạm) (pháp )?luật", re.I),
    re.compile(r"(nên|cần|phải) (kỷ luật|xử lý kỷ luật)", re.I),
]

# Câu cảnh báo do CHÍNH hệ thống chèn — bỏ ra trước khi soi từ ngữ.
SYSTEM_DISCLAIMERS = (
    "KHÔNG phải dự báo người này sẽ ở lại",
    "không phải dự báo người này sẽ ở lại",
)

NEGATORS = ("không", "chưa", "chẳng")


def _variants(token: str) -> list[float]:
    """
    Một token số có thể đọc theo nhiều cách — trả về MỌI cách đọc hợp lý.

    Tiếng Việt: dấu chấm là hàng nghìn ("1.285" = 1285), dấu phẩy là thập phân
    ("85,78"). Nhưng model đôi khi xuất theo kiểu Anh ("0.965" = 0,965).
    Nhập nhằng thì chấp nhận cả hai cách đọc, còn hơn báo nhầm là bịa số.
    """
    t = token.strip().rstrip(".,")
    if not t:
        return []
    out = []

    def push(x):
        try:
            v = float(x)
        except ValueError:
            return
        if v not in out:
            out.append(v)

    # cách đọc kiểu Anh: chấm là thập phân, phẩy là hàng nghìn
    push(t.replace(",", ""))
    # cách đọc kiểu Việt: chấm là hàng nghìn, phẩy là thập phân
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", t) and not t.startswith("0"):
        push(t.replace(".", ""))
    if re.fullmatch(r"\d+,\d+", t):
        push(t.replace(",", "."))
    return out


def _norm(token: str):
    """Cách đọc chính (dùng để báo cáo). None nếu không phải số."""
    v = _variants(token)
    return v[0] if v else None


def collect_allowed(obj, acc: set | None = None) -> set:
    """
    Gom mọi con số hợp lệ từ kết quả tool — kể cả số nằm trong chuỗi
    (reason_salary chứa "thấp hơn P50 thị trường 50.7%").
    """
    acc = set() if acc is None else acc
    if isinstance(obj, bool):
        return acc
    if isinstance(obj, (int, float)):
        _add(acc, float(obj))
    elif isinstance(obj, str):
        for m in NUM_RE.findall(obj):
            for v in _variants(m):      # nạp mọi cách đọc vào tập cho phép
                _add(acc, v)
    elif isinstance(obj, dict):
        for v in obj.values():
            collect_allowed(v, acc)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            collect_allowed(v, acc)
    return acc


def _add(acc: set, v: float):
    """Thêm giá trị + các biến thể làm tròn mà người viết hay dùng."""
    acc.add(round(v, 2))
    acc.add(round(v, 1))
    acc.add(round(v, 0))
    acc.add(round(v * 100, 2))   # 0.4 → 40 (trọng số ghi dạng %)
    acc.add(round(v * 100, 0))
    if v != 0:
        acc.add(round(abs(v), 2))


# Số mang tính cấu trúc, luôn cho phép: thang /100, ngưỡng band, trọng số gốc,
# nhãn P1/P2/P3, 4 yếu tố. KHÔNG cho phép mọi số nhỏ — đếm sai là kiểu bịa
# hay gặp nhất ("có khoảng 12 người rủi ro cao").
STRUCTURAL = {0.0, 1.0, 2.0, 3.0, 4.0, 100.0, 66.0, 33.0, 40.0, 30.0, 20.0, 10.0, 50.0}

# Số thứ tự đầu dòng ("1.", "2)") là cấu trúc trình bày, không phải dữ liệu.
ORDINAL_RE = re.compile(r"^[ \t]*\d+[.)]", re.MULTILINE)


def check_numbers(answer: str, tool_results) -> list[float]:
    """Trả về danh sách số XUẤT HIỆN TRONG CÂU TRẢ LỜI mà không truy được về tool."""
    allowed = collect_allowed(tool_results) | STRUCTURAL
    text = ORDINAL_RE.sub(" ", answer or "")     # bỏ số thứ tự đầu dòng
    bad = []
    for m in NUM_RE.findall(text):
        variants = _variants(m)
        if not variants:
            continue
        # đạt nếu BẤT KỲ cách đọc nào truy được về dữ liệu tool
        if any(abs(v - a) < 0.011 for v in variants for a in allowed):
            continue
        bad.append(variants[-1])   # cách đọc kiểu Việt, hợp với người đọc
    return bad


def check_phrases(answer: str) -> list[str]:
    """Trả về các cụm từ vi phạm R9 / R7 (đã bỏ câu cảnh báo hệ thống, đã né phủ định)."""
    text = answer or ""
    for d in SYSTEM_DISCLAIMERS:
        text = text.replace(d, " ")
    hits = []
    for rx in FORBIDDEN_RE + LEGAL_RE:
        for m in rx.finditer(text):
            before = text[max(0, m.start() - 30):m.start()].lower()
            if any(n in before for n in NEGATORS):
                continue                      # đang phủ định → không tính là vi phạm
            hits.append(m.group(0))
    return hits


def verify(answer: str, tool_results) -> dict:
    """Kết quả hậu kiểm gộp. ok=False → runtime yêu cầu viết lại một lần."""
    bad_nums = check_numbers(answer, tool_results)
    bad_phr = check_phrases(answer)
    return {
        "ok": not bad_nums and not bad_phr,
        "unverified_numbers": bad_nums,
        "forbidden_phrases": bad_phr,
    }


def correction_prompt(report: dict) -> str:
    bits = []
    if report["unverified_numbers"]:
        nums = ", ".join(f"{n:g}" for n in report["unverified_numbers"][:8])
        bits.append(
            f"Câu trả lời chứa con số KHÔNG có trong kết quả tool: {nums}. "
            "Viết lại, chỉ dùng đúng những con số tool đã trả về. "
            "Nếu không có dữ liệu thì nói là không có, tuyệt đối không ước lượng."
        )
    if report["forbidden_phrases"]:
        bits.append(
            "Câu trả lời dùng từ hứa hẹn hoặc kết luận pháp lý: "
            f"{', '.join(report['forbidden_phrases'])}. "
            "Bỏ những từ đó. Mô phỏng là giả định, không phải cam kết giữ được người; "
            "vấn đề kỷ luật/pháp lý thì chuyển sang bộ phận pháp chế."
        )
    return " ".join(bits)
