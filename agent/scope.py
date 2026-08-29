# -*- coding: utf-8 -*-
"""
scope.py — Tuyến phòng thủ #3 của RetAIn (BLUEPRINT §4.2, §7).

Đây là chỗ phân quyền THỰC SỰ được thực thi. AgentBase Policy chỉ gate được
tool nào role nào gọi; nó KHÔNG lọc được theo dòng dữ liệu. Vì vậy:

    * scope được suy ra từ danh tính ĐÃ XÁC THỰC, không phải từ câu hỏi
    * dept_code KHÔNG BAO GIỜ là tham số do LLM truyền vào
    * mọi lỗi resolve đều FAIL CLOSED → trả tập rỗng, không bao giờ trả tất cả

Xử lý đúng "8 dept_code mồ côi" (BLUEPRINT §5.4): 8 mã trong fact table nằm ở
cấp trung gian (lvl2/lvl3), không phải node lá. Thuật toán match trên MỌI cấp,
không chỉ lowest_code.
"""
from __future__ import annotations

import csv
import os
from functools import lru_cache

# Thứ tự cấp, từ gốc xuống lá. lowest_code lặp lại cấp sâu nhất có giá trị.
LEVELS = ("lvl1_code", "lvl2_code", "lvl3_code", "lvl4_code", "lowest_code")

DATA_DIR = os.environ.get("RETAIN_DATA_DIR", "data")


def _dedupe(seq):
    """Giữ thứ tự, bỏ trùng. lowest_code thường trùng cấp sâu nhất."""
    seen, out = set(), []
    for x in seq:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


@lru_cache(maxsize=1)
def load_hierarchy(path: str | None = None) -> tuple[tuple[str, ...], ...]:
    """Đọc dim_dept_hierarchy một lần, trả về tuple các chain (gốc → lá)."""
    p = path or os.path.join(DATA_DIR, "dim_dept_hierarchy.csv")
    with open(p, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return tuple(tuple(_dedupe(r[k] for k in LEVELS)) for r in rows)


def resolve_scope(scope_code: str, hierarchy=None) -> frozenset[str]:
    """
    Trả về TẤT CẢ dept_code mà một actor có scope_code được phép nhìn thấy:
    chính nó + toàn bộ cây con, ở mọi cấp.

    FAIL CLOSED: mã không tồn tại → frozenset() rỗng. Không bao giờ trả toàn bộ.
    """
    if not scope_code:
        return frozenset()

    chains = hierarchy if hierarchy is not None else load_hierarchy()
    found = set()
    matched_any = False

    for chain in chains:
        if scope_code in chain:
            matched_any = True
            i = chain.index(scope_code)
            found.update(chain[i:])          # chính nó + mọi cấp bên dưới

    if not matched_any:
        return frozenset()                   # ← fail closed, KHÔNG fallback

    found.add(scope_code)
    return frozenset(found)


def in_scope(dept_code: str, scope: frozenset[str]) -> bool:
    """Một dept_code có nằm trong scope đã resolve không."""
    return bool(dept_code) and dept_code in scope
