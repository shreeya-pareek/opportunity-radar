import sqlite3
from pathlib import Path

from .models import Opportunity


class OpportunityStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS opportunities (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                organization TEXT NOT NULL,
                category TEXT NOT NULL,
                location TEXT NOT NULL,
                description TEXT NOT NULL,
                eligibility TEXT NOT NULL,
                deadline TEXT NOT NULL,
                application_url TEXT NOT NULL UNIQUE,
                source_name TEXT NOT NULL,
                first_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.connection.commit()

    def upsert(self, opportunity: Opportunity) -> str:
        fields = (
            "title", "organization", "category", "location", "description",
            "eligibility", "deadline", "application_url", "source_name",
        )
        values = tuple(getattr(opportunity, field) for field in fields)
        existing = self.connection.execute(
            "SELECT " + ", ".join(fields) + " FROM opportunities WHERE application_url = ?",
            (opportunity.application_url,),
        ).fetchone()

        if existing is None:
            self.connection.execute(
                "INSERT INTO opportunities (" + ", ".join(fields) + ") VALUES ("
                + ", ".join("?" for _ in fields) + ")",
                values,
            )
            self.connection.commit()
            return "inserted"

        if all(
            existing[field] == getattr(opportunity, field)
            for field in fields
            if field != "application_url"
        ):
            return "unchanged"

        self.connection.execute("""
            UPDATE opportunities SET
                title=?, organization=?, category=?, location=?, description=?,
                eligibility=?, deadline=?, source_name=?, last_seen=CURRENT_TIMESTAMP
            WHERE application_url=?
        """, values[:7] + (opportunity.source_name, opportunity.application_url))
        self.connection.commit()
        return "updated"

    def search(
        self,
        query: str = "",
        category: str = "",
        location: str = "",
        company: str = "",
    ) -> list[sqlite3.Row]:
        clauses, values = [], []
        if query:
            clauses.append("(title LIKE ? OR organization LIKE ? OR description LIKE ? OR eligibility LIKE ?)")
            values.extend([f"%{query}%"] * 4)
        if category:
            clauses.append("category LIKE ?")
            values.append(f"%{category}%")
        if location:
            clauses.append("location LIKE ?")
            values.append(f"%{location}%")
        if company:
            clauses.append("organization LIKE ?")
            values.append(f"%{company}%")
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        return self.connection.execute(
            "SELECT * FROM opportunities" + where + " ORDER BY deadline = '', deadline, title", values
        ).fetchall()

    def get_by_id(self, opportunity_id: int) -> sqlite3.Row | None:
        return self.connection.execute(
            "SELECT * FROM opportunities WHERE id = ?", (opportunity_id,)
        ).fetchone()

    def check_health(self) -> bool:
        try:
            self.connection.execute("SELECT 1").fetchone()
        except sqlite3.Error:
            return False
        return True

    def close(self) -> None:
        self.connection.close()
