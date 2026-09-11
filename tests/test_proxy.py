"""Optional HTTP integration against the running website, including browser Origin headers."""

import json
import os

import httpx
import pytest

from backend.data import sample_rows


@pytest.mark.skipif(
    not os.environ.get("CAMPUS_TEST_URL"),
    reason="Start the local website and set CAMPUS_TEST_URL to test the live proxy.",
)
def test_browser_origin_login_upload_and_logout():
    origin = os.environ["CAMPUS_TEST_URL"].rstrip("/")
    with httpx.Client(
        base_url=origin + "/api",
        headers={"Origin": origin, "Sec-Fetch-Site": "same-origin"},
        timeout=30,
    ) as c:
        r = c.post(
            "/auth/login",
            json={
                "account": "uga",
                "password": os.environ.get("CAMPUS_DEMO_PASSWORD", "local-lab"),
            },
        )
        assert r.status_code == 200
        assert c.get("/auth/me").json()["school_id"] == "uga"
        content = "\n".join(json.dumps(row) for row in sample_rows("uga")[:6])
        upload = c.post(
            "/datasets", files={"file": ("proxy-regression.jsonl", content)}
        )
        assert upload.status_code == 201
        try:
            assert (
                c.post(
                    "/auth/logout", headers={"Origin": "http://127.0.0.1:4000"}
                ).status_code
                == 403
            )
            assert c.get("/auth/me").status_code == 200
        finally:
            assert c.delete("/datasets/" + upload.json()["id"]).status_code == 200
        assert c.post("/auth/logout").status_code == 200
        assert c.get("/auth/me").status_code == 401
