from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Opportunity:
    title: str
    organization: str
    category: str
    location: str
    description: str
    eligibility: str
    deadline: str
    application_url: str
    source_name: str

    @classmethod
    def from_mapping(cls, item: dict, source_name: str) -> "Opportunity":
        required = ("title", "application_url")
        missing = [key for key in required if not str(item.get(key, "")).strip()]
        if missing:
            raise ValueError(f"Missing required field(s): {', '.join(missing)}")
        return cls(
            title=str(item["title"]).strip(),
            organization=str(item.get("organization", "")).strip(),
            category=str(item.get("category", "Other")).strip() or "Other",
            location=str(item.get("location", "Unspecified")).strip() or "Unspecified",
            description=str(item.get("description", "")).strip(),
            eligibility=str(item.get("eligibility", "Not provided by source")).strip(),
            deadline=str(item.get("deadline", "")).strip(),
            application_url=str(item["application_url"]).strip(),
            source_name=source_name.strip(),
        )
