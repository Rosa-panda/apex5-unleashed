# routers 公共帮手（ADR-029 B2）
from fastapi.responses import JSONResponse


def err(e):
    return JSONResponse({"error": str(e)}, status_code=400)
