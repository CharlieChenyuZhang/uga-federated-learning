import json
import threading
import time

import pytest
from fastapi.testclient import TestClient
from backend import store, ml
from backend.app import app, MODEL_LOCK
from backend.data import parse_dataset, sample_rows, split_dataset


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path)
    with TestClient(app) as client:
        yield client


def login(client, account="uga"):
    r = client.post("/auth/login", json={"account": account, "password": "local-lab"})
    assert r.status_code == 200
    return r


def insert_completed(school, dataset_id):
    rid = f"run-{school}"
    metrics = {
        "baseline": {"loss": 2, "perplexity": 7.389, "tokens": 12},
        "tuned": {"loss": 1, "perplexity": 2.718, "tokens": 12},
        "samples": [
            {"instruction": "PRIVATE HELD OUT PROMPT", "expected": "PRIVATE REFERENCE"}
        ],
    }
    store.execute(
        "INSERT INTO runs (id,school_id,dataset_id,name,status,steps,phase,metrics,created) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            rid,
            school,
            dataset_id,
            "Private school adapter",
            "completed",
            2,
            "Done",
            json.dumps(metrics),
            time.time(),
        ),
    )
    return rid


def test_login_logout_and_cookie(lab):
    assert lab.get("/datasets").status_code == 401
    assert (
        lab.post(
            "/auth/login", json={"account": "uga", "password": "wrong"}
        ).status_code
        == 401
    )
    r = login(lab)
    assert (
        "HttpOnly" in r.headers["set-cookie"]
        and "SameSite=strict" in r.headers["set-cookie"]
    )
    assert lab.get("/auth/me").json()["school_id"] == "uga"
    lab.post("/auth/logout")
    assert lab.get("/auth/me").status_code == 401


def test_school_isolation_and_user_role(lab):
    login(lab)
    ds = lab.post("/datasets/sample").json()
    rid = insert_completed("uga", ds["id"])
    assert len(lab.get("/runs").json()) == 1
    login(lab, "gatech")
    assert lab.get("/datasets").json() == []
    assert lab.get("/runs").json() == []
    assert lab.get("/models").json() == []
    assert lab.post("/runs", json={"dataset_id": ds["id"]}).status_code == 404
    assert lab.delete("/datasets/" + ds["id"]).status_code == 404
    assert (
        lab.patch(
            f"/runs/{rid}/sharing", json={"shared": True, "acknowledge_risk": True}
        ).status_code
        == 404
    )
    assert (
        lab.post("/chat", json={"model_id": rid, "prompt": "hello"}).status_code == 404
    )
    assert "Private school adapter" not in lab.get("/overview").text
    login(lab, "user")
    assert lab.get("/datasets").status_code == 403
    assert lab.post("/datasets/sample").status_code == 403
    assert lab.post("/runs", json={"dataset_id": ds["id"]}).status_code == 403
    assert (
        lab.patch(
            f"/runs/{rid}/sharing", json={"shared": True, "acknowledge_risk": True}
        ).status_code
        == 403
    )


def test_sharing_is_explicit_revocable_and_redacts_samples(lab):
    login(lab)
    ds = lab.post("/datasets/sample").json()
    rid = insert_completed("uga", ds["id"])
    assert lab.patch(f"/runs/{rid}/sharing", json={"shared": True}).status_code == 422
    assert (
        lab.patch(
            f"/runs/{rid}/sharing", json={"shared": "false", "acknowledge_risk": True}
        ).status_code
        == 422
    )
    assert (
        lab.patch(
            f"/runs/{rid}/sharing", json={"shared": True, "acknowledge_risk": True}
        ).status_code
        == 200
    )
    login(lab, "user")
    r = lab.get("/runs")
    assert len(r.json()) == 1
    assert "PRIVATE" not in r.text and "samples" not in r.json()[0]["metrics"]
    assert "history" not in r.json()[0] and "dataset_id" not in r.json()[0]
    login(lab)
    assert "PRIVATE HELD OUT PROMPT" in lab.get("/runs").text
    lab.patch(f"/runs/{rid}/sharing", json={"shared": False})
    login(lab, "user")
    assert lab.get("/models").json() == []
    assert (
        lab.post("/chat", json={"model_id": rid, "prompt": "hello"}).status_code == 404
    )


