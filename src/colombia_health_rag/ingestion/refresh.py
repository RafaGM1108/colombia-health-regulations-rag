"""Download official PDFs without replacing reviewed source snapshots."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess  # nosec B404
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

from colombia_health_rag.ingestion.manifest import SourceRecord, load_manifest

MAX_PDF_BYTES = 50 * 1024 * 1024
type Fetcher = Callable[[str], bytes]


class RefreshError(ValueError):
    """Report a source, checksum, or review problem without changing snapshots."""


@dataclass(frozen=True)
class CheckResult:
    """Describe the live version found at one reviewed source URL."""

    source_url: str
    status: Literal["unchanged", "known_version", "changed"]
    sha256: str
    candidate_path: Path | None = None


def fetch_pdf(url: str) -> bytes:
    """Fetch one PDF from an already validated official URL without redirects."""
    curl = shutil.which("curl")
    if curl is None:
        raise RefreshError("curl is required for official PDF downloads")
    try:
        # The URL comes from the validated manifest; the command uses no shell.
        result = subprocess.run(  # nosec B603
            [
                str(Path(curl).resolve()),
                "--fail",
                "--silent",
                "--show-error",
                "--proto",
                "=https",
                "--max-filesize",
                str(MAX_PDF_BYTES),
                "--connect-timeout",
                "15",
                "--max-time",
                "90",
                url,
            ],
            capture_output=True,
            check=True,
            timeout=95,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise RefreshError(f"Official PDF download failed: {url}") from error
    return _check_pdf(result.stdout)


def _check_pdf(data: bytes) -> bytes:
    if len(data) > MAX_PDF_BYTES or not data.startswith(b"%PDF-"):
        raise RefreshError("Source is not a PDF within the 50 MiB limit")
    return data


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _raw_path(root: Path, relative: str) -> Path:
    raw_dir = (root / "data/01_raw").resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(raw_dir):
        raise RefreshError(f"Raw path escapes data/01_raw: {relative}")
    return path


def _write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as output:
            output.write(data)
    except FileExistsError:
        if _sha256(path.read_bytes()) != _sha256(data):
            raise RefreshError(f"Existing raw file has different bytes: {path}") from None


def _write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as file:
            temporary = file.name
            json.dump(value, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)


def check_sources(
    manifest_path: Path, fetcher: Fetcher = fetch_pdf
) -> tuple[list[CheckResult], list[Path]]:
    """Check live URLs and restore only exact, previously recorded snapshots."""
    manifest = load_manifest(manifest_path)
    root = manifest_path.resolve().parent.parent
    for record in manifest:
        local = _raw_path(root, record.raw_path)
        if local.exists() and _sha256(local.read_bytes()) != record.sha256:
            raise RefreshError(f"Local snapshot differs from manifest: {record.raw_path}")

    by_url: dict[str, list[SourceRecord]] = {}
    for record in manifest:
        by_url.setdefault(str(record.source_url), []).append(record)

    results: list[CheckResult] = []
    for url, versions in by_url.items():
        data = _check_pdf(fetcher(url))
        digest = _sha256(data)
        recorded = next((version for version in versions if version.sha256 == digest), None)
        if recorded is not None:
            _write_new(_raw_path(root, recorded.raw_path), data)
            latest = max(versions, key=lambda version: version.retrieved_at)
            status: Literal["unchanged", "known_version", "changed"] = (
                "unchanged" if recorded.sha256 == latest.sha256 else "known_version"
            )
            results.append(CheckResult(url, status, digest))
            continue

        candidate = _raw_path(root, f"data/01_raw/candidates/{digest}.pdf")
        _write_new(candidate, data)
        sidecar = candidate.with_suffix(".json")
        if sidecar.exists():
            saved = json.loads(sidecar.read_text(encoding="utf-8"))
            if (
                not isinstance(saved, dict)
                or saved.get("source_url") != url
                or saved.get("sha256") != digest
            ):
                raise RefreshError(f"Candidate download record differs: {sidecar}")
        else:
            _write_new(
                sidecar,
                json.dumps(
                    {
                        "source_url": url,
                        "sha256": digest,
                        "retrieved_at": datetime.now(UTC).isoformat(),
                    },
                    ensure_ascii=False,
                    indent=2,
                ).encode("utf-8"),
            )
        results.append(CheckResult(url, "changed", digest, candidate))

    missing = [
        _raw_path(root, record.raw_path)
        for record in manifest
        if not _raw_path(root, record.raw_path).exists()
    ]
    return results, missing


def record_candidate(
    manifest_path: Path,
    candidate_path: Path,
    *,
    title: str,
    publication_date: date,
    version: str,
    reuse_terms: str,
    public_document_reviewed: bool,
    personal_data_reviewed: bool,
) -> SourceRecord:
    """Append a manually reviewed candidate as a new immutable source version."""
    if not public_document_reviewed or not personal_data_reviewed:
        raise RefreshError("Both source and personal-data review confirmations are required")
    manifest = load_manifest(manifest_path)
    root = manifest_path.resolve().parent.parent
    candidate = _raw_path(root, str(candidate_path.resolve().relative_to(root)))
    if candidate.parent != _raw_path(root, "data/01_raw/candidates"):
        raise RefreshError("Candidate must be in data/01_raw/candidates")
    data = _check_pdf(candidate.read_bytes())
    digest = _sha256(data)
    metadata = json.loads(candidate.with_suffix(".json").read_text(encoding="utf-8"))
    if (
        not isinstance(metadata, dict)
        or metadata.get("sha256") != digest
        or candidate.stem != digest
    ):
        raise RefreshError("Candidate bytes or filename differ from its download record")

    url = metadata.get("source_url")
    versions = [record for record in manifest if str(record.source_url) == url]
    if not versions:
        raise RefreshError("Candidate URL is not in the reviewed manifest")
    if any(record.sha256 == digest or record.version == version for record in versions):
        raise RefreshError("This source checksum or version is already recorded")

    latest = max(versions, key=lambda record: record.retrieved_at)
    raw_relative = f"data/01_raw/versions/{digest}.pdf"
    proposed = SourceRecord.model_validate(
        latest.model_dump(mode="json")
        | {
            "title": title,
            "publication_date": publication_date.isoformat(),
            "version": version,
            "retrieved_at": metadata.get("retrieved_at"),
            "sha256": digest,
            "reuse_terms": reuse_terms,
            "raw_path": raw_relative,
        }
    )
    _write_new(_raw_path(root, raw_relative), data)
    _write_json_atomic(
        manifest_path, [record.model_dump(mode="json") for record in [*manifest, proposed]]
    )
    return proposed


def main() -> int:
    """Run the source check or record a manually reviewed new version."""
    parser = argparse.ArgumentParser(description="Check and version official regulation PDFs")
    parser.add_argument("--manifest", type=Path, default=Path("data/manifest.json"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="download and compare each live source")
    record = commands.add_parser("record", help="append a reviewed changed PDF")
    record.add_argument("candidate", type=Path)
    record.add_argument("--title", required=True)
    record.add_argument("--publication-date", type=date.fromisoformat, required=True)
    record.add_argument("--version", required=True)
    record.add_argument("--reuse-terms", required=True)
    record.add_argument("--public-document-reviewed", action="store_true")
    record.add_argument("--personal-data-reviewed", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "record":
            source = record_candidate(
                args.manifest,
                args.candidate,
                title=args.title,
                publication_date=args.publication_date,
                version=args.version,
                reuse_terms=args.reuse_terms,
                public_document_reviewed=args.public_document_reviewed,
                personal_data_reviewed=args.personal_data_reviewed,
            )
            print(f"Recorded {source.source_url} as {source.raw_path}")
            return 0

        results, missing = check_sources(args.manifest)
        for result in results:
            print(f"{result.status}: {result.source_url} ({result.sha256})")
            if result.candidate_path:
                print(f"  review candidate: {result.candidate_path}")
        for path in missing:
            print(f"Missing historical snapshot: {path}")
        return 1 if missing or any(result.status != "unchanged" for result in results) else 0
    except (OSError, RefreshError, ValueError) as error:
        parser.exit(2, f"Source refresh failed: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
