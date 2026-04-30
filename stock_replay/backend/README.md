# Backend Environment

Use the repository-local virtual environment:

```powershell
E:\atas回放系统\stock_replay\.venv\Scripts\Activate.ps1
python -m pip install -r E:\atas回放系统\stock_replay\backend\requirements.txt
```

Core runtime:

- FastAPI and Uvicorn for local API/WebSocket service.
- Polars, DuckDB, PyArrow, and Parquet for data import/cache/query.
- SQLite through Python standard library for local metadata.
