"""Consent, authorization, and lifecycle for local federated LoRA experiments."""

import json
import logging
import re
import secrets
import threading
import time

from fastapi import Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from . import ml, store

log = logging.getLogger("campus")


class CreateFederation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(default="Collaborative STEM model", min_length=1, max_length=80)
    rounds: int = Field(default=2, ge=1, le=5, strict=True)
    local_steps: int = Field(default=2, ge=1, le=20, strict=True)


class Enroll(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_id: str = Field(min_length=1, max_length=80)
    acknowledge_risk: StrictBool = False


class Sharing(BaseModel):
    model_config = ConfigDict(extra="forbid")
    shared: StrictBool
    acknowledge_risk: StrictBool = False


def participants(federation_id, db=None):
    sql = "SELECT school_id,dataset_id,joined FROM federation_participants WHERE federation_id=? ORDER BY school_id"
    if db is not None:
        return [dict(row) for row in db.execute(sql, (federation_id,)).fetchall()]
    return store.rows(sql, (federation_id,))


def is_member(enrolled, user):
    return user["role"] == "contributor" and any(
        item["school_id"] == user["school_id"] for item in enrolled
    )


def measured_values(value):
    """Numeric fields only. A worker must never publish evaluation examples."""
    return {
        key: value[key]
        for key in ("loss", "perplexity", "tokens")
        if key in value and isinstance(value[key], (int, float))
    }


def public_metrics(raw):
    if not raw:
        return None
    metrics = json.loads(raw) if isinstance(raw, str) else raw
    result = {
        key: metrics[key]
        for key in ("train_examples", "eval_examples", "seconds", "seed")
        if key in metrics and isinstance(metrics[key], (int, float))
    }
    for key in ("baseline", "tuned"):
        if isinstance(metrics.get(key), dict):
            result[key] = measured_values(metrics[key])
    # These are implementation metadata, not evaluation examples or prompts.
    for key in ("device", "model", "revision", "method"):
        if isinstance(metrics.get(key), str):
            result[key] = metrics[key]
    return result


def public_history(raw):
    history = json.loads(raw) if isinstance(raw, str) else raw
    result = []
    for entry in history:
        item = {
            key: entry[key]
            for key in ("round", "train_examples", "eval_examples", "seconds", "loss", "perplexity", "tokens")
            if key in entry and isinstance(entry[key], (int, float))
        }
        for key in ("baseline", "tuned", "evaluation", "global"):
            if isinstance(entry.get(key), dict):
                item[key] = measured_values(entry[key])
        for key in ("start_sha256", "adapter_sha256"):
            if isinstance(entry.get(key), str) and re.fullmatch(r"[0-9a-f]{64}", entry[key]):
                item[key] = entry[key]
        if isinstance(entry.get("clients"), list):
            item["clients"] = []
            for client in entry["clients"]:
                if client.get("school_id") not in {school["id"] for school in store.SCHOOLS}:
                    continue
                safe = {"school_id": client["school_id"]}
                for key in ("train_examples", "eval_examples", "weight"):
                    if isinstance(client.get(key), (int, float)):
                        safe[key] = client[key]
                for key in ("before", "local", "global"):
                    if isinstance(client.get(key), dict):
                        safe[key] = measured_values(client[key])
                for key in ("start_sha256", "update_sha256"):
                    if isinstance(client.get(key), str) and re.fullmatch(r"[0-9a-f]{64}", client[key]):
                        safe[key] = client[key]
                item["clients"].append(safe)
        result.append(item)
    return result


def serialize(row, user, enrolled=None):
    enrolled = participants(row["id"]) if enrolled is None else enrolled
    member = is_member(enrolled, user)
    result = {
        key: row[key]
        for key in (
            "id", "name", "owner_school_id", "status", "rounds", "local_steps",
            "round", "phase", "shared", "created", "finished",
        )
    }
    result.update(
        is_member=member,
        is_owner=user["role"] == "contributor" and row["owner_school_id"] == user["school_id"],
        participants=[
            {
                **{key: item[key] for key in ("school_id", "joined")},
                **({"dataset_id": item["dataset_id"]} if item["school_id"] == user["school_id"] else {}),
            }
            for item in enrolled
        ],
    )
    if member or (row["shared"] and row["status"] == "completed"):
        result.update(metrics=public_metrics(row["metrics"]), history=public_history(row["history"]))
    if member:
        result["error"] = row["error"]
    return result


def accessible_model(federation_id, user):
    row = store.one(
        "SELECT * FROM federations WHERE id=? AND status='completed'",
        (federation_id,),
    )
    if row and (row["shared"] or is_member(participants(federation_id), user)):
        return row
    raise HTTPException(404, "This model is private, unavailable, or no longer shared.")


def models(user):
    found = store.rows(
        "SELECT * FROM federations f WHERE status='completed' AND (shared=1 OR EXISTS (SELECT 1 FROM federation_participants p WHERE p.federation_id=f.id AND p.school_id=?)) ORDER BY created DESC",
        (user["school_id"],),
    )
    return [
        {
            "id": row["id"], "name": row["name"], "school_id": "federation",
            "status": row["status"], "steps": row["rounds"] * row["local_steps"],
            "step": row["round"] * row["local_steps"], "phase": row["phase"],
            "shared": row["shared"], "created": row["created"], "finished": row["finished"],
            "metrics": public_metrics(row["metrics"]), "history": [],
        }
        for row in found
    ]


def worker(federation, enrolled, model_lock):
    federated_ml = None
    try:
        from . import federated_ml

        store.update_federation(federation["id"], status="running")
        metrics = federated_ml.train(
            federation,
            enrolled,
            store.DATA / "federations" / federation["id"],
            lambda **updates: store.update_federation(federation["id"], **updates),
        )
        store.update_federation(
            federation["id"], status="completed", round=federation["rounds"],
            phase="Global model ready", metrics=public_metrics(metrics), finished=time.time(),
        )
    except Exception as error:
        # Exception strings may contain private data, paths, or model examples.
        log.error("Federation %s failed (%s)", federation["id"], type(error).__name__)
        message = (
            str(error)
            if isinstance(error, getattr(federated_ml, "FederationDataError", ()))
            else "The local federation worker failed. Check model availability and memory, then create a new federation to retry."
        )
        store.update_federation(
            federation["id"], status="failed", phase="Federation failed",
            error=message,
            finished=time.time(),
        )
    finally:
        model_lock.release()


def register_routes(app, current_user, contributor, model_lock):
    @app.get("/federations")
    def list_federations(user=Depends(current_user)):
        query = "SELECT * FROM federations"
        if user["role"] != "contributor":
            query += " WHERE shared=1 AND status='completed'"
        return [serialize(row, user) for row in store.rows(query + " ORDER BY created DESC")]

    @app.post("/federations", status_code=201)
    def create(body: CreateFederation, user=Depends(contributor)):
        if not body.name.strip():
            raise HTTPException(422, "Enter a federation name.")
        federation_id = "f-" + secrets.token_hex(12)
        store.execute(
            "INSERT INTO federations (id,owner_school_id,name,rounds,local_steps,created) VALUES (?,?,?,?,?,?)",
            (federation_id, user["school_id"], body.name.strip(), body.rounds, body.local_steps, time.time()),
        )
        return serialize(store.one("SELECT * FROM federations WHERE id=?", (federation_id,)), user)

    @app.post("/federations/{federation_id}/participants")
    def enroll(federation_id: str, body: Enroll, user=Depends(contributor)):
        if not body.acknowledge_risk:
            raise HTTPException(
                422,
                "Consent to sharing the global model and numeric evaluations with participants, and to optional guest publication by the owner. Model updates and outputs may reveal training information.",
            )
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM federations WHERE id=?", (federation_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Federation not found.")
            if row["status"] != "draft":
                raise HTTPException(409, "Participants and datasets are frozen after training starts.")
            dataset = db.execute(
                "SELECT id FROM datasets WHERE id=? AND school_id=?",
                (body.dataset_id, user["school_id"]),
            ).fetchone()
            if not dataset:
                raise HTTPException(404, "Dataset not found in your institution.")
            db.execute(
                "INSERT INTO federation_participants (federation_id,school_id,dataset_id,joined,acknowledged) VALUES (?,?,?,?,1) ON CONFLICT(federation_id,school_id) DO UPDATE SET dataset_id=excluded.dataset_id,joined=excluded.joined,acknowledged=1",
                (federation_id, user["school_id"], body.dataset_id, time.time()),
            )
            result = serialize(dict(row), user, participants(federation_id, db))
        return result

    @app.delete("/federations/{federation_id}/participants")
    def withdraw(federation_id: str, user=Depends(contributor)):
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM federations WHERE id=?", (federation_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Federation not found.")
            if row["status"] != "draft":
                raise HTTPException(409, "Participants and datasets are frozen after training starts.")
            db.execute(
                "DELETE FROM federation_participants WHERE federation_id=? AND school_id=?",
                (federation_id, user["school_id"]),
            )
            result = serialize(dict(row), user, participants(federation_id, db))
        return result

    @app.post("/federations/{federation_id}/start", status_code=202)
    def start(federation_id: str, user=Depends(contributor)):
        acquired = False
        try:
            with store.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute(
                    "SELECT * FROM federations WHERE id=? AND owner_school_id=?",
                    (federation_id, user["school_id"]),
                ).fetchone()
                if not row:
                    raise HTTPException(404, "Federation not found in your institution.")
                if row["status"] != "draft":
                    raise HTTPException(409, "This federation has already started.")
                enrolled = participants(federation_id, db)
                if len(enrolled) < 2 or not is_member(enrolled, user):
                    raise HTTPException(422, "Enroll the owner and at least one other institution before starting.")
                for item in enrolled:
                    if not db.execute(
                        "SELECT 1 FROM datasets WHERE id=? AND school_id=?",
                        (item["dataset_id"], item["school_id"]),
                    ).fetchone():
                        raise HTTPException(409, "A participant dataset is unavailable. Update enrollment before starting.")
                if not ml.available():
                    raise HTTPException(503, "Install the local Python training dependencies before starting.")
                acquired = model_lock.acquire(blocking=False)
                if not acquired:
                    raise HTTPException(409, "The local model is busy. Wait for training or the current response to finish.")
                db.execute(
                    "UPDATE federations SET status='queued',phase='Preparing federated worker' WHERE id=?",
                    (federation_id,),
                )
                row = dict(db.execute("SELECT * FROM federations WHERE id=?", (federation_id,)).fetchone())
            try:
                threading.Thread(target=worker, args=(row, enrolled, model_lock), daemon=True).start()
            except Exception:
                store.update_federation(
                    federation_id, status="failed", phase="Worker unavailable",
                    error="The local worker could not start. Create a new federation to retry.", finished=time.time(),
                )
                raise HTTPException(503, "The local worker could not start.") from None
            # The worker owns the lock after a successful thread start.
            acquired = False
            return serialize(row, user, enrolled)
        finally:
            if acquired:
                model_lock.release()

    @app.patch("/federations/{federation_id}/sharing")
    def share(federation_id: str, body: Sharing, user=Depends(contributor)):
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM federations WHERE id=?", (federation_id,)).fetchone()
            enrolled = participants(federation_id, db)
            if not row or not is_member(enrolled, user):
                raise HTTPException(404, "Federation not available to this institution.")
            if row["status"] != "completed":
                raise HTTPException(409, "Complete training and evaluation before sharing.")
            if body.shared and row["owner_school_id"] != user["school_id"]:
                raise HTTPException(403, "Only the federation owner may enable guest access.")
            if body.shared and not body.acknowledge_risk:
                raise HTTPException(422, "Acknowledge that model outputs may reveal training information before enabling guest access.")
            db.execute("UPDATE federations SET shared=? WHERE id=?", (int(body.shared), federation_id))
        return {"shared": body.shared}

    @app.get("/federations/{federation_id}/evaluation")
    def evaluation(federation_id: str, user=Depends(current_user)):
        row = store.one("SELECT * FROM federations WHERE id=?", (federation_id,))
        enrolled = participants(federation_id)
        if not row or not (is_member(enrolled, user) or (row["shared"] and row["status"] == "completed")):
            raise HTTPException(404, "Evaluation not available to this account.")
        if row["status"] != "completed" or not row["metrics"]:
            raise HTTPException(409, "This federation does not have a completed evaluation yet.")
        # Exports contain shared numeric results, with no dataset IDs or private examples.
        result = serialize(row, user, enrolled)
        for item in result["participants"]:
            item.pop("dataset_id", None)
        result.pop("error", None)
        return JSONResponse(
            result,
            headers={"Content-Disposition": f'attachment; filename="campus-federation-{federation_id}.json"'},
        )
