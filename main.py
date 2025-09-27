import asyncio
import os
import sys
import tempfile
from typing import List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Unlimited Runner API", version="0.1.0")

# 완화된 제한
MAX_STDOUT_BYTES = 2_000_000  # 2MB
EXEC_TIMEOUT = 120            # 120s
PIP_TIMEOUT = 600             # 10m

class RunPythonBody(BaseModel):
    code: str

class PipBody(BaseModel):
    packages: List[str]

@app.get("/health")
async def health():
    return {"ok": True}

@app.post("/run-python")
async def run_python(body: RunPythonBody):
    # 코드 파일로 저장 후 실행
    with tempfile.TemporaryDirectory() as td:
        code_path = os.path.join(td, "snippet.py")
        with open(code_path, "w", encoding="utf-8") as f:
            f.write(body.code)

        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, code_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=EXEC_TIMEOUT)
            except asyncio.TimeoutError:
                proc.kill()
                raise HTTPException(status_code=408, detail="Execution timed out")

            return {
                "returncode": proc.returncode,
                "stdout": stdout[:MAX_STDOUT_BYTES].decode("utf-8", errors="replace"),
                "stderr": stderr[:MAX_STDOUT_BYTES].decode("utf-8", errors="replace"),
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

@app.post("/pip")
async def pip_install(body: PipBody):
    pkgs = [p.strip() for p in body.packages if p.strip()]
    if not pkgs:
        raise HTTPException(status_code=400, detail="No packages provided")

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "pip", "install", "--no-input", *pkgs,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=PIP_TIMEOUT)
        except asyncio.TimeoutError:
            proc.kill()
            raise HTTPException(status_code=408, detail="pip install timed out")

        return {
            "returncode": proc.returncode,
            "stdout": stdout[:MAX_STDOUT_BYTES].decode("utf-8", errors="replace"),
            "stderr": stderr[:MAX_STDOUT_BYTES].decode("utf-8", errors="replace"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "7860"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, workers=1)