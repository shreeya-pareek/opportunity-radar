import json
from contextlib import closing
from io import BytesIO

import pytest

from opportunity_radar.sources import (
    GreenhouseSource,
    GreenhouseSourceError,
    JsonFileSource,
)


def test_ingests_json_array_of_opportunities(tmp_path):
    source_file = tmp_path / "feed.json"
    source_file.write_text(
        json.dumps(
            [
                {"title": "Fellowship", "application_url": "https://example.org/apply"},
                {"title": "Internship", "application_url": "https://example.org/intern"},
            ]
        ),
        encoding="utf-8",
    )

    opportunities = JsonFileSource(source_file).fetch()

    assert [item.title for item in opportunities] == ["Fellowship", "Internship"]
    assert all(item.source_name == "feed" for item in opportunities)


def test_rejects_json_root_that_is_not_an_array(tmp_path):
    source_file = tmp_path / "feed.json"
    source_file.write_text(json.dumps({"title": "Fellowship"}), encoding="utf-8")

    with pytest.raises(ValueError, match="Expected a JSON array"):
        JsonFileSource(source_file).fetch()


def test_rejects_listing_missing_required_field(tmp_path):
    source_file = tmp_path / "feed.json"
    source_file.write_text(
        json.dumps([{"title": "Fellowship"}]),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="application_url"):
        JsonFileSource(source_file).fetch()


def greenhouse_response(payload):
    return closing(BytesIO(json.dumps(payload).encode("utf-8")))


def test_greenhouse_fetches_internships_and_maps_api_fields(monkeypatch):
    responses = iter(
        [
            {"name": "Verified Example Employer", "content": "Careers"},
            {
                "jobs": [
                    {
                        "id": 123,
                        "title": "Software Engineering Intern",
                        "location": {"name": "Remote, US"},
                        "absolute_url": "https://boards.greenhouse.io/example/jobs/123",
                        "content": "<p>Build software with us.</p>",
                    }
                ]
            },
            {"application_deadline": "2027-02-03T20:00:00Z"},
        ]
    )
    requested_urls = []

    def fake_urlopen(url, timeout):
        requested_urls.append((url, timeout))
        return greenhouse_response(next(responses))

    monkeypatch.setattr("opportunity_radar.sources.urlopen", fake_urlopen)

    opportunities = GreenhouseSource("verified-board", timeout=3).fetch()

    assert len(opportunities) == 1
    opportunity = opportunities[0]
    assert opportunity.title == "Software Engineering Intern"
    assert opportunity.organization == "Verified Example Employer"
    assert opportunity.category == "Internship"
    assert opportunity.location == "Remote, US"
    assert opportunity.description == "<p>Build software with us.</p>"
    assert opportunity.application_url == "https://boards.greenhouse.io/example/jobs/123"
    assert opportunity.deadline == "2027-02-03"
    assert opportunity.source_name == "Greenhouse"
    assert requested_urls == [
        ("https://boards-api.greenhouse.io/v1/boards/verified-board", 3),
        ("https://boards-api.greenhouse.io/v1/boards/verified-board/jobs?content=true", 3),
        ("https://boards-api.greenhouse.io/v1/boards/verified-board/jobs/123", 3),
    ]


def test_greenhouse_filters_out_non_internship_jobs(monkeypatch):
    payloads = iter(
        [
            {"name": "Employer"},
            {
                "jobs": [
                    {"title": "Internal Auditor", "absolute_url": "https://example.org/a"},
                    {"title": "Software Intern", "absolute_url": "https://example.org/b"},
                    {"title": "Internship Coordinator", "absolute_url": "https://example.org/c"},
                    {"title": "Software Engineer", "absolute_url": "https://example.org/d"},
                ]
            },
        ]
    )
    monkeypatch.setattr(
        "opportunity_radar.sources.urlopen",
        lambda url, timeout: greenhouse_response(next(payloads)),
    )

    opportunities = GreenhouseSource("verified-board").fetch()

    assert [item.title for item in opportunities] == ["Software Intern", "Internship Coordinator"]


def test_greenhouse_missing_optional_fields_use_model_defaults(monkeypatch):
    payloads = iter(
        [
            {"name": "Employer"},
            {"jobs": [{"title": "Policy Intern", "absolute_url": "https://example.org/intern"}]},
        ]
    )
    monkeypatch.setattr(
        "opportunity_radar.sources.urlopen",
        lambda url, timeout: greenhouse_response(next(payloads)),
    )

    opportunity = GreenhouseSource("verified-board").fetch()[0]

    assert opportunity.location == "Unspecified"
    assert opportunity.description == ""
    assert opportunity.eligibility == "Not provided by source"
    assert opportunity.deadline == ""


