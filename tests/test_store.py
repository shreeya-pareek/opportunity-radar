import pytest

from opportunity_radar.models import Opportunity
from opportunity_radar.store import OpportunityStore


@pytest.fixture
def store(tmp_path):
    database_path = tmp_path / "opportunities.sqlite3"
    instance = OpportunityStore(database_path)
    try:
        yield instance
    finally:
        instance.close()


def make_opportunity(
    title,
    url,
    *,
    organization="Example Organization",
    category="Research",
    location="Remote",
    description="An opportunity",
    deadline="2026-12-01",
):
    return Opportunity(
        title=title,
        organization=organization,
        category=category,
        location=location,
        description=description,
        eligibility="Open to applicants",
        deadline=deadline,
        application_url=url,
        source_name="Test source",
    )


def test_inserts_opportunity(store):
    opportunity = make_opportunity("Research Fellowship", "https://example.org/1")

    assert store.upsert(opportunity) == "inserted"
    rows = store.search()
    assert len(rows) == 1
    assert rows[0]["title"] == "Research Fellowship"
    assert rows[0]["application_url"] == "https://example.org/1"


def test_searches_by_keyword(store):
    store.upsert(make_opportunity("Climate Fellowship", "https://example.org/climate"))
    store.upsert(
        make_opportunity(
            "Data Internship",
            "https://example.org/data",
            organization="Climate Data Lab",
        )
    )

    assert [row["title"] for row in store.search(query="Climate")] == [
        "Climate Fellowship",
        "Data Internship",
    ]


def test_filters_by_category(store):
    store.upsert(make_opportunity("Research Fellowship", "https://example.org/research"))
    store.upsert(
        make_opportunity(
            "Design Internship",
            "https://example.org/design",
            category="Design",
        )
    )

    rows = store.search(category="design")
    assert [row["title"] for row in rows] == ["Design Internship"]


def test_filters_by_location(store):
    store.upsert(make_opportunity("Remote Fellowship", "https://example.org/remote"))
    store.upsert(
        make_opportunity(
            "Local Internship",
            "https://example.org/local",
            location="New York",
        )
    )

    rows = store.search(location="york")
    assert [row["title"] for row in rows] == ["Local Internship"]


def test_filters_by_company(store):
    store.upsert(
        make_opportunity(
            "North Lab Internship",
            "https://north.example.test/internship",
            organization="North Lab",
        )
    )
    store.upsert(
        make_opportunity(
            "West Institute Internship",
            "https://west.example.test/internship",
            organization="West Institute",
        )
    )

    rows = store.search(company="north")

    assert [row["title"] for row in rows] == ["North Lab Internship"]


def test_updates_listing_with_same_url_without_adding_row(store):
    url = "https://example.org/same-listing"
    store.upsert(make_opportunity("Original title", url))

    changed = make_opportunity(
        "Updated title",
        url,
        organization="Updated Organization",
        category="Career",
        deadline="2027-01-15",
    )
    assert store.upsert(changed) == "updated"

    rows = store.search()
    assert len(rows) == 1
    assert rows[0]["title"] == "Updated title"
    assert rows[0]["organization"] == "Updated Organization"
    assert rows[0]["category"] == "Career"
    assert rows[0]["deadline"] == "2027-01-15"


def test_upsert_does_not_create_additional_rows_for_duplicate_url(store):
    url = "https://example.org/duplicate"
    store.upsert(make_opportunity("First", url))
    store.upsert(make_opportunity("Second", url))

    assert len(store.search()) == 1


def test_upsert_reports_unchanged_and_preserves_last_seen(store):
    opportunity = make_opportunity("Same listing", "https://example.org/unchanged")
    assert store.upsert(opportunity) == "inserted"
    store.connection.execute(
        "UPDATE opportunities SET last_seen = '2000-01-01 00:00:00' WHERE application_url = ?",
        (opportunity.application_url,),
    )
    store.connection.commit()

    assert store.upsert(opportunity) == "unchanged"
    row = store.search()[0]
    assert row["last_seen"] == "2000-01-01 00:00:00"


def test_upsert_updates_last_seen_when_listing_changes(store):
    original = make_opportunity("Original", "https://example.org/changed")
    store.upsert(original)
    store.connection.execute(
        "UPDATE opportunities SET last_seen = '2000-01-01 00:00:00' WHERE application_url = ?",
        (original.application_url,),
    )
    store.connection.commit()

    result = store.upsert(make_opportunity("Changed", original.application_url))

    assert result == "updated"
    row = store.search()[0]
    assert row["title"] == "Changed"
    assert row["last_seen"] != "2000-01-01 00:00:00"


def test_orders_iso_formatted_deadlines_earliest_first(store):
    store.upsert(make_opportunity("Later deadline", "https://example.org/later", deadline="2027-03-01"))
    store.upsert(make_opportunity("Earlier deadline", "https://example.org/earlier", deadline="2026-11-20"))
    store.upsert(make_opportunity("Middle deadline", "https://example.org/middle", deadline="2026-12-15"))

    assert [row["title"] for row in store.search()] == [
        "Earlier deadline",
        "Middle deadline",
        "Later deadline",
    ]
