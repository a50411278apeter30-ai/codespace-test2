import asyncio
import os
import sys
import tempfile
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# =========================
# 설정
# =========================
PORT = int(os.environ.get("PORT", "7860"))
EXEC_TIMEOUT = int(os.environ.get("EXEC_TIMEOUT", "60"))      # 코드 실행 타임아웃(초)
PIP_TIMEOUT = int(os.environ.get("PIP_TIMEOUT", "600"))       # pip 설치 타임아웃(초)
MAX_STDOUT = int(os.environ.get("MAX_STDOUT", "1000000"))     # 최대 출력 바이트(기본 1MB)

# 네트워크 허용 여부(기본 허용). 필요하면 False로 바꾸고 allow_network=True일 때만 열어도 됨.
DEFAULT_ALLOW_NETWORK = os.environ.get("DEFAULT_ALLOW_NETWORK", "true").lower() == "true"

# =========================
# 앱 초기화
# =========================
app = FastAPI(title="Codespace Proxy Backend", version="1.0.0")

# CORS 전면 허용 (프런트가 어디에 있어도 붙게)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# 모델
# =========================
class RunPythonBody(BaseModel):
    code: str
    allow_network: Optional[bool] = None  # None면 DEFAULT_ALLOW_NETWORK 따름

class PipBody(BaseModel):
    packages: List[str]

# =========================
# 헬스
# =========================
@app.get("/health")
async def health():
    return {
        "ok": True,
        "port": PORT,
        "exec_timeout": EXEC_TIMEOUT,
        "pip_timeout": PIP_TIMEOUT,
        "max_stdout": MAX_STDOUT,
    }

# =========================
# 파이썬 코드 실행
# =========================
@app.post("/run-python")
async def run_python(body: RunPythonBody, request: Request):
    allow_network = DEFAULT_ALLOW_NETWORK if body.allow_network is None else body.allow_network

    # 환경 변수로 네트워크 허용 신호 전달(원하면 iptables 등으로 실제 차단 구현 가능)
    env = os.environ.copy()
    env["RUN_NETWORK"] = "1" if allow_network else "0"

    # 임시 파일에 코드 쓰고 실행
    with tempfile.TemporaryDirectory() as td:
        code_path = os.path.join(td, "snippet.py")
        with open(code_path, "w", encoding="utf-8") as f:
            f.write(body.code)

        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, code_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=EXEC_TIMEOUT)
            except asyncio.TimeoutError:
                proc.kill()
                raise HTTPException(status_code=408, detail="Execution timed out")

            out = stdout[:MAX_STDOUT].decode("utf-8", errors="replace")
            err = stderr[:MAX_STDOUT].decode("utf-8", errors="replace")
            return {"returncode": proc.returncode, "stdout": out, "stderr": err}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

# =========================
# pip 설치
# =========================
@app.post("/pip")
async def pip_install(body: PipBody):
    pkgs = [p.strip() for p in body.packages if p.strip()]
    if not pkgs:
        raise HTTPException(status_code=400, detail="No packages provided")

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "pip", "install", "--no-input", *pkgs,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=PIP_TIMEOUT)
        except asyncio.TimeoutError:
            proc.kill()
            raise HTTPException(status_code=408, detail="pip install timed out")

        out = stdout[:MAX_STDOUT].decode("utf-8", errors="replace")
        err = stderr[:MAX_STDOUT].decode("utf-8", errors="replace")
        return {"returncode": proc.returncode, "stdout": out, "stderr": err}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =========================
# 로컬 실행 진입점
# =========================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=PORT, workers=1)
