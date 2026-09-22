"""Federation lifecycle and tenant-boundary tests without loading model weights."""

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import backend
from backend import federation, ml, store
from backend.app import MODEL_LOCK, app


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path)
    with TestClient(app) as client:
        yield client


def login(client, account="uga"):
    result = client.post("/auth/login", json={"account": account, "password": "local-lab"})
    assert result.status_code == 200


def create(client, **values):
    result = client.post("/federations", json={"name": "Joint STEM model", **values})
    assert result.status_code == 201
    return result.json()["id"]


def enroll(client, federation_id, account):
    login(client, account)
    dataset_id = client.post("/datasets/sample").json()["id"]
    result = client.post(
        f"/federations/{federation_id}/participants",
        json={"dataset_id": dataset_id, "acknowledge_risk": True},
    )
    assert result.status_code == 200
    return dataset_id


def ready(client):
    login(client)
    fid = create(client)
    datasets = {account: enroll(client, fid, account) for account in ("uga", "gatech")}
    login(client)
    return fid, datasets


def metrics():
    return {
        "baseline": {"loss": 2.0, "perplexity": 7.389, "tokens": 20},
        "tuned": {"loss": 1.0, "perplexity": 2.718, "tokens": 20},
        "train_examples": 38, "eval_examples": 10, "seconds": 1.2,
        "seed": 42, "device": "cpu", "model": "test-model", "revision": "test-revision",
        "method": "fedavg_lora", "samples": [{"instruction": "SECRET PROMPT"}],
        "unrecognized": "SECRET METADATA",
    }


def history():
    return [{
        "round": 1, "global": {"loss": 1.0, "perplexity": 2.718, "tokens": 20, "prompt": "SECRET PROMPT"},
        "start_sha256": "a" * 64, "adapter_sha256": "b" * 64,
        "samples": "SECRET EXAMPLES",
        "clients": [{
            "school_id": school, "train_examples": 19, "eval_examples": 5, "weight": 0.5,
            "before": {"loss": 2.0, "perplexity": 7.389, "tokens": 10},
            "local": {"loss": 1.1, "perplexity": 3.004, "tokens": 10},
            "global": {"loss": 1.0, "perplexity": 2.718, "tokens": 10},
            "start_sha256": "a" * 64, "update_sha256": "c" * 64,
            "dataset_id": "PRIVATE DATASET", "prompt": "SECRET PROMPT",
        } for school in ("uga", "gatech")],
    }]


def complete(fid):
    store.update_federation(
        fid, status="completed", round=2, phase="Global model ready",
        metrics=metrics(), history=history(), finished=time.time(),
    )


def wait_worker():
    deadline = time.monotonic() + 5
    while MODEL_LOCK.locked() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not MODEL_LOCK.locked()


def test_discovery_enrollment_requires_own_data_and_explicit_consent(lab):
    assert lab.get("/federations").status_code == 401
    assert lab.post("/federations", json={}).status_code == 401
    login(lab)
    fid = create(lab)
    own = lab.post("/datasets/sample").json()["id"]
    url = f"/federations/{fid}/participants"
    assert lab.post(url, json={"dataset_id": own}).status_code == 422
    assert lab.post(url, json={"dataset_id": own, "acknowledge_risk": "true"}).status_code == 422
    assert lab.post(url, json={"dataset_id": own, "acknowledge_risk": True, "school_id": "gatech"}).status_code == 422
    assert lab.post(url, json={"dataset_id": own, "acknowledge_risk": True}).status_code == 200
    assert lab.delete("/datasets/" + own).status_code == 409
    mine = lab.get("/federations").json()[0]
    assert mine["is_member"] and mine["is_owner"]
    assert mine["participants"][0]["dataset_id"] == own
    login(lab, "gatech")
    discovered = lab.get("/federations").json()[0]
    assert not discovered["is_member"] and not discovered["is_owner"]
    assert discovered["participants"] == [{"school_id": "uga", "joined": mine["participants"][0]["joined"]}]
    assert "metrics" not in discovered and "history" not in discovered and "error" not in discovered
    assert lab.post(url, json={"dataset_id": own, "acknowledge_risk": True}).status_code == 404
    assert lab.post(f"/federations/{fid}/start").status_code == 404
    # Withdrawal affects only the caller, never another institution.
    assert lab.delete(url).status_code == 200
    assert len(store.rows("SELECT * FROM federation_participants")) == 1
    login(lab, "user")
    assert lab.get("/federations").json() == []
    assert lab.post("/federations", json={}).status_code == 403
    assert lab.post(url, json={"dataset_id": own, "acknowledge_risk": True}).status_code == 403
    assert lab.delete(url).status_code == 403
    assert lab.post(f"/federations/{fid}/start").status_code == 403
    login(lab)
    assert lab.delete(url).status_code == 200
    assert lab.delete("/datasets/" + own).status_code == 200


