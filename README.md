# Finance Dashboard

A small personal finance dashboard. Upload a CSV exported from your bank and get instant totals, a monthly income vs. spending chart, a category breakdown, and a transaction list you can recategorize. Data is stored locally in SQLite, so nothing leaves your machine.

![Finance Dashboard](screenshots/dashboard.png)

*Screenshot shows the included `sample_transactions.csv` loaded.*

## Features

- **CSV import** with flexible column detection (`date`, `description`/`details`/`narration`/`payee`/`memo`/`particulars`, and either `amount` or separate `debit`/`credit` columns)
- **Multiple date formats** (`2026-07-01`, `01/07/2026`, `01 Jul 2026`, `Jul 01, 2026`, and more)
- **Automatic categorization** by keyword (Housing, Groceries, Dining, Transport, Subscriptions, Utilities, Health, Shopping, Income, Other)
- **Duplicate protection**: re-uploading the same file won't double-count transactions
- **Manual recategorization** from a dropdown on any row, plus a category filter
- **KPI cards**: income, spent, left over (or overspent), and savings rate
- **Charts** (Chart.js): income vs. spending by month, and spending by category
- **Full-screen mode** and a layout that adapts to small screens

## Tech stack

- **Backend:** Python, FastAPI, SQLite
- **Frontend:** Vanilla HTML/CSS/JS with Chart.js (loaded from a CDN)

## Project structure

```
.
├── main.py                   # FastAPI app and API routes
├── index.html                # Single-page frontend
├── requirement.txt           # Python dependencies
├── sample_transactions.csv   # Example data to try the app
├── finance.db                # SQLite database (created automatically)
└── screenshots/
    └── dashboard.png
```

## Getting started

1. **Install dependencies** (Python 3.10+):

   ```bash
   pip install -r requirement.txt
   ```

2. **Run the app:**

   ```bash
   python main.py
   ```

3. **Open** <http://127.0.0.1:8000> and click **Upload bank CSV**. Try `sample_transactions.csv` first.

You can also run it with auto-reload during development:

```bash
uvicorn main:app --reload
```

## CSV format

The minimum is a date, a description, and an amount:

```csv
Date,Description,Amount
2026-07-01,ACME CORP SALARY,3200.00
2026-07-02,CITY APARTMENTS RENT,-1100.00
2026-07-03,WHOLE FOODS MARKET,-86.40
```

Negative amounts are expenses and positive amounts are income. Amounts in parentheses, like `(45.00)`, are treated as negative. If your bank uses separate **Debit** and **Credit** columns instead, that works too.

## API

| Method | Endpoint | Description |
| --- | --- | --- |
| `POST` | `/api/upload` | Upload a CSV (multipart field `file`) |
| `GET` | `/api/transactions?category=&limit=` | List transactions, newest first |
| `PATCH` | `/api/transactions/{id}` | Change a transaction's category |
| `DELETE` | `/api/transactions` | Delete all transactions |
| `GET` | `/api/categories` | List available categories |
| `GET` | `/api/summary` | Totals, monthly breakdown, and spending by category |

Interactive docs are available at <http://127.0.0.1:8000/docs> while the app is running.

## Customizing categories

Edit the `RULES` dictionary at the top of `main.py`. Each category maps to a list of lowercase keywords, and the first match wins, so order matters. If you add a new category, add a color for it in the `COLORS` object in `index.html` too.

## Notes

- Deleting data is permanent. **Clear all data** wipes every transaction in `finance.db`.
- The server binds to `127.0.0.1` only, so it isn't reachable from other devices on your network.
- Chart.js and the Google Font load from CDNs, so the first load needs an internet connection.
