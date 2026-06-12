import os

project_dir = r"C:\Users\omaar\Downloads\project"

# Update main.py
main_path = os.path.join(project_dir, r"src\suspensionlab\backend\api\main.py")
with open(main_path, "r", encoding="utf-8") as f:
    content = f.read()

# Fix /metrics
old_metrics = """@app.get("/metrics")
async def metrics():
    \"\"\"Exposes Prometheus metrics for scraping.\"\"\"
    return Response(generate_latest(), media_type="text/plain")"""
new_metrics = """@app.get("/metrics", dependencies=[Depends(verify_api_key)])
async def metrics():
    \"\"\"Exposes Prometheus metrics for scraping.\"\"\"
    return Response(generate_latest(), media_type="text/plain")"""
content = content.replace(old_metrics, new_metrics)

# Fix /ready
old_ready = """@app.get("/ready")
async def readiness():
    # Check DB is reachable
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ready", "db": "ok"}
    except Exception:
        from suspensionlab.backend.core.errors import DatabaseUnavailableError
        raise DatabaseUnavailableError()"""
new_ready = """@app.get("/ready")
async def readiness():
    # Check DB is reachable
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ready", "db": "ok"}
    except Exception:
        raise HTTPException(status_code=503, detail="Database is unavailable")"""
content = content.replace(old_ready, new_ready)

with open(main_path, "w", encoding="utf-8") as f:
    f.write(content)

print("main.py refactored.")
