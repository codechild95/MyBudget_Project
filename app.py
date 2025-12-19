import os
from dotenv import load_dotenv
load_dotenv()
from datetime import datetime
import sqlite3

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import List, Optional
from openai import OpenAI
import keyring



# --------------------------
#  .env 로드
# --------------------------
env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv("C:/Users/Administrator/Desktop/SideProject/my_budget_app/.env")
print(" OPENAI_API_KEY =", os.environ.get("OPENAI_API_KEY"))

# --------------------------
#  FastAPI 기본 설정
# --------------------------
app = FastAPI()
templates = Jinja2Templates(directory="templates")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")

# =========================
# DB
# =========================
def get_db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_db()
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

@app.on_event("startup")
def on_startup():
    init_db()

# =========================
# OpenAI Client (요청 시 생성)
# =========================
def get_openai_client():
    api_key = keyring.get_password("my_budget_app", "open_api_key")
    if not api_key:
        raise Exception("OPENAI_API_KEY is missing")
    return OpenAI(api_key=api_key)

# =========================
# Models
# =========================
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    history: Optional[List[ChatMessage]] = None

class APIKeyRequest(BaseModel):
    api_key: str

class OpenAIKeyRequest(BaseModel):
    api_key: str

@app.post("/settings/openai-key")
def save_openai_key(req: OpenAIKeyRequest):
    if not req.api_key.startswith("sk-"):
        raise HTTPException(status_code=400, detail="Invalid API Key")

    # Windows Credential Manager에 저장
    keyring.set_password(
        "my_budget_app",   # 서비스 이름
        "openai_api_key",  # 계정 이름
        req.api_key
    )

    return {"status": "ok"}
# =========================
# API KEY 저장
# =========================
@app.post("/settings/openai-key")
def save_openai_key(req: APIKeyRequest):
    import keyring
    keyring.set_password("MyBudgetApp", "openai_api_key", req.api_key)
    return {"status": "saved"}

# =========================
# 기본 페이지
# =========================
@app.get("/")
def index(request: Request):
    income, expense = get_summary()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "income": income,
            "expense": expense,
        },
    )

# =========================
# 가계부 CRUD
# =========================
@app.post("/add")
def add_record(
    date: str = Form(...),
    type: str = Form(...),
    title: str = Form(...),
    amount: int = Form(...),
    category: str = Form(...),
):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO records (date, type, title, amount, category) VALUES (?, ?, ?, ?, ?)",
        (date, type, title, amount, category),
    )
    conn.commit()
    conn.close()
    return RedirectResponse("/", status_code=303)

@app.delete("/records/{record_id}")
def delete_record(record_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM records WHERE id=?", (record_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}

@app.get("/records")
def get_records(date: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, date, type, title, amount, category FROM records WHERE date=?",
        (date,),
    )
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

@app.get("/records/all")
def get_all_records():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT date, type, amount FROM records")
    rows = cur.fetchall()
    conn.close()
    return [{"date": r[0], "type": r[1], "amount": r[2]} for r in rows]

# =========================
# 통계
# =========================
def get_summary():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT SUM(amount) FROM records WHERE type='income'")
    income = cur.fetchone()[0] or 0
    cur.execute("SELECT SUM(amount) FROM records WHERE type='expense'")
    expense = cur.fetchone()[0] or 0
    conn.close()
    return income, expense

@app.get("/stats/monthly")
def stats_monthly():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT substr(date,1,7) AS month,
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
        }
        for r in rows
    ]

@app.get("/stats/categories")
def stats_categories():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            CASE WHEN category IS NULL OR category='' THEN '기타' ELSE category END,
            SUM(amount)
        FROM records
        WHERE type='expense'
        GROUP BY category
    """)
    rows = cur.fetchall()
    conn.close()
    return [{"category": r[0], "total": r[1]} for r in rows]

@app.get("/stats/current_month")
def stats_current_month():
    ym = datetime.now().strftime("%Y-%m")
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT SUM(amount) FROM records WHERE type='expense' AND substr(date,1,7)=?",
        (ym,),
    )
    total = cur.fetchone()[0] or 0
    conn.close()
    return {"month": ym, "total_expense": total}

# =========================
#  가계부 경제 Agent
# =========================
@app.post("/agent/chat")
def agent_chat(req: ChatRequest):
    client = get_openai_client()

    monthly = stats_monthly()
    categories = stats_categories()

    system_prompt = (
        "너는 개인 가계부 분석을 도와주는 한국어 경제 도우미야. "
        "주어진 가계부 데이터만 기반으로 답변해."
    )

    input_items = [
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": f"월별 통계: {monthly}"},
        {"role": "system", "content": f"카테고리 지출: {categories}"},
    ]

    if req.history:
        for h in req.history:
            input_items.append({"role": h.role, "content": h.content})

    input_items.append({"role": "user", "content": req.message})

    response = client.responses.create(
        model="gpt-4o-mini",
        input=input_items,
    )

    reply = ""
    if response.output:
        reply = response.output[0].content[0].text

    return {"reply": reply or "(응답이 비어있어요)"}

