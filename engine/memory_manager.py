"""
memory_manager.py
Reads and writes MD files as structured agent memory.
Each file uses YAML frontmatter for metadata and markdown body for content.
"""

from __future__ import annotations
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


MEMORY_DIR = Path(__file__).parent.parent / "memory"


@dataclass
class MemoryEntry:
    memory_id: str
    domain: str
    title: str
    tags: list[str]
    confidence: float           # 0.0–1.0, how reliable this memory is
    source: str                 # "human_agent" | "engine" | "learning"
    created_at: str
    last_updated: str
    access_count: int
    body: str                   # markdown content
    file_path: str = ""

    def to_frontmatter(self) -> dict:
        return {
            "memory_id": self.memory_id,
            "domain": self.domain,
            "title": self.title,
            "tags": self.tags,
            "confidence": self.confidence,
            "source": self.source,
            "created_at": self.created_at,
            "last_updated": self.last_updated,
            "access_count": self.access_count,
        }

    def to_md(self) -> str:
        fm = yaml.dump(self.to_frontmatter(), default_flow_style=False, sort_keys=True)
        return f"---\n{fm}---\n\n{self.body.strip()}\n"


class MemoryManager:
    def __init__(self, memory_dir: Path | str | None = None):
        self.memory_dir = Path(memory_dir or MEMORY_DIR)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self._index: dict[str, MemoryEntry] = {}
        self._load_index()

    # ── Index ──────────────────────────────────────────────────────────────────
    def _load_index(self) -> None:
        self._index = {}
        for path in self.memory_dir.glob("**/*.md"):
            entry = self._parse_file(path)
            if entry:
                self._index[entry.memory_id] = entry

    def _parse_file(self, path: Path) -> MemoryEntry | None:
        text = path.read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---\n(.*)", text, re.DOTALL)
        if not match:
            return None
        try:
            fm = yaml.safe_load(match.group(1))
            body = match.group(2).strip()
            entry = MemoryEntry(
                memory_id=fm["memory_id"],
                domain=fm["domain"],
                title=fm["title"],
                tags=fm.get("tags", []),
                confidence=fm.get("confidence", 0.5),
                source=fm.get("source", "unknown"),
                created_at=fm["created_at"],
                last_updated=fm["last_updated"],
                access_count=fm.get("access_count", 0),
                body=body,
                file_path=str(path),
            )
            return entry
        except Exception:
            return None

    def refresh(self) -> None:
        self._load_index()

    # ── CRUD ───────────────────────────────────────────────────────────────────
    def create(
        self,
        domain: str,
        title: str,
        body: str,
        tags: list[str] | None = None,
        confidence: float = 0.7,
        source: str = "engine",
    ) -> MemoryEntry:
        now = datetime.now(timezone.utc).isoformat()
        entry = MemoryEntry(
            memory_id=str(uuid.uuid4()),
            domain=domain,
            title=title,
            tags=tags or [],
            confidence=confidence,
            source=source,
            created_at=now,
            last_updated=now,
            access_count=0,
            body=body,
        )
        self._write(entry)
        self._index[entry.memory_id] = entry
        return entry

    def read(self, memory_id: str) -> MemoryEntry | None:
        entry = self._index.get(memory_id)
        if entry:
            entry.access_count += 1
            entry.last_updated = datetime.now(timezone.utc).isoformat()
            self._write(entry)
        return entry

    def update(self, memory_id: str, body: str | None = None, confidence: float | None = None, tags: list[str] | None = None) -> MemoryEntry | None:
        entry = self._index.get(memory_id)
        if not entry:
            return None
        if body is not None:
            entry.body = body
        if confidence is not None:
            entry.confidence = max(0.0, min(1.0, confidence))
        if tags is not None:
            entry.tags = tags
        entry.last_updated = datetime.now(timezone.utc).isoformat()
        self._write(entry)
        return entry

    def append(self, memory_id: str, text: str, separator: str = "\n\n") -> MemoryEntry | None:
        entry = self._index.get(memory_id)
        if not entry:
            return None
        entry.body = entry.body.rstrip() + separator + text.strip()
        entry.last_updated = datetime.now(timezone.utc).isoformat()
        self._write(entry)
        return entry

    def upsert(self, domain: str, title: str, body: str, **kwargs) -> MemoryEntry:
        existing = self.search(domain=domain, title_contains=title, limit=1)
        if existing:
            return self.update(existing[0].memory_id, body=body) or existing[0]
        return self.create(domain=domain, title=title, body=body, **kwargs)

    def delete(self, memory_id: str) -> bool:
        entry = self._index.pop(memory_id, None)
        if entry and entry.file_path and Path(entry.file_path).exists():
            Path(entry.file_path).unlink()
            return True
        return False

    # ── Search ─────────────────────────────────────────────────────────────────
    def search(
        self,
        domain: str | None = None,
        tags: list[str] | None = None,
        title_contains: str | None = None,
        min_confidence: float = 0.0,
        limit: int = 20,
    ) -> list[MemoryEntry]:
        results = list(self._index.values())
        if domain:
            results = [e for e in results if e.domain == domain]
        if tags:
            results = [e for e in results if any(t in e.tags for t in tags)]
        if title_contains:
            results = [e for e in results if title_contains.lower() in e.title.lower()]
        results = [e for e in results if e.confidence >= min_confidence]
        results.sort(key=lambda e: e.last_updated, reverse=True)
        return results[:limit]

    def full_text_search(self, query: str, limit: int = 10) -> list[MemoryEntry]:
        q = query.lower()
        scored: list[tuple[float, MemoryEntry]] = []
        for entry in self._index.values():
            score = 0.0
            if q in entry.title.lower():
                score += 2.0
            if q in entry.body.lower():
                score += 1.0
            for tag in entry.tags:
                if q in tag.lower():
                    score += 0.5
            if score > 0:
                scored.append((score * entry.confidence, entry))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:limit]]

    def all(self) -> list[MemoryEntry]:
        return list(self._index.values())

    # ── Internals ──────────────────────────────────────────────────────────────
    def _write(self, entry: MemoryEntry) -> None:
        if not entry.file_path:
            safe_title = re.sub(r"[^\w\-]", "_", entry.title.lower())[:48]
            subdir = self.memory_dir / entry.domain
            subdir.mkdir(parents=True, exist_ok=True)
            entry.file_path = str(subdir / f"{safe_title}_{entry.memory_id[:8]}.md")
        Path(entry.file_path).write_text(entry.to_md(), encoding="utf-8")

    def stats(self) -> dict:
        entries = list(self._index.values())
        domains: dict[str, int] = {}
        for e in entries:
            domains[e.domain] = domains.get(e.domain, 0) + 1
        return {
            "total": len(entries),
            "domains": domains,
            "avg_confidence": sum(e.confidence for e in entries) / len(entries) if entries else 0,
        }
