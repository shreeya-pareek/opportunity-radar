import pytest

from opportunity_radar.models import Opportunity


def test_creates_valid_opportunity():
    opportunity = Opportunity.from_mapping(
        {
            "title": "Research Fellowship",
            "application_url": "https://example.org/apply",
            "organization": "Example Institute",
            "category": "Research",
            "location": "Remote",
            "description": "A research opportunity.",
            "eligibility": "Graduate students",
            "deadline": "2026-12-01",
        },
        "Example Feed",
    )

    assert opportunity.title == "Research Fellowship"
    assert opportunity.application_url == "https://example.org/apply"
    assert opportunity.organization == "Example Institute"
    assert opportunity.source_name == "Example Feed"


@pytest.mark.parametrize("field", ["title", "application_url"])
def test_requires_title_and_application_url(field):
    item = {"title": "Valid title", "application_url": "https://example.org/apply"}
    item[field] = "  "

    with pytest.raises(ValueError, match="Missing required field"):
        Opportunity.from_mapping(item, "Example Feed")


def test_optional_fields_use_defaults():
    opportunity = Opportunity.from_mapping(
        {"title": "Fellowship", "application_url": "https://example.org/apply"},
        "  Example Feed  ",
    )

    assert opportunity.organization == ""
    assert opportunity.category == "Other"
    assert opportunity.location == "Unspecified"
    assert opportunity.description == ""
    assert opportunity.eligibility == "Not provided by source"
    assert opportunity.deadline == ""
    assert opportunity.source_name == "Example Feed"
