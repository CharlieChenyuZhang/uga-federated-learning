"""Loopback-only local research API. Run a single uvicorn process."""

import hashlib
import json
import logging
import secrets
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import ml, store
from .data import parse_dataset, sample_rows

log = logging.getLogger("campus")
MODEL_LOCK = threading.Lock()
MAX_UPLOAD = 2 * 1024 * 1024


@asynccontextmanager
async def lifespan(app):
    store.initialize()
    yield


app = FastAPI(title="Campus local lab", lifespan=lifespan, docs_url="/docs")
app.add_middleware(
    TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
)


@app.middleware("http")
async def local_boundary(request: Request, call_next):
    origin = request.headers.get("origin")
    if (
        origin and origin not in {"http://127.0.0.1:3000", "http://localhost:3000"}
    ) or request.headers.get("sec-fetch-site") == "cross-site":
        return JSONResponse(
            {"detail": "Only the local website may access this API."}, status_code=403
        )
    # Chunked bodies are also bounded; do not depend on Content-Length.
    if request.method in {"POST", "PATCH", "DELETE"}:
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_UPLOAD + 16384:
                return JSONResponse(
                    {"detail": "Request exceeds the 2 MB upload limit."},
                    status_code=413,
                )
        request._body = bytes(body)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def current_user(request: Request):
    token = request.cookies.get("campus_session", "")
    row = store.one(
        "SELECT users.id,users.name,users.role,users.school_id FROM users JOIN sessions ON sessions.user_id=users.id WHERE sessions.token=? AND sessions.expires>?",
        (hashlib.sha256(token.encode()).hexdigest(), time.time()),
    )
    if not row:
        raise HTTPException(401, "Sign in to your local workspace.")
    return row


def contributor(user=Depends(current_user)):
    if user["role"] != "contributor":
        raise HTTPException(403, "Only a contributor can change institution data.")
    return user


class Login(BaseModel):
    account: str = Field(max_length=40)
    password: str = Field(max_length=200)


@app.post("/auth/login")
def login(body: Login, response: Response):
    row = store.one("SELECT * FROM users WHERE id=?", (body.account,))
    if not row or not secrets.compare_digest(
        row["password"], store.password_hash(body.password, row["salt"])
    ):
        raise HTTPException(401, "The account or password is incorrect.")
    token = secrets.token_urlsafe(32)
    store.execute(
        "INSERT INTO sessions VALUES (?,?,?)",
        (
            hashlib.sha256(token.encode()).hexdigest(),
            row["id"],
            time.time() + 12 * 3600,
        ),
    )
    response.set_cookie(
        "campus_session",
        token,
        httponly=True,
        samesite="strict",
        max_age=12 * 3600,
        path="/",
    )
    return {k: row[k] for k in ["id", "name", "role", "school_id"]}


