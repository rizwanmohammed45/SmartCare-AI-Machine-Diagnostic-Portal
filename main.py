"""
Root main.py — entry point shim.
Delegates to backend.main so the server can be started from the project root with:
    python main.py
    uvicorn main:app --port 8000
"""
from backend.main import app  # noqa: F401 — re-exported for uvicorn

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
