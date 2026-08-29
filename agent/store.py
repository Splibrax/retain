# -*- coding: utf-8 -*-
"""
store.py — tầng đọc dữ liệu. Load một lần lúc khởi động, giữ trong bộ nhớ.

Nguyên tắc BLUEPRINT §5:
  * fact_flight_risk_score là nguồn sự thật DUY NHẤT về điểm — agent không tính lại
  * cột BLOCKLIST (gender, marital_status, education) KHÔNG BAO GIỜ rời tầng này
  * dim_employee là tuỳ chọn: thiếu thì degrade về employee_id, không crash
"""
from __future__ import annotations

import csv
import os
from functools import lru_cache

DATA_DIR = os.environ.get("RETAIN_DATA_DIR", "data")

# BLUEPRINT §5.3 — không bao giờ đọc lên khỏi tầng này.
BLOCKLIST = {"gender", "marital_status", "education", "base_salary"}

# BLUEPRINT §5.2 — cột duy nhất được phép đi tiếp lên tool/LLM.
EMPLOYEE_SAFE_FIELDS = ("employee_id", "full_name", "dept_code", "band")


def _p(name: str) -> str:
    return os.path.join(DATA_DIR, name)


def _to_float(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _to_int(s):
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


@lru_cache(maxsize=1)
def load_scores() -> tuple[dict, ...]:
    """Đọc fact_flight_risk_score, ép kiểu số ngay để tool không phải parse lại."""
    with open(_p("fact_flight_risk_score.csv"), encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["flight_risk_score"] = _to_float(r["flight_risk_score"])
        r["salary_gap_to_p50_pct"] = _to_float(r["salary_gap_to_p50_pct"])
        r["kpi_score"] = _to_float(r["kpi_score"])
        r["pay_freeze_months"] = _to_int(r["pay_freeze_months"])
        r["tenure_months"] = _to_int(r["tenure_months"])
        r["warning_letter_count_12m"] = _to_int(r["warning_letter_count_12m"])
        r["seniority_risk_window_flag"] = str(r["seniority_risk_window_flag"]).strip() == "True"
        r["is_excluded_from_risk_list"] = str(r["is_excluded_from_risk_list"]).strip() == "True"
    return tuple(rows)


@lru_cache(maxsize=1)
def latest_snapshot() -> str:
    """Kỳ gần nhất. BLUEPRINT §5.1: snapshot là ngày ĐẦU tháng — đừng hardcode."""
    return max(r["snapshot_date"] for r in load_scores())


@lru_cache(maxsize=1)
def load_employees() -> dict:
    """
    dim_employee → {employee_id: {các cột an toàn}}.
    Tuỳ chọn: file không có thì trả {} và tool sẽ dùng employee_id thay tên.
    Cột BLOCKLIST bị loại ngay tại đây, không đi tiếp.
    """
    path = _p("dim_employee.csv")
    if not os.path.exists(path):
        return {}
    out = {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out[r["employee_id"]] = {
                k: r.get(k) for k in EMPLOYEE_SAFE_FIELDS if k in r
            }
    return out


def display_name(employee_id: str) -> str:
    emp = load_employees().get(employee_id)
    if emp and emp.get("full_name"):
        return emp["full_name"]
    return employee_id


@lru_cache(maxsize=1)
def load_actors() -> dict:
    """dim_actor → {actor_id: {actor_name, role, dept_scope_code}}."""
    with open(_p("dim_actor.csv"), encoding="utf-8") as f:
        return {r["actor_id"]: r for r in csv.DictReader(f)}


def rows_for(snapshot_date: str, scope: frozenset[str], active_only: bool = True):
    """
    Lọc theo scope Ở TẦNG DỮ LIỆU. Đây là câu 'WHERE dept_code IN (...)'.
    Mọi tool phải đi qua hàm này — không tool nào tự duyệt load_scores().
    """
    for r in load_scores():
        if r["snapshot_date"] != snapshot_date:
            continue
        if r["dept_code"] not in scope:
            continue
        if active_only and r["employment_status"] != "Active":
            continue
        yield r


@lru_cache(maxsize=1)
def load_playbook() -> dict:
    """
    data/playbook.csv → {factor: {P1, P2, P3}}.
    Nội dung do HRBP viết. LLM chỉ đọc lại, không tự nghĩ lời khuyên.
    """
    path = _p("playbook.csv")
    if not os.path.exists(path):
        return {}
    out: dict = {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out.setdefault(r["factor"], {})[r["priority"]] = r["action"]
    return out


@lru_cache(maxsize=1)
def playbook_is_draft() -> bool:
    """
    True nếu playbook còn ô nào ở trạng thái nháp.
    Agent PHẢI nói ra điều này — để bản nháp không lỡ lên sân khấu như bản thật.
    """
    path = _p("playbook.csv")
    if not os.path.exists(path):
        return True
    with open(path, encoding="utf-8") as f:
        return any(r.get("status", "").strip().lower() != "final"
                   for r in csv.DictReader(f))