def test_upload_validation_and_retention(lab):
    login(lab)
    lines = sample_rows("uga")
    content = "\n".join(json.dumps(r) for r in lines)
    r = lab.post("/datasets", files={"file": ("examples.jsonl", content)})
    assert r.status_code == 201 and r.json()["row_count"] == 24
    assert (
        lab.post("/datasets", files={"file": ("x.jsonl", "not json")}).status_code
        == 422
    )
    assert lab.post("/datasets", files={"file": ("x.exe", content)}).status_code == 422
    assert (
        lab.post(
            "/datasets",
            files={"file": ("nested.jsonl", "[" * 20000 + "0" + "]" * 20000)},
        ).status_code
        == 422
    )
    assert (
        lab.post(
            "/datasets", files={"file": ("x.jsonl", b"x" * (2 * 1024 * 1024 + 17000))}
        ).status_code
        == 413
    )
    lines[0]["response"] = "Contact learner@example.com"
    assert (
        lab.post(
            "/datasets",
            files={"file": ("x.jsonl", "\n".join(json.dumps(r) for r in lines))},
        ).status_code
        == 422
    )
    assert len(lab.get("/datasets").json()) == 1
    rid = r.json()["id"]
    insert_completed("uga", rid)
    assert lab.delete("/datasets/" + rid).status_code == 409


def test_split_deduplicates_instructions_and_is_deterministic():
    data = sample_rows("uga")
    duplicated = data + [
        {"instruction": data[0]["instruction"].upper(), "response": "Another answer"}
    ]
    parsed = parse_dataset(
        "\n".join(json.dumps(r) for r in duplicated).encode(), "x.jsonl"
    )
    assert len(parsed) == 24
    train, validation = split_dataset(parsed)
    assert len(train) == 19 and len(validation) == 5
    assert set(r["instruction"] for r in train).isdisjoint(
        r["instruction"] for r in validation
    )
    assert split_dataset(list(reversed(parsed))) == (train, validation)


def test_local_origin_boundary(lab):
    assert (
        lab.post(
            "/auth/login",
            headers={"origin": "https://evil.example"},
            json={"account": "uga", "password": "local-lab"},
        ).status_code
        == 403
    )
    assert lab.get("/health", headers={"host": "evil.example"}).status_code == 400
    assert (
        lab.post(
            "/auth/logout", headers={"origin": "http://127.0.0.1:4000"}
        ).status_code
        == 403
    )
    assert (
        lab.post("/auth/logout", headers={"sec-fetch-site": "cross-site"}).status_code
        == 403
    )
    assert (
        lab.get("/health", headers={"origin": "http://127.0.0.1:3000"}).status_code
        == 200
    )


def test_real_worker_lifecycle_with_bounded_stub(lab, monkeypatch):
    login(lab)
    ds = lab.post("/datasets/sample").json()
    monkeypatch.setattr(ml, "available", lambda: True)
    started = threading.Event()
    finish = threading.Event()

    def fake_train(run, rows, path, report):
        started.set()
        finish.wait(5)
        report(step=2, history=[{"step": 1, "loss": 2.0}, {"step": 2, "loss": 1.0}])
        return {"eval_examples": 5, "samples": []}

    monkeypatch.setattr(ml, "train", fake_train)
    r = lab.post("/runs", json={"dataset_id": ds["id"], "steps": 2})
    assert r.status_code == 202
    assert started.wait(2)
    try:
        assert (
            lab.post("/runs", json={"dataset_id": ds["id"], "steps": 2}).status_code
            == 409
        )
        assert lab.post("/chat", json={"prompt": "test"}).status_code == 409
        assert (
            lab.patch(
                f"/runs/{r.json()['id']}/sharing",
                json={"shared": True, "acknowledge_risk": True},
            ).status_code
            == 409
        )
    finally:
        finish.set()
    for _ in range(100):
        if not MODEL_LOCK.locked():
            break
        time.sleep(0.02)
    row = lab.get("/runs").json()[0]
    assert row["status"] == "completed" and row["step"] == 2 and not row["shared"]
    assert row["metrics"]["eval_examples"] == 5


def test_restart_marks_interrupted_run_failed(lab):
    login(lab)
    ds = lab.post("/datasets/sample").json()
    store.execute(
        "INSERT INTO runs (id,school_id,dataset_id,name,status,steps,phase,created) VALUES (?,?,?,?,?,?,?,?)",
        ("interrupted", "uga", ds["id"], "Test", "running", 8, "Training", time.time()),
    )
    store.initialize()
    row = store.one("SELECT * FROM runs WHERE id=?", ("interrupted",))
    assert row["status"] == "failed" and row["finished"] is not None
