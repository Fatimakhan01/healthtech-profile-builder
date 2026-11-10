"""Restricted extraction and deterministic chunking for approved policy files."""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from django.db import transaction

from .models import PolicyChunk, PolicyDocument


APPROVED_POLICY_DIR = Path(__file__).resolve().parent / "policies" / "approved"
SUPPORTED_SUFFIXES = {".md", ".txt"}
DEFAULT_CHUNK_SIZE = 1_000
DEFAULT_CHUNK_OVERLAP = 150


class PolicyIngestionError(Exception):
    """An approved policy source could not be safely extracted."""


@dataclass(frozen=True)
class ExtractedDocument:
    source_filename: str
    title: str
    text: str
    content_sha256: str


@dataclass(frozen=True)
class IngestionSummary:
    processed: int = 0
    created: int = 0
    unchanged: int = 0
    updated: int = 0
    chunks_created: int = 0
    chunks_updated: int = 0


def _approved_file(path: Path) -> Path:
    if APPROVED_POLICY_DIR.is_symlink():
        raise PolicyIngestionError(
            "The approved policy directory cannot be a symbolic link."
        )
    approved_root = APPROVED_POLICY_DIR.resolve()
    if path.is_symlink():
        raise PolicyIngestionError("Symbolic links are not approved policy sources.")
    resolved = path.resolve()
    if resolved.parent != approved_root:
        raise PolicyIngestionError(
            "Policy sources must be direct files in the approved policy directory."
        )
    if resolved.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise PolicyIngestionError("Only .md and .txt policy sources are supported.")
    if not resolved.is_file():
        raise PolicyIngestionError("Policy source is not a regular file.")
    return resolved


def _extract_markdown(markdown: str) -> tuple[str | None, str]:
    title = None
    body_lines = []
    for line in markdown.splitlines():
        heading = re.match(r"^\s{0,3}#\s+(.+?)\s*#*\s*$", line)
        if heading and title is None:
            title = heading.group(1).strip()
            continue
        line = re.sub(r"^\s{0,3}#{1,6}\s*", "", line)
        line = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", line)
        line = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", line)
        line = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", line)
        line = re.sub(r"`([^`]*)`", r"\1", line)
        line = re.sub(r"(\*\*|__|\*|_)(.*?)\1", r"\2", line)
        body_lines.append(line.rstrip())

    text = "\n".join(body_lines).strip()
    return title, text


def extract_document(path: Path) -> ExtractedDocument:
    source = _approved_file(path)
    try:
        raw_bytes = source.read_bytes()
        raw_text = raw_bytes.decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise PolicyIngestionError("Policy source must be readable UTF-8 text.") from error

    if source.suffix.lower() == ".md":
        title, text = _extract_markdown(raw_text)
    else:
        title, text = None, raw_text.strip()
    if not text:
        raise PolicyIngestionError("Policy source is empty after text extraction.")

    title = title or source.stem.replace("_", " ").replace("-", " ").strip()
    if not title:
        raise PolicyIngestionError("Policy source has no usable document title.")
    digest = hashlib.sha256(raw_bytes).hexdigest()
    return ExtractedDocument(source.name, title, text, digest)


def _validate_chunk_parameters(chunk_size: int, overlap: int) -> None:
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive.")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be non-negative and smaller than chunk_size.")


def _chunk_end(text: str, start: int, maximum: int) -> int:
    end = min(start + maximum, len(text))
    if end == len(text):
        return end

    preferred_start = start + maximum // 2
    paragraph_break = text.rfind("\n\n", preferred_start, end)
    if paragraph_break > start:
        return paragraph_break

    whitespace = text.rfind(" ", preferred_start, end)
    newline = text.rfind("\n", preferred_start, end)
    boundary = max(whitespace, newline)
    if boundary > start:
        return boundary

    boundary = max(text.rfind(" ", start, end), text.rfind("\n", start, end))
    return boundary if boundary > start else end


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    _validate_chunk_parameters(chunk_size, overlap)

    paragraphs = [
        re.sub(r"[ \t]+", " ", paragraph).strip()
        for paragraph in re.split(r"\n\s*\n", text.strip())
    ]
    normalized_text = "\n\n".join(paragraph for paragraph in paragraphs if paragraph)
    if not normalized_text:
        return []

    chunks = []
    start = 0
    while start < len(normalized_text):
        end = _chunk_end(normalized_text, start, chunk_size)
        chunk = normalized_text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized_text):
            break
        if overlap:
            next_start = max(start + 1, end - overlap)
            word_boundary = max(
                normalized_text.rfind(" ", start + 1, next_start),
                normalized_text.rfind("\n", start + 1, next_start),
            )
            if word_boundary >= start:
                next_start = word_boundary + 1
        else:
            next_start = end
        start = next_start
    return chunks


@transaction.atomic
def ingest_document(
    source_path: Path,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> tuple[str, int]:
    extracted = extract_document(source_path)
    existing = PolicyDocument.objects.filter(
        source_filename=extracted.source_filename
    ).first()
    if (
        existing is not None
        and existing.content_sha256 == extracted.content_sha256
        and existing.chunk_size == chunk_size
        and existing.chunk_overlap == overlap
    ):
        return "unchanged", existing.chunks.count()

    document, created = PolicyDocument.objects.update_or_create(
        source_filename=extracted.source_filename,
        defaults={
            "title": extracted.title,
            "content_sha256": extracted.content_sha256,
            "chunk_size": chunk_size,
            "chunk_overlap": overlap,
        },
    )
    document.chunks.all().delete()
    chunks = chunk_text(extracted.text, chunk_size=chunk_size, overlap=overlap)
    PolicyChunk.objects.bulk_create(
        [
            PolicyChunk(
                document=document,
                chunk_index=index,
                text=text,
            )
            for index, text in enumerate(chunks)
        ]
    )
    return ("created" if created else "updated"), len(chunks)


def ingest_approved_documents(
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> IngestionSummary:
    _validate_chunk_parameters(chunk_size, overlap)
    if not APPROVED_POLICY_DIR.is_dir():
        raise PolicyIngestionError("Approved policy directory is missing.")

    paths = sorted(APPROVED_POLICY_DIR.iterdir(), key=lambda path: path.name.casefold())
    outcomes = {"created": 0, "unchanged": 0, "updated": 0}
    chunk_counts = {"created": 0, "updated": 0}
    processed = 0
    for path in paths:
        if path.is_dir() and not path.is_symlink():
            continue
        outcome, count = ingest_document(path, chunk_size, overlap)
        outcomes[outcome] += 1
        if outcome == "created":
            chunk_counts["created"] += count
        elif outcome == "updated":
            chunk_counts["updated"] += count
        processed += 1

    return IngestionSummary(
        processed=processed,
        created=outcomes["created"],
        unchanged=outcomes["unchanged"],
        updated=outcomes["updated"],
        chunks_created=chunk_counts["created"],
        chunks_updated=chunk_counts["updated"],
    )
