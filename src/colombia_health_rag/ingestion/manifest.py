"""Validate provenance for public, official regulation documents."""

from datetime import date
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    TypeAdapter,
    field_validator,
)

OFFICIAL_DOMAINS = ("minsalud.gov.co",)


class SourceRecord(BaseModel):
    """Metadata required before a public document can enter the corpus."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_url: HttpUrl
    authority: str = Field(min_length=1)
    title: str = Field(min_length=1)
    publication_date: date
    version: str = Field(min_length=1)
    retrieved_at: AwareDatetime
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reuse_terms: str = Field(min_length=1)
    raw_path: str
    public_document_confirmed: Literal[True]
    personal_data_scope: Literal["official_attribution_only"]

    @field_validator("source_url")
    @classmethod
    def official_https_url(cls, value: HttpUrl) -> HttpUrl:
        """Accept HTTPS URLs only from reviewed government source domains."""
        host = value.host or ""
        if value.scheme != "https" or not any(
            host == domain or host.endswith(f".{domain}") for domain in OFFICIAL_DOMAINS
        ):
            raise ValueError("source_url must use HTTPS on an approved official domain")
        return value

    @field_validator("raw_path")
    @classmethod
    def raw_file_path(cls, value: str) -> str:
        """Keep raw files under the project's immutable raw-data directory."""
        parts = PurePosixPath(value).parts
        if (
            len(parts) < 3
            or parts[:2] != ("data", "01_raw")
            or ".." in parts
            or PurePosixPath(value).as_posix() != value
        ):
            raise ValueError("raw_path must be a relative file in data/01_raw")
        return value


def load_manifest(path: Path) -> list[SourceRecord]:
    """Read and validate every record in a JSON manifest."""
    return TypeAdapter(list[SourceRecord]).validate_json(path.read_bytes())


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Validate official-source metadata")
    parser.add_argument("path", nargs="?", type=Path, default=Path("data/manifest.json"))
    records = load_manifest(parser.parse_args().path)
    print(f"Validated {len(records)} source records")
