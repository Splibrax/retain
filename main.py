# -*- coding: utf-8 -*-
"""
main.py — máy chủ HTTP của agent.

Yêu cầu cứng của AgentBase Runtime: GET /health trả 200.

Lớp server ở file này CỐ TÌNH mỏng. Khi chạy /agentbase-wizard ngày 4/9, wizard sẽ
sinh ra bản main.py dùng GreenNodeAgentBaseApp — lúc đó chỉ cần thay phần server,
GIỮ NGUYÊN toàn bộ agent/ (logic, phân quyền, guard). Đó là lý do tách như vậy:
nghiệp vụ không dính vào SDK nền tảng.

Chạy local:  python main.py           (mặc định mock, không cần model)
             RETAIN_MOCK=0 python main.py
"""
import os

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from agent import runtime
from agent.llm import make_llm

# MẶC ĐỊNH LÀ MODEL THẬT. Trước đây mặc định là mock, và đó là quả mìn:
# deploy lên runtime mà quên đặt biến thì agent vẫn chạy, vẫn trả lời trôi chảy,
# nhưng bằng MockLLM — sai hoàn toàn mà không có dấu hiệu nào trên màn hình.
# Muốn chạy mock thì phải nói rõ: RETAIN_MOCK=1
USE_MOCK = os.environ.get("RETAIN_MOCK", "0") == "1"


class UTF8JSONResponse(JSONResponse):
    """
    Ép charset=utf-8 vào header trả về.

    JSON theo chuẩn RFC 8259 vốn đã là UTF-8, nhưng client cũ (PowerShell 5.1,
    một số thư viện HTTP đời trước) khi không thấy charset thì mặc định đọc bằng
    ISO-8859-1 → tiếng Việt vỡ hết. Sửa ở server vì ta không kiểm soát được
    client nào sẽ gọi vào lúc demo.
    """
    media_type = "application/json; charset=utf-8"


app = FastAPI(title="RetAIn", version="0.2", default_response_class=UTF8JSONResponse)
_llm = None


def llm():
    global _llm
    if _llm is None:
        _llm = make_llm(mock=USE_MOCK)
    return _llm


class ChatIn(BaseModel):
    message: str
    history: list | None = None


@app.get("/health")
def health():
    """
    Runtime yêu cầu endpoint này trả 200. Trả kèm chế độ đang chạy để nhìn một cái
    là biết agent đang dùng model thật hay mock — kiểm tra bắt buộc sau mỗi lần deploy.
    """
    return {"status": "ok", "mode": "mock" if USE_MOCK else "real"}


@app.post("/chat")
def chat(body: ChatIn, x_actor_id: str = Header(default=None)):
    """
    Danh tính đến từ HEADER, không từ body — người hỏi không tự khai mình là ai.
    Production: thay bằng claim trong JWT do gateway xác thực. Đổi đúng dòng này.
    """
    if not x_actor_id:
        raise HTTPException(status_code=401, detail="Thiếu X-Actor-Id")
    return runtime.answer(llm(), x_actor_id, body.message, body.history)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
