import csv
import io
import re
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE = Path(__file__).resolve().parent
DB_PATH = BASE / "finance.db"

# Finds index.html next to this file, in ./frontend, or in ../frontend
FRONTEND = next(
    (p for p in (BASE / "frontend", BASE.parent / "frontend", BASE) if (p / "index.html").exists()),
    None,
)
if FRONTEND is None:
    raise RuntimeError("index.html not found. Put it next to main.py or in a 'frontend' folder.")

# Category -> keywords. First match wins, so order matters.
RULES = {
    "Income": ["salary", "payroll", "deposit", "refund", "interest paid"],
    "Housing": ["rent", "mortgage", "apartments", "landlord"],
    "Groceries": ["whole foods", "trader joe", "walmart", "kroger", "grocery", "supermarket", "bigbasket", "dmart"],
    "Dining": ["starbucks", "restaurant", "pizza", "cafe", "coffee", "mcdonald", "zomato", "swiggy", "doordash"],
    "Transport": ["uber", "lyft", "ola", "fuel", "shell", "chevron", "metro", "parking"],
    "Subscriptions": ["netflix", "spotify", "prime video", "disney", "hulu", "youtube premium"],
    "Utilities": ["electric", "water bill", "internet", "broadband", "gas bill", "phone bill"],
    "Health": ["pharmacy", "cvs", "clinic", "hospital", "gym", "doctor"],
    "Shopping": ["amazon", "flipkart", "target", "ebay", "mall"],
}
CATEGORIES = list(RULES) + ["Other"]

DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%d %b %Y", "%d/%m/%y", "%b %d, %Y"]


def categorize(description: str, amount: float) -> str:
    text = description.lower()
    for category, words in RULES.items():
        if category == "Income" and amount < 0:
            continue
        if any(w in text for w in words):
            return category
    return "Income" if amount > 0 else "Other"


def parse_date(raw: str) -> str:
    raw = raw.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date: {raw!r}")


def parse_amount(raw: str) -> float:
    raw = (raw or "").strip()
    if not raw:
        return 0.0
    negative = (raw.startswith("(") and raw.endswith(")")) or raw.startswith("-")
    value = float(re.sub(r"[^\d.]", "", raw) or 0)
    return -value if negative else value


def find_col(headers, *needles):
    for h in headers:
        if any(n in h for n in needles):
            return h
    return None


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                description TEXT NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                UNIQUE(date, description, amount)
            )"""
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Finance Dashboard", lifespan=lifespan)


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    text = (await file.read()).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(400, "The file is empty or has no header row.")

    headers = {h.strip().lower(): h for h in reader.fieldnames}
    keys = list(headers)
    date_k = find_col(keys, "date")
    desc_k = find_col(keys, "description", "details", "narration", "payee", "memo", "particulars")
    amount_k = find_col(keys, "amount")
    debit_k = find_col(keys, "debit", "withdrawal")
    credit_k = find_col(keys, "credit", "deposit")

    if not date_k or not desc_k or not (amount_k or debit_k or credit_k):
        raise HTTPException(
            400,
            "Could not find the columns. Include a date, a description, and either "
            "an amount or debit/credit columns.",
        )

    added = skipped = 0
    errors = []
    with db() as conn:
        for line_no, row in enumerate(reader, start=2):
            try:
                date = parse_date(row[headers[date_k]])
                desc = row[headers[desc_k]].strip()
                if amount_k:
                    amount = parse_amount(row[headers[amount_k]])
                else:
                    debit = parse_amount(row.get(headers[debit_k], "") if debit_k else "")
                    credit = parse_amount(row.get(headers[credit_k], "") if credit_k else "")
                    amount = abs(credit) - abs(debit)
                cur = conn.execute(
                    "INSERT OR IGNORE INTO transactions (date, description, amount, category) VALUES (?,?,?,?)",
                    (date, desc, amount, categorize(desc, amount)),
                )
                added += cur.rowcount
                skipped += 1 - cur.rowcount
            except (ValueError, KeyError, AttributeError) as e:
                errors.append(f"Line {line_no}: {e}")
    return {"added": added, "duplicates_skipped": skipped, "errors": errors[:10]}


@app.get("/api/transactions")
def transactions(category: str | None = None, limit: int = 500):
    sql = "SELECT * FROM transactions"
    params: list = []
    if category:
        sql += " WHERE category = ?"
        params.append(category)
    sql += " ORDER BY date DESC, id DESC LIMIT ?"
    params.append(limit)
    with db() as conn:
        return [dict(r) for r in conn.execute(sql, params)]


class CategoryUpdate(BaseModel):
    category: str


@app.patch("/api/transactions/{tx_id}")
def recategorize(tx_id: int, body: CategoryUpdate):
    if body.category not in CATEGORIES:
        raise HTTPException(400, "Unknown category.")
    with db() as conn:
        cur = conn.execute("UPDATE transactions SET category=? WHERE id=?", (body.category, tx_id))
    if cur.rowcount == 0:
        raise HTTPException(404, "Transaction not found.")
    return {"ok": True}


@app.delete("/api/transactions")
def clear_all():
    with db() as conn:
        conn.execute("DELETE FROM transactions")
    return {"ok": True}


@app.get("/api/categories")
def categories():
    return CATEGORIES


@app.get("/api/summary")
def summary():
    with db() as conn:
        totals = conn.execute(
            """SELECT COALESCE(SUM(CASE WHEN amount>0 THEN amount END),0) AS income,
                      COALESCE(SUM(CASE WHEN amount<0 THEN -amount END),0) AS expenses
               FROM transactions"""
        ).fetchone()
        by_cat = conn.execute(
            """SELECT category, SUM(-amount) AS total FROM transactions
               WHERE amount<0 GROUP BY category ORDER BY total DESC"""
        ).fetchall()
        monthly = conn.execute(
            """SELECT substr(date,1,7) AS month,
                      COALESCE(SUM(CASE WHEN amount>0 THEN amount END),0) AS income,
                      COALESCE(SUM(CASE WHEN amount<0 THEN -amount END),0) AS expenses
               FROM transactions GROUP BY month ORDER BY month"""
        ).fetchall()
    return {
        "income": totals["income"],
        "expenses": totals["expenses"],
        "net": totals["income"] - totals["expenses"],
        "by_category": [dict(r) for r in by_cat],
        "monthly": [dict(r) for r in monthly],
    }


# Mounted last so the /api routes take priority.
app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