@app.post("/auth/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get("campus_session", "")
    store.execute(
        "DELETE FROM sessions WHERE token=?",
        (hashlib.sha256(token.encode()).hexdigest(),),
    )
    response.delete_cookie("campus_session", path="/", samesite="strict")
    return {"ok": True}


@app.get("/auth/me")
def me(user=Depends(current_user)):
    return user


@app.get("/health")
def health():
    return {
        "ok": True,
        "ml_available": ml.available(),
        "model": ml.MODEL_ID,
        "busy": MODEL_LOCK.locked(),
        "mode": "local",
    }


@app.get("/overview")
def overview(user=Depends(current_user)):
    schools = []
    for school in store.SCHOOLS:
        # Only deliberately shared activity is visible to the network.
        shared = store.one(
            "SELECT COUNT(*) AS n FROM runs WHERE school_id=? AND shared=1 AND status='completed'",
            (school["id"],),
        )["n"]
        schools.append({**school, "shared_models": shared})
    return {"schools": schools, "runtime": health()}


@app.get("/datasets")
def datasets(user=Depends(contributor)):
    return store.rows(
        "SELECT id,school_id,name,row_count,created,synthetic FROM datasets WHERE school_id=? ORDER BY created DESC",
        (user["school_id"],),
    )


def save_dataset(name, rows, user, synthetic=False):
    dataset_id = secrets.token_hex(12)
    store.execute(
        "INSERT INTO datasets VALUES (?,?,?,?,?,?,?)",
        (
            dataset_id,
            user["school_id"],
            name,
            json.dumps(rows),
            len(rows),
            time.time(),
            int(synthetic),
        ),
    )
    return {
        "id": dataset_id,
        "name": name,
        "row_count": len(rows),
        "synthetic": synthetic,
    }


@app.post("/datasets", status_code=201)
async def upload(file: UploadFile = File(...), user=Depends(contributor)):
    content = await file.read(MAX_UPLOAD + 1)
    try:
        parsed = parse_dataset(content, file.filename or "")
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    return save_dataset(Path(file.filename or "dataset").name[:120], parsed, user)


@app.post("/datasets/sample", status_code=201)
def sample(user=Depends(contributor)):
    existing = store.one(
        "SELECT id,name,row_count,synthetic FROM datasets WHERE school_id=? AND synthetic=1",
        (user["school_id"],),
    )
    return existing or save_dataset(
        "Synthetic STEM coaching.jsonl", sample_rows(user["school_id"]), user, True
    )


@app.get("/datasets/template")
def template(user=Depends(contributor)):
    content = "\n".join(json.dumps(row) for row in sample_rows(user["school_id"]))
    return Response(
        content,
        media_type="application/x-ndjson",
        headers={"Content-Disposition": 'attachment; filename="campus-example.jsonl"'},
    )


@app.delete("/datasets/{dataset_id}")
def delete_dataset(dataset_id: str, user=Depends(contributor)):
    with store.connect() as db:
        row = db.execute(
            "SELECT id FROM datasets WHERE id=? AND school_id=?",
            (dataset_id, user["school_id"]),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Dataset not found.")
        if db.execute(
            "SELECT 1 FROM runs WHERE dataset_id=?", (dataset_id,)
        ).fetchone():
            raise HTTPException(
                409,
                "This dataset is linked to a training run and is retained for reproducibility.",
            )
        db.execute("DELETE FROM datasets WHERE id=?", (dataset_id,))
    return {"ok": True}


class TrainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_id: str
    steps: int = Field(default=8, ge=2, le=100)
    name: str = Field(default="STEM coaching adapter", min_length=1, max_length=80)


def training_worker(run, data):
    try:
        store.update_run(run["id"], status="running")
        metrics = ml.train(
            run,
            data,
            store.DATA / "adapters" / run["id"],
            lambda **updates: store.update_run(run["id"], **updates),
        )
        store.update_run(
            run["id"],
            status="completed",
            phase="Evaluation complete",
            metrics=metrics,
            finished=time.time(),
        )
    except Exception as error:
        # Never log training text or expose arbitrary filesystem details to other tenants.
        log.error("Training run %s failed (%s)", run["id"], type(error).__name__)
        message = (
            str(error)
            if isinstance(error, ValueError)
            else "The local model worker failed. Check model download access and available memory, then start a new run."
        )
        store.update_run(
            run["id"],
            status="failed",
            phase="Run failed",
            error=message,
            finished=time.time(),
        )
    finally:
        MODEL_LOCK.release()


@app.post("/runs", status_code=202)
def train(body: TrainRequest, user=Depends(contributor)):
    dataset = store.one(
        "SELECT * FROM datasets WHERE id=? AND school_id=?",
        (body.dataset_id, user["school_id"]),
    )
    if not dataset:
        raise HTTPException(404, "Dataset not found in your institution.")
    if not ml.available():
        raise HTTPException(
            503,
            "Install the local training dependencies: pip install -r backend/requirements-ml.txt",
        )
    if not MODEL_LOCK.acquire(blocking=False):
        raise HTTPException(
            409,
            "The local model is busy. Wait for the current training or response to finish.",
        )
    try:
        run_id = secrets.token_hex(12)
        store.execute(
            "INSERT INTO runs (id,school_id,dataset_id,name,status,steps,phase,created) VALUES (?,?,?,?,?,?,?,?)",
            (
                run_id,
                user["school_id"],
                body.dataset_id,
                body.name.strip() or "STEM coaching adapter",
                "queued",
                body.steps,
                "Preparing local worker",
                time.time(),
            ),
        )
        run = store.one("SELECT * FROM runs WHERE id=?", (run_id,))
        threading.Thread(
            target=training_worker, args=(run, json.loads(dataset["rows"])), daemon=True
        ).start()
    except Exception:
        MODEL_LOCK.release()
        raise
    return store.public_run(run, True)


@app.get("/runs")
def runs(user=Depends(current_user)):
    if user["role"] == "contributor":
        found = store.rows(
            "SELECT * FROM runs WHERE school_id=? ORDER BY created DESC",
            (user["school_id"],),
        )
        return [store.public_run(row, True) for row in found]
    return [
        store.public_run(row)
        for row in store.rows(
            "SELECT * FROM runs WHERE shared=1 AND status='completed' ORDER BY created DESC"
        )
    ]


@app.get("/models")
def models(user=Depends(current_user)):
    found = store.rows(
        "SELECT * FROM runs WHERE status='completed' AND (shared=1 OR school_id=?) ORDER BY created DESC",
        (user["school_id"],),
    )
    return [
        store.public_run(row, row["school_id"] == user["school_id"]) for row in found
    ]


@app.get("/runs/{run_id}/evaluation")
def export_evaluation(run_id: str, user=Depends(current_user)):
    run = store.one(
        "SELECT * FROM runs WHERE id=? AND (school_id=? OR shared=1)",
        (run_id, user["school_id"]),
    )
    if not run:
        raise HTTPException(404, "Evaluation not available to this account.")
    if run["status"] != "completed" or not run["metrics"]:
        raise HTTPException(409, "This run does not have a completed evaluation yet.")
    return JSONResponse(
        store.public_run(run, run["school_id"] == user["school_id"]),
        headers={
            "Content-Disposition": f'attachment; filename="campus-evaluation-{run["id"]}.json"'
        },
    )


class Sharing(BaseModel):
    shared: StrictBool
    acknowledge_risk: StrictBool = False


@app.patch("/runs/{run_id}/sharing")
def sharing(run_id: str, body: Sharing, user=Depends(contributor)):
    run = store.one(
        "SELECT * FROM runs WHERE id=? AND school_id=?", (run_id, user["school_id"])
    )
    if not run:
        raise HTTPException(404, "Run not found in your institution.")
    if run["status"] != "completed":
        raise HTTPException(409, "Complete training and evaluation before sharing.")
    if body.shared and not body.acknowledge_risk:
        raise HTTPException(
            422,
            "Acknowledge that model outputs may reveal training information before enabling shared access.",
        )
    store.update_run(run_id, shared=int(body.shared))
    return {"shared": body.shared}


class Chat(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    model_id: str = "base"


@app.post("/chat")
def chat(body: Chat, user=Depends(current_user)):
    adapter_path = None
    if not body.prompt.strip():
        raise HTTPException(422, "Enter a question.")
    if body.model_id != "base":
        run = store.one(
            "SELECT * FROM runs WHERE id=? AND status='completed' AND (shared=1 OR school_id=?)",
            (body.model_id, user["school_id"]),
        )
        if not run:
            raise HTTPException(
                404, "This model is private, unavailable, or no longer shared."
            )
        adapter_path = store.DATA / "adapters" / run["id"]
    if not ml.available():
        raise HTTPException(
            503, "Install the Python training dependencies to use the local model."
        )
    if not MODEL_LOCK.acquire(blocking=False):
        raise HTTPException(
            409,
            "The local model is busy. Wait for training or the current response to finish.",
        )
    try:
        return {**ml.infer(body.prompt, adapter_path), "model_id": body.model_id}
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    except Exception as error:
        log.error("Inference failed (%s)", type(error).__name__)
        raise HTTPException(
            503,
            "The local model could not generate a response. Check the model download and memory, then retry.",
        ) from None
    finally:
        MODEL_LOCK.release()
