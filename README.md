# Opportunity Radar

Opportunity Radar is a small Python command-line application for collecting and searching career, research, scholarship, and internship opportunities. It imports publisher-provided JSON and published internship listings from Greenhouse job boards configured by the user. Listings are stored in SQLite with their employer attribution and original application URL.

Greenhouse collection only checks the board tokens supplied to the command or configuration file. It does not discover or scrape every employer.

## Features

- Import a JSON array of opportunity listings.
- Collect internship listings from one Greenhouse board or from multiple configured boards.
- Search stored listings by keyword, category, and location.
- Store opportunities in SQLite and identify duplicates by application URL.
- Report whether collected listings were inserted, updated, or unchanged.
- Use the Python standard library for application functionality; no runtime API client dependency is required.

## Project structure

```text
opportunity-radar/
|-- data/
|   |-- greenhouse_employers.json   # Configured Greenhouse boards
|   `-- sample_opportunities.json   # Example JSON input
|-- src/
|   `-- opportunity_radar/
|       |-- cli.py                  # Command-line interface
|       |-- models.py               # Opportunity data model
|       |-- sources.py              # JSON and Greenhouse source adapters
|       `-- store.py                # SQLite storage and search
|-- tests/                          # pytest suite
`-- pyproject.toml                  # Package metadata and CLI entry point
```

## Windows setup

Use PowerShell from the project directory. Python 3.11 or newer is required.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

After activation, the virtual environment is shown in the PowerShell prompt. The editable install makes the `radar` command available while using the project source tree.

Install the optional FastAPI backend dependencies when you want to run the API:

```powershell
python -m pip install -e ".[api]"
```

If PowerShell blocks activation, allow scripts for the current session only, then activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## Collect from a JSON file

The JSON input must be an array. Each listing needs `title` and `application_url`. Optional fields are `organization`, `category`, `location`, `description`, `eligibility`, and `deadline`.

```powershell
radar collect data/sample_opportunities.json --source "Example feed"
```

The `--source` label is optional; when omitted, the JSON file name is used.

## Collect from one Greenhouse board

Pass the board token published in the employer's Greenhouse board URL:

```powershell
radar collect-greenhouse BOARD_TOKEN
```

This fetches published jobs from that one board and keeps listings whose titles identify them as internships. The command does not search for other employers. Greenhouse requests use public job-board endpoints and do not require an API key.

For internship listings with valid Greenhouse job IDs, the adapter also fetches job details to retrieve an application deadline. Available dates are normalized to `YYYY-MM-DD`. Missing or unavailable deadlines are stored as blank; a failure to retrieve optional deadline details does not discard the listing.

## Collect from configured Greenhouse boards

The multi-employer command reads every employer entry in a JSON configuration file:

```powershell
radar collect-greenhouse-all --config data/greenhouse_employers.json
```

The configuration must contain at least one employer. Each entry requires a non-empty `display_name` and `board_token`. Tokens must be unique (case-insensitively). For example, use this structure and replace the placeholder values with board tokens you have verified:

```json
{
  "employers": [
    {
      "display_name": "Example Employer",
      "board_token": "replace-with-verified-board-token"
    },
    {
      "display_name": "Another Employer",
      "board_token": "replace-with-another-verified-token"
    }
  ]
}
```

The display name is used in collection progress and error messages. The employer name returned by Greenhouse is retained on each opportunity as its organization.

Each employer is fetched independently. A failed employer is reported by display name, and collection continues for the remaining configured employers. A successful employer returning zero internship listings is reported as a success with zero listings, separate from a fetch failure. The final summary includes successful and failed employer counts, plus aggregate inserted, updated, and unchanged listing counts. The command exits with a nonzero status if any employer failed.

## Search

Search all stored opportunities by keyword:

```powershell
radar search Python
```

Optional filters can be used together:

```powershell
radar search --category Internship --location Remote
radar search research --category Fellowship --location Canada
```

The keyword searches title, organization, description, and eligibility. Category and location filters match those fields in the stored listing.

## SQLite storage and duplicate detection

The default database is `data/opportunities.sqlite3`. Change it with the global `--db` option, which goes before the command:

```powershell
radar --db data/local-opportunities.sqlite3 collect data/sample_opportunities.json
radar --db data/local-opportunities.sqlite3 search Python
```

SQLite enforces a unique constraint on `application_url`. Collecting the same URL again does not create another row: the store inserts new listings, updates listing information when it changes, and reports identical listings as unchanged. `last_seen` is refreshed only when listing information changes.

## Run the tests

Install the project's test tools in the active environment, then run the suite:

```powershell
python -m pip install -e ".[test]"
python -m pytest
```

If pytest cannot access its default temporary directory, use a directory inside the project workspace:

```powershell
python -m pytest --basetemp .pytest-tmp
```

Greenhouse tests use mocked HTTP responses and do not make real API requests. Tests that use temporary JSON files or databases use pytest's temporary-path fixture.

## Run the API locally

Install the API extra as shown in [Windows setup](#windows-setup), then start Uvicorn from the project directory:

```powershell
uvicorn opportunity_radar.api:app --reload
```

The server uses the same default SQLite path as the CLI: `data/opportunities.sqlite3`. Open `http://127.0.0.1:8000/docs` for the interactive API documentation.

Available endpoints:

- `GET /health` checks the API and SQLite connection.
- `GET /api/opportunities` lists all stored opportunities. Optional `q`, `category`, and `location` query parameters apply the existing store search filters.
- `GET /api/opportunities/{opportunity_id}` retrieves one opportunity by its SQLite ID and returns 404 when it does not exist.
