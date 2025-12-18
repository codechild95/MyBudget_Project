import os
from dotenv import load_dotenv
load_dotenv()
from datetime import datetime
import sqlite3

from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import List, Optional

from openai import OpenAI

# --------------------------
# 🔥 .env 로드
# --------------------------
env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv("C:/Users/Administrator/Desktop/SideProject/my_budget_app/.env")
print("🔥 OPENAI_API_KEY =", os.environ.get("OPENAI_API_KEY"))

# --------------------------
# 🌐 FastAPI 기본 설정
# --------------------------
app = FastAPI()
templates = Jinja2Templates(directory="templates")


# =========================================================
# ✨ 데이터베이스 초기화
# =========================================================
def init_db():
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            type TEXT,
            title TEXT,
            amount INTEGER,
            category TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()


# =========================================================
# ✨ 공용 함수
# =========================================================
def get_openai_client():
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise Exception("OPENAI_API_KEY is missing")
    return OpenAI(api_key=key)


def get_summary():
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute("SELECT SUM(amount) FROM records WHERE type='income'")
    income = cur.fetchone()[0] or 0

    cur.execute("SELECT SUM(amount) FROM records WHERE type='expense'")
    expense = cur.fetchone()[0] or 0

    conn.close()
    return income, expense


def get_monthly_stats_full():
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT substr(date, 1, 7) AS month,
               SUM(CASE WHEN type='income' THEN amount ELSE 0 END),
               SUM(CASE WHEN type='expense' THEN amount ELSE 0 END)
        FROM records
        GROUP BY month
        ORDER BY month
    """)
    rows = cur.fetchall()
    conn.close()

    return [
        {
            "month": r[0],
            "income": r[1] or 0,
            "expense": r[2] or 0,
            "profit": (r[1] or 0) - (r[2] or 0)
        }
        for r in rows
    ]


def get_category_stats(month: Optional[str] = None):
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    if month:
        cur.execute("""
            SELECT 
                CASE WHEN category IS NULL OR category='' THEN '기타' ELSE category END AS cat,
                SUM(amount)
            FROM records
            WHERE type='expense' AND substr(date, 1, 7)=?
            GROUP BY cat
        """, (month,))
    else:
        cur.execute("""
            SELECT 
                CASE WHEN category IS NULL OR category='' THEN '기타' ELSE category END AS cat,
                SUM(amount)
            FROM records
            WHERE type='expense'
            GROUP BY cat
        """)

    rows = cur.fetchall()
    conn.close()

    return [{"category": r[0], "total": r[1]} for r in rows]


def get_recent_records(limit: int = 30):
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT id, date, type, title, amount, category
        FROM records
        ORDER BY date DESC, id DESC
        LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    conn.close()

    return [
        {
            "id": r[0],
            "date": r[1],
            "type": r[2],
            "title": r[3],
            "amount": r[4],
            "category": r[5],
        }
        for r in rows
    ]


# =========================================================
# 🌍 라우팅
# =========================================================

@app.get("/")
def index(request: Request):
    income, expense = get_summary()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "income": income,
        "expense": expense
    })


@app.get("/records")
def get_records(date: str):
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT id, date, type, title, amount, category
        FROM records
        WHERE date=?
    """, (date,))
    rows = cur.fetchall()
    conn.close()

    return [
        {
            "id": r[0],
            "date": r[1],
            "type": r[2],
            "title": r[3],
            "amount": r[4],
            "category": r[5]
        }
        for r in rows
    ]


@app.get("/records/all")
def get_all_records():
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("SELECT date, type, amount FROM records")
    rows = cur.fetchall()
    conn.close()
    return [{"date": r[0], "type": r[1], "amount": r[2]} for r in rows]


@app.post("/add")
def add_record(
    date: str = Form(...),
    type: str = Form(...),
    title: str = Form(...),
    amount: int = Form(...),
    category: str = Form(...)
):
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO records(date, type, title, amount, category)
        VALUES (?, ?, ?, ?, ?)
    """, (date, type, title, amount, category))
    conn.commit()
    conn.close()

    return RedirectResponse("/", status_code=303)


# =========================================================
# ❌ 삭제 API (캘린더 내역 삭제)
# =========================================================
@app.delete("/records/{record_id}")
def delete_record(record_id: int):
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("DELETE FROM records WHERE id=?", (record_id,))
    conn.commit()
    conn.close()
    return {"status": "ok", "deleted_id": record_id}


# =========================================================
# 📊 통계 API
# =========================================================

# 월별 통계
@app.get("/stats/monthly")
def stats_monthly():
    return get_monthly_stats_full()


# 연도별 통계
@app.get("/stats/yearly")
def stats_yearly():
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT substr(date, 1, 4) AS year,
               SUM(CASE WHEN type='income' THEN amount ELSE 0 END),
               SUM(CASE WHEN type='expense' THEN amount ELSE 0 END)
        FROM records
        GROUP BY year
        ORDER BY year
    """)
    rows = cur.fetchall()
    conn.close()

    return [
        {"year": r[0], "income": r[1] or 0, "expense": r[2] or 0}
        for r in rows
    ]


# 카테고리별 지출
@app.get("/stats/categories")
def category_stats_all():
    return get_category_stats()


# 이번 달 지출
@app.get("/stats/current_month")
def current_month_stats():
    now = datetime.now()
    ym = now.strftime("%Y-%m")

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT SUM(amount)
        FROM records
        WHERE type='expense' AND substr(date, 1, 7)=?
    """, (ym,))
    total = cur.fetchone()[0] or 0
    conn.close()

    return {"month": ym, "total_expense": total}


# =========================================================
# 🤖 AI Agent (OpenAI 연결)
# =========================================================

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    history: Optional[List[ChatMessage]] = None


@app.post("/agent/chat")
def agent_chat(req: ChatRequest):

    monthly = get_monthly_stats_full()
    categories_all = get_category_stats()
    recent = get_recent_records(30)

    system_prompt = (
        "너는 개인 가계부 분석을 도와주는 한국어 경제 도우미야. "
        "아래 사용자 가계부 데이터를 기반으로만 대답하고, "
        "추측하지 말고 필요한 정보는 요청해줘."
    )

    context_text = (
        f"### 월별 통계\n{monthly}\n\n"
        f"### 카테고리별 지출\n{categories_all}\n\n"
        f"### 최근 30건 거래\n{recent}\n\n"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": context_text},
    ]

    if req.history:
        for m in req.history:
            messages.append({"role": m.role, "content": m.content})

    messages.append({"role": "user", "content": req.message})

    client = get_openai_client()
    response = client.responses.create(
        model="gpt-4o-mini",
        input=messages
    )

    reply = "(응답 없음)"
    try:
        output = response.output[0].content[0].text
        reply = output
    except:
        reply = "(응답 처리 중 오류 발생)"

    return {"reply": reply}