def test_creation_validation_and_draft_enrollment_update(lab):
    login(lab)
    for invalid in ({"rounds": 0}, {"rounds": 6}, {"local_steps": 0}, {"local_steps": 21}, {"rounds": True}, {"rounds": 1.2}, {"name": "   "}, {"owner_school_id": "emory"}):
        assert lab.post("/federations", json=invalid).status_code == 422
    fid = create(lab)
    url = f"/federations/{fid}/participants"
    first = enroll(lab, fid, "uga")
    row = store.one("SELECT * FROM datasets WHERE id=?", (first,))
    second = "another-own-dataset"
    store.execute("INSERT INTO datasets VALUES (?,?,?,?,?,?,?)", (second, "uga", "Second dataset", row["rows"], row["row_count"], time.time(), 0))
    result = lab.post(url, json={"dataset_id": second, "acknowledge_risk": True})
    assert result.status_code == 200
    assert len(result.json()["participants"]) == 1
    assert result.json()["participants"][0]["dataset_id"] == second
    assert lab.delete("/datasets/" + first).status_code == 200
    assert lab.post(f"/federations/{fid}/start").status_code == 422
    lab.delete(url)
    enroll(lab, fid, "gatech")
    enroll(lab, fid, "emory")
    login(lab)
    assert lab.post(f"/federations/{fid}/start").status_code == 422


def test_real_worker_lifecycle_blocks_other_jobs_and_freezes_participants(lab, monkeypatch):
    fid, datasets = ready(lab)
    monkeypatch.setattr(ml, "available", lambda: True)
    started, finish = threading.Event(), threading.Event()
    calls = []

    def fake_train(config, enrolled, path, report):
        calls.append((config, enrolled, path))
        started.set()
        assert finish.wait(5)
        report(round=1, phase="Aggregating round 1", history=history())
        return metrics()

    monkeypatch.setattr(backend, "federated_ml", SimpleNamespace(train=fake_train), raising=False)
    result = lab.post(f"/federations/{fid}/start")
    assert result.status_code == 202 and started.wait(2)
    try:
        assert result.json()["status"] == "queued"
        assert lab.post(f"/federations/{fid}/start").status_code == 409
        assert lab.post("/runs", json={"dataset_id": datasets["uga"], "steps": 2}).status_code == 409
        assert lab.post("/chat", json={"prompt": "hello"}).status_code == 409
        assert lab.post(f"/federations/{fid}/participants", json={"dataset_id": datasets["uga"], "acknowledge_risk": True}).status_code == 409
        assert lab.delete(f"/federations/{fid}/participants").status_code == 409
        assert lab.delete("/datasets/" + datasets["uga"]).status_code == 409
        assert lab.patch(f"/federations/{fid}/sharing", json={"shared": True, "acknowledge_risk": True}).status_code == 409
        assert lab.get(f"/federations/{fid}/evaluation").status_code == 409
        second = create(lab)
        enroll(lab, second, "uga")
        enroll(lab, second, "gatech")
        login(lab)
        assert lab.post(f"/federations/{second}/start").status_code == 409
        assert store.one("SELECT status FROM federations WHERE id=?", (second,))["status"] == "draft"
    finally:
        finish.set()
        wait_worker()
    found = next(row for row in lab.get("/federations").json() if row["id"] == fid)
    assert found["status"] == "completed" and found["round"] == 2
    assert found["metrics"]["method"] == "fedavg_lora"
    assert found["history"][0]["clients"][0]["start_sha256"] == "a" * 64
    assert "SECRET" not in json.dumps(found)
    assert calls[0][2] == store.DATA / "federations" / fid
    assert {item["school_id"] for item in calls[0][1]} == {"uga", "gatech"}
    assert all("rows" not in item for item in calls[0][1])


