"""Source adapters. The first adapter reads publisher-approved JSON exports/feeds."""
import json
import re
from datetime import date, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from typing import Protocol
from urllib.parse import quote
from urllib.request import urlopen

from .models import Opportunity


class OpportunitySource(Protocol):
    name: str

    def fetch(self) -> list[Opportunity]: ...


class JsonFileSource:
    def __init__(self, path: Path, name: str | None = None):
        self.path = path
        self.name = name or path.stem

    def fetch(self) -> list[Opportunity]:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError(f"Expected a JSON array in {self.path}")
        return [Opportunity.from_mapping(item, self.name) for item in payload]


class GreenhouseSourceError(RuntimeError):
    """Raised when the Greenhouse API cannot provide a valid response."""


class GreenhouseConfigError(ValueError):
    """Raised when a Greenhouse employer configuration is invalid."""


def load_greenhouse_employers(path: Path) -> list[dict[str, str]]:
    """Load and validate employers from a JSON configuration file."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise GreenhouseConfigError(f"Could not read Greenhouse config {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise GreenhouseConfigError(f"Greenhouse config {path} is not valid JSON") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("employers"), list):
        raise GreenhouseConfigError("Greenhouse config must contain an 'employers' array")
    if not payload["employers"]:
        raise GreenhouseConfigError("Greenhouse config must list at least one employer")

    employers = []
    seen_tokens = set()
    for index, employer in enumerate(payload["employers"]):
        if not isinstance(employer, dict):
            raise GreenhouseConfigError(f"Employer at index {index} must be an object")
        display_name = employer.get("display_name")
        board_token = employer.get("board_token")
        if not isinstance(display_name, str) or not display_name.strip():
            raise GreenhouseConfigError(
                f"Employer at index {index} must have a non-empty display_name"
            )
        if not isinstance(board_token, str) or not board_token.strip():
            raise GreenhouseConfigError(
                f"Employer at index {index} must have a non-empty board_token"
            )
        display_name = display_name.strip()
        board_token = board_token.strip()
        token_key = board_token.casefold()
        if token_key in seen_tokens:
            raise GreenhouseConfigError(f"Duplicate Greenhouse board token: {board_token}")
        seen_tokens.add(token_key)
        employers.append({"display_name": display_name, "board_token": board_token})
    return employers


class GreenhouseSource:
    """Fetch internship postings from one public Greenhouse job board."""

    API_ROOT = "https://boards-api.greenhouse.io/v1/boards"
    INTERNSHIP_TITLE = re.compile(r"\bintern(?:ship)?\b", re.IGNORECASE)

    def __init__(self, board_token: str, timeout: float = 15.0):
        board_token = board_token.strip()
        if not board_token:
            raise ValueError("A Greenhouse board token is required")
        self.board_token = board_token
        self.timeout = timeout
        self.name = "Greenhouse"

    def _get_json(self, url: str) -> dict:
        try:
            with urlopen(url, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise GreenhouseSourceError(
                f"Greenhouse API returned HTTP {exc.code} for board {self.board_token}"
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise GreenhouseSourceError(
                f"Could not fetch Greenhouse board {self.board_token}: {exc}"
            ) from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GreenhouseSourceError("Greenhouse API returned invalid JSON") from exc

        if not isinstance(payload, dict):
            raise GreenhouseSourceError("Greenhouse API response must be a JSON object")
        return payload

    @staticmethod
    def _valid_job_id(job_id: object) -> bool:
        if isinstance(job_id, bool):
            return False
        if isinstance(job_id, int):
            return job_id > 0
        return isinstance(job_id, str) and job_id.isdecimal() and int(job_id) > 0

    @staticmethod
    def _normalize_deadline(value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            return ""
        value = value.strip()
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            try:
                timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return ""
            return timestamp.date().isoformat()

    def _fetch_deadline(self, job_id: object) -> str:
        if not self._valid_job_id(job_id):
            return ""
        token = quote(self.board_token, safe="")
        url = f"{self.API_ROOT}/{token}/jobs/{job_id}"
        try:
            job = self._get_json(url)
        except GreenhouseSourceError:
            # A detail endpoint is only used to enrich an otherwise valid listing.
            return ""
        return self._normalize_deadline(job.get("application_deadline"))

    def fetch(self) -> list[Opportunity]:
        token = quote(self.board_token, safe="")
        board = self._get_json(f"{self.API_ROOT}/{token}")
        employer = board.get("name")
        if not isinstance(employer, str) or not employer.strip():
            raise GreenhouseSourceError("Greenhouse board response is missing its employer name")

        payload = self._get_json(f"{self.API_ROOT}/{token}/jobs?content=true")
        jobs = payload.get("jobs")
        if not isinstance(jobs, list):
            raise GreenhouseSourceError("Greenhouse jobs response must contain a jobs array")

        opportunities = []
        for index, job in enumerate(jobs):
            if not isinstance(job, dict):
                raise GreenhouseSourceError(f"Greenhouse job at index {index} must be an object")
            title = job.get("title")
            application_url = job.get("absolute_url")
            if not isinstance(title, str) or not title.strip():
                raise GreenhouseSourceError(f"Greenhouse job at index {index} is missing its title")
            if not isinstance(application_url, str) or not application_url.strip():
                raise GreenhouseSourceError(
                    f"Greenhouse job at index {index} is missing its application URL"
                )
            if not self.INTERNSHIP_TITLE.search(title):
                continue

            location = job.get("location")
            location_name = location.get("name", "") if isinstance(location, dict) else ""
            content = job.get("content", "")
            if not isinstance(content, str):
                content = ""
            deadline = self._fetch_deadline(job.get("id"))

            opportunities.append(
                Opportunity.from_mapping(
                    {
                        "title": title,
                        "organization": employer,
                        "category": "Internship",
                        "location": location_name,
                        "description": content,
                        "deadline": deadline,
                        "application_url": application_url,
                    },
                    self.name,
                )
            )
        return opportunities
