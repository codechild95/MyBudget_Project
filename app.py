from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, JSONResponse
import sqlite3

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# DB 초기화
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

# 총 수입/지출 계산
def get_summary():
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute("SELECT SUM(amount) FROM records WHERE type='income'")
    income = cur.fetchone()[0] or 0

    cur.execute("SELECT SUM(amount) FROM records WHERE type='expense'")
    expense = cur.fetchone()[0] or 0

    conn.close()
    return income, expense

@app.get("/")
def index(request: Request):
    income, expense = get_summary()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "income": income,
        "expense": expense
    })

# 👉 특정 날짜의 내역 가져오기
@app.get("/records")
def get_records(date: str):
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("SELECT id, date, type, title, amount, category FROM records WHERE date=?", (date,))
    rows = cur.fetchall()
    conn.close()

    return [
        {"id": r[0], "date": r[1], "type": r[2], "title": r[3], "amount": r[4], "category": r[5]}
    for r in rows]

# 👉 모든 기록 달력용
@app.get("/records/all")
def get_all_records():
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("SELECT date, type, amount FROM records")
    rows = cur.fetchall()
    conn.close()

    return [{"date": r[0], "type": r[1], "amount": r[2]} for r in rows]

# 👉 월별 통계 제공
@app.get("/stats/monthly")
def get_monthly_stats():
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute("""
        SELECT substr(date, 1, 7) AS month,
        SUM(CASE WHEN type='income' THEN amount ELSE 0 END),
        SUM(CASE WHEN type='expense' THEN amount ELSE 0 END)
        FROM records GROUP BY month
    """)
    rows = cur.fetchall()
    conn.close()

    return [{"month": r[0], "income": r[1], "expense": r[2]} for r in rows]

# 👉 기록 추가
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
    cur.execute("INSERT INTO records(date, type, title, amount, category) VALUES (?, ?, ?, ?, ?)",
                (date, type, title, amount, category))
    conn.commit()
    conn.close()

    return RedirectResponse("/", status_code=303)
