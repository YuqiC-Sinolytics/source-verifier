import json

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from . import cache
from .config import ROOT, cfg
from .examples import load_all as load_examples
from .pipeline import run

app = FastAPI(title="Source Verifier")
STATIC = ROOT / "static"


class VerifyReq(BaseModel):
    text: str
    repair: bool = True


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
async def health():
    return {"ok": True, "mock": cfg.mock, "model": cfg.verify_model}


@app.get("/api/examples")
async def examples():
    return {"examples": load_examples()}


@app.get("/api/sample")
async def sample():
    """Kept for older links — returns the first example."""
    ex = load_examples()
    return {"text": ex[0]["text"] if ex else ""}


@app.post("/api/cache/clear")
async def clear_cache():
    return {"cleared": cache.clear()}


@app.post("/api/verify")
async def verify(req: VerifyReq):
    """NDJSON stream.

    NDJSON rather than SSE because EventSource is GET-only and we need to POST a
    whole document. fetch + ReadableStream on the client is just as streaming and
    takes less code.
    """

    async def gen():
        try:
            async for event in run(req.text, do_repair=req.repair):
                yield json.dumps(event, ensure_ascii=False) + "\n"
        except Exception as e:  # never let an exception become a silent hang
            yield json.dumps({"type": "error", "message": f"{type(e).__name__}: {e}"}) + "\n"

    return StreamingResponse(
        gen(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
