"""POST /api/audit-url and the homepage form's web-address field, with the fetcher faked."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from legallens.webpage import FetchedPolicy, FetchError
from webapp.main import app, get_url_fetcher

POLICY = (Path(__file__).resolve().parent.parent / "data" / "samples" / "sample_privacy_policy.txt").read_text(encoding="utf-8")
client = TestClient(app)


@pytest.fixture
def fetched(request):
    """Replace the fetcher; the test reads which addresses it was asked for."""
    calls = []
    result = getattr(request, "param", FetchedPolicy("https://kettle.example/privacy", "html", "Privacy | Kettle", POLICY))

    def fake(url):
        calls.append(url)
        if isinstance(result, Exception):
            raise result
        return result

    app.dependency_overrides[get_url_fetcher] = lambda: fake
    yield calls
    app.dependency_overrides.pop(get_url_fetcher, None)


def test_audit_url_returns_the_same_audit_as_pasted_text(fetched):
    response = client.post("/api/audit-url", data={"url": "kettle.example/privacy"})
    assert response.status_code == 200
    result = response.json()
    assert fetched == ["kettle.example/privacy"]
    assert result["source"] == "kettle.example/privacy"
    pasted = client.post("/api/audit", data={"text": POLICY}).json()
    assert result["score"] == pasted["score"] and result["status_counts"] == pasted["status_counts"]
    assert len(result["missing"]) == 10


@pytest.mark.parametrize("fetched", [FetchedPolicy(
    "https://kettle.example/legal/privacy", "html", "Privacy", POLICY, found_from="https://kettle.example/")], indirect=True)
def test_a_followed_link_is_reported(fetched):
    result = client.post("/api/audit-url", data={"url": "kettle.example", "business_type": "ecommerce"}).json()
    assert result["business_type"] == "ecommerce"
    assert any(w.startswith("LegalLens followed the policy link on kettle.example to kettle.example/legal/privacy")
               for w in result["warnings"])


@pytest.mark.parametrize("fetched", [FetchError("The website didn't let LegalLens read this page.", 422)], indirect=True)
def test_fetch_errors_come_back_as_their_status(fetched):
    response = client.post("/api/audit-url", data={"url": "https://kettle.example/privacy"})
    assert response.status_code == 422
    assert response.json() == {"detail": "The website didn't let LegalLens read this page."}


def test_an_empty_address_is_a_400(fetched):
    response = client.post("/api/audit-url", data={"url": "  "})
    assert response.status_code == 400 and "web address" in response.json()["detail"]
    assert fetched == []


def test_the_real_fetcher_refuses_private_addresses_through_the_api():
    response = client.post("/api/audit-url", data={"url": "http://127.0.0.1:80/admin"})
    assert response.status_code == 400 and "private or local network" in response.json()["detail"]


def test_the_homepage_form_accepts_a_web_address(fetched):
    response = client.post("/audit", data={"url": "kettle.example/privacy"})
    assert response.status_code == 200
    assert "kettle.example/privacy" in response.text


def test_the_homepage_form_wants_one_input_at_a_time(fetched):
    response = client.post("/audit", data={"url": "kettle.example/privacy", "text": POLICY})
    assert response.status_code == 400
    assert "one at a time" in response.text and fetched == []