@pytest.mark.parametrize(
    ("deadline_value", "expected"),
    [
        ("2027-04-05", "2027-04-05"),
        ("2027-04-05T23:30:00-07:00", "2027-04-05"),
        ("", ""),
        (None, ""),
        ("not a date", ""),
    ],
)
def test_greenhouse_normalizes_detail_deadline(monkeypatch, deadline_value, expected):
    payloads = iter(
        [
            {"name": "Employer"},
            {"jobs": [{"id": "456", "title": "Research Intern", "absolute_url": "https://example.org/intern"}]},
            {"application_deadline": deadline_value},
        ]
    )
    monkeypatch.setattr(
        "opportunity_radar.sources.urlopen",
        lambda url, timeout: greenhouse_response(next(payloads)),
    )

    opportunity = GreenhouseSource("verified-board").fetch()[0]

    assert opportunity.deadline == expected


def test_greenhouse_skips_detail_request_for_missing_or_invalid_job_id(monkeypatch):
    payloads = iter(
        [
            {"name": "Employer"},
            {
                "jobs": [
                    {"title": "Research Intern", "absolute_url": "https://example.org/no-id"},
                    {"id": "not-an-id", "title": "Policy Intern", "absolute_url": "https://example.org/bad-id"},
                ]
            },
        ]
    )
    requested_urls = []

    def fake_urlopen(url, timeout):
        requested_urls.append(url)
        return greenhouse_response(next(payloads))

    monkeypatch.setattr("opportunity_radar.sources.urlopen", fake_urlopen)

    opportunities = GreenhouseSource("verified-board").fetch()

    assert len(opportunities) == 2
    assert all(item.deadline == "" for item in opportunities)
    assert len(requested_urls) == 2


def test_greenhouse_missing_detail_deadline_is_empty(monkeypatch):
    payloads = iter(
        [
            {"name": "Employer"},
            {"jobs": [{"id": 321, "title": "Data Intern", "absolute_url": "https://example.org/intern"}]},
            {},
        ]
    )
    monkeypatch.setattr(
        "opportunity_radar.sources.urlopen",
        lambda url, timeout: greenhouse_response(next(payloads)),
    )

    opportunity = GreenhouseSource("verified-board").fetch()[0]

    assert opportunity.deadline == ""


def test_greenhouse_detail_request_failure_does_not_drop_listing(monkeypatch):
    from urllib.error import URLError

    payloads = iter(
        [
            {"name": "Employer"},
            {"jobs": [{"id": 789, "title": "Summer Intern", "absolute_url": "https://example.org/intern"}]},
        ]
    )

    def fake_urlopen(url, timeout):
        if url.endswith("/jobs/789"):
            raise URLError("detail endpoint unavailable")
        return greenhouse_response(next(payloads))

    monkeypatch.setattr("opportunity_radar.sources.urlopen", fake_urlopen)

    opportunities = GreenhouseSource("verified-board").fetch()

    assert len(opportunities) == 1
    assert opportunities[0].deadline == ""


@pytest.mark.parametrize(
    ("payloads", "message"),
    [
        ([{"name": "Employer"}, {"jobs": {}}], "jobs array"),
        ([{"name": "Employer"}, {"jobs": ["not a job"]}], "must be an object"),
        ([{"content": "no name"}], "employer name"),
        ([{"name": "Employer"}, {"unexpected": []}], "jobs array"),
        ([{"name": "Employer"}, {"jobs": [{"absolute_url": "https://example.org"}]}], "missing its title"),
    ],
)
def test_greenhouse_rejects_malformed_responses(monkeypatch, payloads, message):
    responses = iter(payloads)
    monkeypatch.setattr(
        "opportunity_radar.sources.urlopen",
        lambda url, timeout: greenhouse_response(next(responses)),
    )

    with pytest.raises(GreenhouseSourceError, match=message):
        GreenhouseSource("verified-board").fetch()


def test_greenhouse_raises_on_request_failure(monkeypatch):
    from urllib.error import URLError

    def fail_request(url, timeout):
        raise URLError("network unavailable")

    monkeypatch.setattr("opportunity_radar.sources.urlopen", fail_request)

    with pytest.raises(GreenhouseSourceError, match="Could not fetch Greenhouse board"):
        GreenhouseSource("verified-board").fetch()


def test_greenhouse_raises_on_http_error(monkeypatch):
    from urllib.error import HTTPError

    def fail_request(url, timeout):
        raise HTTPError(url, 503, "Service unavailable", {}, None)

    monkeypatch.setattr("opportunity_radar.sources.urlopen", fail_request)

    with pytest.raises(GreenhouseSourceError, match="HTTP 503"):
        GreenhouseSource("verified-board").fetch()
