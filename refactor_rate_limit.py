import os

filepath = r"C:\Users\omaar\Downloads\project\src\suspensionlab\backend\security\rate_limit.py"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# Fail closed on None connection
old_conn = """        if async_redis_conn is None:
            # Fail open if Redis is down, but realistically main.py initializes it
            return True"""
new_conn = """        if async_redis_conn is None:
            # Fail closed if Redis is down
            raise HTTPException(status_code=503, detail="Rate limiter unavailable")"""
content = content.replace(old_conn, new_conn)

# Fail closed on exception
old_except = """        except Exception:
            # Fallback fail-open if redis commands fail
            return True"""
new_except = """        except Exception:
            # Fallback fail-closed if redis commands fail
            raise HTTPException(status_code=503, detail="Rate limiter unavailable")"""
content = content.replace(old_except, new_except)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("rate_limit.py refactored.")