def test_completed_models_membership_sharing_revocation_and_numeric_exports(lab, monkeypatch):
    fid, datasets = ready(lab)
    complete(fid)
    monkeypatch.setattr(ml, "available", lambda: True)
    paths = []

    def infer(prompt, path):
        paths.append(path)
        return {"response": "A model answer", "seconds": 0.1}

    monkeypatch.setattr(ml, "infer", infer)
    evaluation = f"/federations/{fid}/evaluation"
    sharing = f"/federations/{fid}/sharing"
    for account in ("uga", "gatech"):
        login(lab, account)
        listed = lab.get("/models").json()
        assert len(listed) == 1 and listed[0]["school_id"] == "federation"
        assert listed[0]["steps"] == 4 and listed[0]["step"] == 4
        assert lab.get("/runs").json() == []
        own = lab.get(evaluation)
        assert own.status_code == 200 and "attachment" in own.headers["content-disposition"]
        assert "SECRET" not in own.text and "dataset_id" not in own.text
        assert "no-store" in own.headers["cache-control"]
        assert lab.post("/chat", json={"model_id": fid, "prompt": "hello"}).status_code == 200
    assert paths == [store.DATA / "federations" / fid / "global"] * 2
    assert lab.patch(sharing, json={"shared": True, "acknowledge_risk": True}).status_code == 403
    for account in ("emory", "user"):
        login(lab, account)
        assert lab.get("/models").json() == []
        assert lab.get(evaluation).status_code == 404
        assert lab.post("/chat", json={"model_id": fid, "prompt": "hello"}).status_code == 404
    login(lab)
    assert lab.patch(sharing, json={"shared": True}).status_code == 422
    assert lab.patch(sharing, json={"shared": "false", "acknowledge_risk": True}).status_code == 422
    assert lab.patch(sharing, json={"shared": True, "acknowledge_risk": True}).status_code == 200
    for account in ("emory", "user"):
        login(lab, account)
        visible = lab.get("/federations").json()[0]
        assert visible["metrics"]["tuned"]["loss"] == 1.0
        assert "error" not in visible and "dataset_id" not in json.dumps(visible)
        assert "SECRET" not in json.dumps(visible)
        assert len(lab.get("/models").json()) == 1
        assert lab.get(evaluation).status_code == 200
        assert lab.post("/chat", json={"model_id": fid, "prompt": "hello"}).status_code == 200
    login(lab, "emory")
    assert lab.patch(sharing, json={"shared": False}).status_code == 404
    login(lab, "gatech")
    assert lab.patch(sharing, json={"shared": False}).status_code == 200
    login(lab, "user")
    assert lab.get("/federations").json() == []
    assert lab.get("/models").json() == []
    assert lab.get(evaluation).status_code == 404
    assert lab.post("/chat", json={"model_id": fid, "prompt": "hello"}).status_code == 404


def test_failures_scrub_private_text_release_lock_and_hide_errors_from_outsiders(lab, monkeypatch):
    fid, _ = ready(lab)
    monkeypatch.setattr(ml, "available", lambda: True)

    def failed_train(*args):
        raise ValueError("SECRET training text and /private/path")

    monkeypatch.setattr(backend, "federated_ml", SimpleNamespace(train=failed_train), raising=False)
    assert lab.post(f"/federations/{fid}/start").status_code == 202
    wait_worker()
    own = lab.get("/federations").json()[0]
    assert own["status"] == "failed" and own["error"]
    assert "SECRET" not in json.dumps(own) and "/private/path" not in json.dumps(own)
    login(lab, "emory")
    outsider = lab.get("/federations").json()[0]
    assert "error" not in outsider and "history" not in outsider and "metrics" not in outsider


def test_safe_dataset_validation_error_is_visible_only_to_members(lab, monkeypatch):
    fid, _ = ready(lab)
    monkeypatch.setattr(ml, "available", lambda: True)

    class FederationDataError(ValueError):
        pass

    message = "Participant datasets overlap across training and evaluation splits. Use disjoint examples and create a new federation."

    def failed_train(*args):
        raise FederationDataError(message)

    monkeypatch.setattr(
        backend,
        "federated_ml",
        SimpleNamespace(train=failed_train, FederationDataError=FederationDataError),
        raising=False,
    )
    assert lab.post(f"/federations/{fid}/start").status_code == 202
    wait_worker()
    for account in ("uga", "gatech"):
        login(lab, account)
        own = lab.get("/federations").json()[0]
        assert own["status"] == "failed" and own["error"] == message
    login(lab, "emory")
    outsider = lab.get("/federations").json()[0]
    assert "error" not in outsider and message not in json.dumps(outsider)
    login(lab, "user")
    assert lab.get("/federations").json() == []


