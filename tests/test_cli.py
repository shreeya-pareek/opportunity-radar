import json
import sys

import pytest

from opportunity_radar import cli
from opportunity_radar.models import Opportunity
from opportunity_radar.sources import GreenhouseSourceError


class FakeStore:
    instances = []

    def __init__(self, path):
        self.path = path
        self.upserted = []
        self.closed = False
        self.instances.append(self)

    def upsert(self, opportunity):
        self.upserted.append(opportunity)
        return "inserted"

    def search(self, query="", category="", location=""):
        return []

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def fake_store(monkeypatch):
    FakeStore.instances.clear()
    monkeypatch.setattr(cli, "OpportunityStore", FakeStore)


def write_config(tmp_path, employers):
    config_path = tmp_path / "greenhouse.json"
    config_path.write_text(json.dumps({"employers": employers}), encoding="utf-8")
    return config_path


def test_loads_and_normalizes_greenhouse_employer_config(tmp_path):
    config_path = write_config(
        tmp_path,
        [{"display_name": "  Example Employer ", "board_token": "  example-token  "}],
    )

    assert cli.load_greenhouse_employers(config_path) == [
        {"display_name": "Example Employer", "board_token": "example-token"}
    ]


def test_rejects_duplicate_greenhouse_board_tokens(tmp_path):
    config_path = write_config(
        tmp_path,
        [
            {"display_name": "Employer One", "board_token": "same-token"},
            {"display_name": "Employer Two", "board_token": " SAME-TOKEN "},
        ],
    )

    with pytest.raises(cli.GreenhouseConfigError, match="Duplicate Greenhouse board token"):
        cli.load_greenhouse_employers(config_path)


@pytest.mark.parametrize(
    ("employers", "message"),
    [
        ([], "at least one employer"),
        ([{"display_name": "", "board_token": "token"}], "display_name"),
        ([{"display_name": "Employer", "board_token": " "}], "board_token"),
        (["invalid entry"], "must be an object"),
    ],
)
def test_rejects_invalid_greenhouse_employer_config(tmp_path, employers, message):
    config_path = write_config(tmp_path, employers)

    with pytest.raises(cli.GreenhouseConfigError, match=message):
        cli.load_greenhouse_employers(config_path)


def test_rejects_malformed_greenhouse_config_json(tmp_path):
    config_path = tmp_path / "greenhouse.json"
    config_path.write_text("{broken", encoding="utf-8")

    with pytest.raises(cli.GreenhouseConfigError, match="not valid JSON"):
        cli.load_greenhouse_employers(config_path)


def test_rejects_missing_greenhouse_config(tmp_path):
    with pytest.raises(cli.GreenhouseConfigError, match="Could not read Greenhouse config"):
        cli.load_greenhouse_employers(tmp_path / "missing.json")


def test_collect_greenhouse_all_reports_empty_success_separately_from_failure(
    monkeypatch, tmp_path, capsys
):
    config_path = write_config(
        tmp_path,
        [
            {"display_name": "Empty Board", "board_token": "empty"},
            {"display_name": "Offline Board", "board_token": "offline"},
            {"display_name": "Active Board", "board_token": "active"},
        ],
    )
    listing = Opportunity.from_mapping(
        {"title": "Research Intern", "application_url": "https://example.org/intern"},
        "Greenhouse",
    )

    class FakeGreenhouseSource:
        def __init__(self, board_token):
            self.board_token = board_token

        def fetch(self):
            if self.board_token == "offline":
                raise GreenhouseSourceError("service unavailable")
            return {"empty": [], "active": [listing]}[self.board_token]

    monkeypatch.setattr(cli, "GreenhouseSource", FakeGreenhouseSource)
    monkeypatch.setattr(
        sys,
        "argv",
        ["radar", "collect-greenhouse-all", "--config", str(config_path)],
    )

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    output = capsys.readouterr().out
    assert exc_info.value.code == 1
    assert "Empty Board: succeeded, 0 internship listing(s)" in output
    assert "Failed Offline Board: service unavailable" in output
    assert "Active Board: succeeded, 1 internship listing(s)" in output
    assert "2 employer(s) succeeded, 1 failed" in output
    assert "1 inserted, 0 updated, 0 unchanged" in output
    assert FakeStore.instances[0].upserted == [listing]
    assert FakeStore.instances[0].closed is True


def test_collect_greenhouse_all_success_returns_normally(monkeypatch, tmp_path, capsys):
    config_path = write_config(tmp_path, [{"display_name": "Empty Board", "board_token": "empty"}])

    class EmptyGreenhouseSource:
        def __init__(self, board_token):
            assert board_token == "empty"

        def fetch(self):
            return []

    monkeypatch.setattr(cli, "GreenhouseSource", EmptyGreenhouseSource)
    monkeypatch.setattr(
        sys,
        "argv",
        ["radar", "collect-greenhouse-all", "--config", str(config_path)],
    )

    cli.main()

    output = capsys.readouterr().out
    assert "1 employer(s) succeeded, 0 failed" in output
    assert "Empty Board: succeeded, 0 internship listing(s)" in output


def test_existing_json_collection_command_is_preserved(monkeypatch, tmp_path, capsys):
    feed_path = tmp_path / "feed.json"
    feed_path.write_text(
        json.dumps([{"title": "Fellowship", "application_url": "https://example.org/apply"}]),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["radar", "collect", str(feed_path), "--source", "Test feed"],
    )

    cli.main()

    output = capsys.readouterr().out
    assert "Collected 1 listing(s) from Test feed" in output
    assert "1 inserted, 0 updated, 0 unchanged" in output
    assert FakeStore.instances[0].closed is True


def test_existing_single_greenhouse_command_is_preserved(monkeypatch, tmp_path, capsys):
    class EmptyGreenhouseSource:
        def __init__(self, board_token):
            assert board_token == "one-token"

        def fetch(self):
            return []

    monkeypatch.setattr(cli, "GreenhouseSource", EmptyGreenhouseSource)
    monkeypatch.setattr(sys, "argv", ["radar", "collect-greenhouse", "one-token"])

    cli.main()

    assert "Collected 0 listing(s) from Greenhouse board one-token" in capsys.readouterr().out


def test_existing_search_command_is_preserved(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["radar", "search", "intern", "--location", "remote"])

    cli.main()

    assert "No opportunities found." in capsys.readouterr().out
    assert FakeStore.instances[0].closed is True
