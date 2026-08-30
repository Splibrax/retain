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

from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

from agent import digest, digest_email, runtime
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


UI_FILE = Path(__file__).parent / "ui" / "index.html"


@app.get("/", include_in_schema=False)
def home():
    """
    Giao diện hội thoại, do CHÍNH agent phục vụ.

    Đặt ở đây thay vì mở file HTML trên máy là có lý do kỹ thuật, không phải cho gọn:
    trang và API cùng một nguồn (same-origin) nên trình duyệt không chặn. Mở file
    bằng nhấp đúp rồi gọi sang endpoint là gọi chéo nguồn — trình duyệt gửi yêu cầu
    kiểm tra trước, server không có CORS nên từ chối, và giao diện trắng trơn không
    báo gì. Kiểu lỗi phát hiện lúc đang demo là hỏng cả buổi.

    Hệ quả tiện lợi: chạy ở máy (localhost:8080) hay trên mây đều dùng
    location.origin, không phải sửa gì khi deploy.
    """
    if not UI_FILE.exists():
        raise HTTPException(status_code=404, detail="Chưa có ui/index.html trong image")
    return FileResponse(
        UI_FILE,
        media_type="text/html; charset=utf-8",
        # CẤM LƯU ĐỆM.
        #
        # Không có dòng này thì sau khi deploy bản mới, trình duyệt vẫn dựng lại
        # trang cũ đã lưu sẵn — code mới nằm trong container mà màn hình vẫn hành
        # xử như bản cũ. Mất rất nhiều thời gian để nhận ra, vì mọi thứ phía máy
        # chủ đều đúng. Trang này nhẹ và chỉ vài người dùng, không cần lưu đệm.
        headers={"Cache-Control": "no-store, must-revalidate"},
    )


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


@app.get("/digest", response_class=HTMLResponse)
def digest_preview(actor: str = "", narrative: int = 0,
                   x_actor_id: str = Header(default=None)):
    """
    Xem trước bản tin ngay trên trình duyệt — để demo không phải mở hộp thư.

    Bản tin thật do send_digest.py chạy theo lịch gửi đi; endpoint này chỉ dựng
    lại đúng nội dung đó. Cùng một hàm build_digest, cùng một resolve_scope:
    đổi kênh KHÔNG được phép đổi quyền.

    Danh tính nhận qua header như /chat, hoặc qua ?actor= để bấm được từ thanh
    địa chỉ lúc demo — cả hai đều là danh tính tự khai, đúng như mô hình của bản POC.
    """
    aid = x_actor_id or actor
    if not aid:
        raise HTTPException(status_code=401, detail="Thiếu X-Actor-Id hoặc ?actor=")
    payload = digest.build_digest(aid)
    text = None
    if narrative and not payload.get("error"):
        n = digest.narrative(llm(), payload)
        text = n.get("text")          # guard trượt → None → bản tin ra không có đoạn nhận xét
    return HTMLResponse(
        content=digest_email.render_html(payload, text,
                                         app_url=os.environ.get("RETAIN_APP_URL", "")),
        media_type="text/html; charset=utf-8",
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
