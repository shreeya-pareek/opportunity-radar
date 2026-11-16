from fastapi.testclient import TestClient
import pytest

from opportunity_radar.api import create_app
from opportunity_radar.models import Opportunity
from opportunity_radar.store import OpportunityStore


@pytest.fixture
def api_client(tmp_path):
    database_path = tmp_path / "api.sqlite3"
    seed_store = OpportunityStore(database_path)
    seed_store.upsert(
        Opportunity.from_mapping(
            {
                "title": "Climate Research Internship",
                "organization": "North Lab",
                "category": "Internship",
                "location": "Remote",
                "description": "Study climate systems",
                "eligibility": "Undergraduate students",
                "deadline": "2027-04-01",
                "application_url": "https://example.org/climate",
            },
            "North Lab careers",
        )
    )
    seed_store.upsert(
        Opportunity.from_mapping(
            {
                "title": "Robotics Fellowship",
                "organization": "West Institute",
                "category": "Fellowship",
                "location": "Boston",
                "description": "Build robotics tools",
                "eligibility": "Graduate students",
                "deadline": "2027-05-15",
                "application_url": "https://example.org/robotics",
            },
            "West Institute feed",
        )
    )
    seed_store.close()

    app = create_app(database_path)
    with TestClient(app) as client:
        yield client, app


def test_health_reports_api_and_database_status(api_client):
    client, _ = api_client

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_reports_unavailable_database(api_client, monkeypatch):
    client, app = api_client
    monkeypatch.setattr(app.state.opportunity_store, "check_health", lambda: False)

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}


def test_lists_all_opportunities_with_ids_and_model_fields(api_client):
    client, _ = api_client

    response = client.get("/api/opportunities")

    assert response.status_code == 200
    opportunities = response.json()
    assert [item["title"] for item in opportunities] == [
        "Climate Research Internship",
        "Robotics Fellowship",
    ]
    assert opportunities[0] == {
        "id": opportunities[0]["id"],
        "title": "Climate Research Internship",
        "organization": "North Lab",
        "category": "Internship",
        "location": "Remote",
        "description": "Study climate systems",
        "eligibility": "Undergraduate students",
        "deadline": "2027-04-01",
        "application_url": "https://example.org/climate",
        "source_name": "North Lab careers",
    }
    assert isinstance(opportunities[0]["id"], int)


def test_searches_opportunities_by_keyword(api_client):
    client, _ = api_client

    response = client.get("/api/opportunities", params={"q": "climate"})

    assert response.status_code == 200
    assert [item["title"] for item in response.json()] == ["Climate Research Internship"]


def test_filters_opportunities_by_category_and_location(api_client):
    client, _ = api_client

    response = client.get(
        "/api/opportunities",
        params={"category": "Intern", "location": "remote"},
    )

    assert response.status_code == 200
    assert [item["title"] for item in response.json()] == ["Climate Research Internship"]


def test_filters_opportunities_by_company(api_client):
    client, _ = api_client

    response = client.get("/api/opportunities", params={"company": "north"})

    assert response.status_code == 200
    assert [item["organization"] for item in response.json()] == ["North Lab"]


def test_returns_empty_list_when_filters_match_no_opportunities(api_client):
    client, _ = api_client

    response = client.get("/api/opportunities", params={"category": "Scholarship"})

    assert response.status_code == 200
    assert response.json() == []


def test_retrieves_opportunity_by_sqlite_id(api_client):
    client, _ = api_client
    listed = client.get("/api/opportunities").json()[0]

    response = client.get(f"/api/opportunities/{listed['id']}")

    assert response.status_code == 200
    assert response.json() == listed


def test_returns_404_for_unknown_opportunity_id(api_client):
    client, _ = api_client

    response = client.get("/api/opportunities/9999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Opportunity not found"}


def test_returns_422_for_non_integer_opportunity_id(api_client):
    client, _ = api_client

    response = client.get("/api/opportunities/not-an-id")

    assert response.status_code == 422


def test_serves_homepage_and_static_assets(api_client):
    client, _ = api_client

    homepage = client.get("/")
    stylesheet = client.get("/static/css/styles.css")
    script = client.get("/static/js/app.js")

    assert homepage.status_code == 200
    assert "Navigate opportunities." in homepage.text
    assert '<h1 id="hero-title">Opportunity <em>Radar</em></h1>' in homepage.text
    assert '<p class="hero-tagline">Navigate opportunities. Discover possibilities.</p>' in homepage.text
    assert stylesheet.status_code == 200
    assert "#111827" in stylesheet.text
    assert script.status_code == 200
    assert "isDisplayableOpportunity" in script.text
    assert 'host === "example.org"' in script.text


def test_closes_database_connection_when_app_lifespan_ends(tmp_path, monkeypatch):
    closed = []
    close = OpportunityStore.close

    def record_close(store):
        close(store)
        closed.append(True)

    monkeypatch.setattr(OpportunityStore, "close", record_close)
    app = create_app(tmp_path / "lifecycle.sqlite3")
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200

    assert closed == [True]
