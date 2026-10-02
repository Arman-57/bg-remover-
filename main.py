import io
import time
from collections import defaultdict, deque
from pathlib import Path

import onnxruntime as ort
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response
from PIL import Image, ImageOps

try:
    ort.preload_dlls()  # picks up pip-installed CUDA/cuDNN on GPU machines
except Exception:
    pass

from rembg import new_session, remove  # noqa: E402

BASE = Path(__file__).parent
MAX_BYTES = 10 * 1024 * 1024
MAX_SIDE = 1000
RATE_LIMIT, RATE_WINDOW = 10, 60  # requests per IP per seconds

MODELS = {"fast": "u2netp"}
PROVIDERS = [
    p for p in ("CUDAExecutionProvider", "CPUExecutionProvider")
    if p in ort.get_available_providers()
]
DEVICE = "GPU" if "CUDAExecutionProvider" in PROVIDERS else "CPU"

app = FastAPI(title="BG Remover")
_sessions = {}
_hits = defaultdict(deque)


def get_session(name: str):
    if name not in _sessions:
        _sessions[name] = new_session(name, providers=PROVIDERS)
    return _sessions[name]


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limited(ip: str) -> bool:
    now = time.time()
    q = _hits[ip]
    while q and now - q[0] > RATE_WINDOW:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        return True
    q.append(now)
    return False

def process(data: bytes, model: str):
    img = Image.open(io.BytesIO(data))
    img.draft("RGB", (MAX_SIDE, MAX_SIDE))  # JPEGs decode at reduced size
    img = ImageOps.exif_transpose(img)
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    img = img.convert("RGBA")
    t = time.perf_counter()
    out = remove(img, session=get_session(model))
    ms = int((time.perf_counter() - t) * 1000)
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue(), ms

@app.post("/api/remove-bg")
async def remove_bg(
    request: Request,
    file: UploadFile = File(...),
    quality: str = Form("fast"),
):
    if rate_limited(client_ip(request)):
        raise HTTPException(429, "Too many requests, try again in a minute")
    if quality not in MODELS:
        raise HTTPException(400, "Invalid quality option")
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "Upload an image file")
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Max file size is 10MB")
    try:
        png, ms = await run_in_threadpool(process, data, MODELS[quality])
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "Could not process this image")
    return Response(
        png,
        media_type="image/png",
        headers={
            "X-Process-Ms": str(ms),
            "X-Device": DEVICE,
            "Access-Control-Expose-Headers": "X-Process-Ms, X-Device",
        },
    )


@app.get("/health")
def health():
    return {"status": "ok", "device": DEVICE}


@app.get("/")
def index():
    return FileResponse(BASE / "static" / "index.html")
