"""Small JSON session store with an append-only event log."""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from core.agent.session import Session


class SessionStore:
    def __init__(self, project_root: Path | str, directory: str = ".agents/sessions",
                 export_dir: str = ".agents/exports", event_log: bool = True) -> None:
        self.project_root = Path(project_root).expanduser().resolve()
        self.directory = (self.project_root / directory).resolve()
        self.export_dir = (self.project_root / export_dir).resolve()
        self.event_log_enabled = event_log

    @staticmethod
    def new_id() -> str:
        return datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]

    def save(self, session_id: str, session: Session, title: str = "新会话") -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", session_id):
            raise ValueError("非法会话编号")
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self.directory / f"{session_id}.json"
        payload = {
            "id": session_id,
            "title": title[:120],
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "session": session.to_dict(),
        }
        temp = target.with_suffix(".json.tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(target)
        return target

    def append_event(self, session_id: str, event: dict[str, Any]) -> None:
        if not self.event_log_enabled:
            return
        if not re.fullmatch(r"[A-Za-z0-9_-]+", session_id):
            raise ValueError("非法会话编号")
        self.directory.mkdir(parents=True, exist_ok=True)
        with (self.directory / f"{session_id}.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def list_sessions(self, limit: int = 30) -> list[dict[str, str]]:
        if not self.directory.is_dir():
            return []
        result = []
        for path in sorted(self.directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                result.append({"id": payload["id"], "title": payload.get("title", ""),
                               "updated_at": payload.get("updated_at", "")})
            except (OSError, ValueError, KeyError, TypeError):
                continue
            if len(result) >= max(1, limit):
                break
        return result

    def load(self, session_id: str) -> tuple[Session, str]:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", session_id):
            raise ValueError("非法会话编号")
        payload = json.loads((self.directory / f"{session_id}.json").read_text(encoding="utf-8"))
        return Session.from_dict(payload["session"]), str(payload.get("title", ""))

    def replay(self, session_id: str) -> list[dict[str, Any]]:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", session_id):
            raise ValueError("非法会话编号")
        path = self.directory / f"{session_id}.jsonl"
        events: list[dict[str, Any]] = []
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    value = json.loads(line)
                except ValueError:
                    continue
                if isinstance(value, dict):
                    events.append(value)
        return events