def test_duplicate_start_requests_launch_one_worker(lab, monkeypatch):
    fid, _ = ready(lab)
    monkeypatch.setattr(ml, "available", lambda: True)
    finish = threading.Event()
    called = []

    def fake_train(*args):
        called.append(1)
        assert finish.wait(5)
        return metrics()

    monkeypatch.setattr(backend, "federated_ml", SimpleNamespace(train=fake_train), raising=False)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: lab.post(f"/federations/{fid}/start"), range(2)))
        assert sorted(response.status_code for response in responses) == [202, 409]
    finally:
        finish.set()
        wait_worker()
    assert called == [1]


def test_enrollment_and_start_are_atomic(lab, monkeypatch):
    fid, _ = ready(lab)
    owner_cookie = "campus_session=" + lab.cookies.get("campus_session")
    login(lab, "emory")
    third_dataset = lab.post("/datasets/sample").json()["id"]
    third_cookie = "campus_session=" + lab.cookies.get("campus_session")
    monkeypatch.setattr(ml, "available", lambda: True)
    finish = threading.Event()
    worker_participants = []

    def fake_train(config, enrolled, path, report):
        worker_participants.extend(item["school_id"] for item in enrolled)
        assert finish.wait(5)
        return metrics()

    monkeypatch.setattr(backend, "federated_ml", SimpleNamespace(train=fake_train), raising=False)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            started = pool.submit(lab.post, f"/federations/{fid}/start", headers={"cookie": owner_cookie})
            joined = pool.submit(
                lab.post, f"/federations/{fid}/participants",
                headers={"cookie": third_cookie},
                json={"dataset_id": third_dataset, "acknowledge_risk": True},
            )
            assert started.result().status_code == 202
            join_status = joined.result().status_code
            assert join_status in (200, 409)
    finally:
        finish.set()
        wait_worker()
    frozen = {item["school_id"] for item in federation.participants(fid)}
    assert frozen == set(worker_participants)
    assert ("emory" in frozen) == (join_status == 200)


def test_delete_and_enrollment_cannot_leave_a_missing_dataset(lab):
    login(lab)
    fid = create(lab)
    dataset_id = lab.post("/datasets/sample").json()["id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        deleted = pool.submit(lab.delete, "/datasets/" + dataset_id)
        joined = pool.submit(
            lab.post, f"/federations/{fid}/participants",
            json={"dataset_id": dataset_id, "acknowledge_risk": True},
        )
        statuses = (deleted.result().status_code, joined.result().status_code)
    assert statuses in ((200, 404), (409, 200))
    assert bool(federation.participants(fid)) == bool(store.one("SELECT id FROM datasets WHERE id=?", (dataset_id,)))


def test_unavailable_model_and_failed_thread_start_leave_no_lock(lab, monkeypatch):
    fid, _ = ready(lab)
    monkeypatch.setattr(ml, "available", lambda: False)
    assert lab.post(f"/federations/{fid}/start").status_code == 503
    assert store.one("SELECT status FROM federations WHERE id=?", (fid,))["status"] == "draft"
    assert not MODEL_LOCK.locked()
    monkeypatch.setattr(ml, "available", lambda: True)

    class FailedThread:
        def __init__(self, **kwargs):
            pass

        def start(self):
            raise RuntimeError("SECRET thread creation details")

    monkeypatch.setattr(federation, "threading", SimpleNamespace(Thread=FailedThread))
    response = lab.post(f"/federations/{fid}/start")
    assert response.status_code == 503 and "SECRET" not in response.text
    assert not MODEL_LOCK.locked()
    row = store.one("SELECT * FROM federations WHERE id=?", (fid,))
    assert row["status"] == "failed" and row["finished"] is not None


def test_restart_preserves_completed_results_and_marks_interrupted_federation(lab):
    fid, _ = ready(lab)
    store.update_federation(fid, status="running", round=1, history=history())
    store.initialize()
    row = store.one("SELECT * FROM federations WHERE id=?", (fid,))
    assert row["status"] == "failed" and row["finished"] is not None
    assert json.loads(row["history"])[0]["round"] == 1
    complete(fid)
    store.initialize()
    assert store.one("SELECT status FROM federations WHERE id=?", (fid,))["status"] == "completed"
