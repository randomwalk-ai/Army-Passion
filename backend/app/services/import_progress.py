"""How far a long import step has got, so the screen can show a progress bar.

The import itself runs in one transaction that is only committed at the end,
so nobody else can see its rows until then. Progress is therefore written on
its OWN connection and committed straight away, where the screen's "how far
along?" request can read it.

It never slows the import down or blocks it:
- it writes at most a couple of times a second, not once per row;
- if the upload record happens to be locked, that update is skipped
  (SKIP LOCKED) instead of waiting, and the next one tries again;
- any error while writing progress is ignored: a progress bar is not worth
  failing an import for.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from app.db import engine

logger = logging.getLogger(__name__)

MIN_SECONDS_BETWEEN_WRITES = 0.4

_WRITE = text(
    """
    UPDATE import_batches SET progress = CAST(:progress AS jsonb)
    WHERE id = (
        SELECT id FROM import_batches WHERE id = :id FOR UPDATE SKIP LOCKED
    )
    """
)


def write_progress(import_id: int, progress: dict[str, Any] | None) -> None:
    """Save the progress now, on a separate connection. Never raises."""
    try:
        with engine.begin() as connection:
            connection.execute(
                _WRITE,
                {"id": import_id, "progress": None if progress is None else json.dumps(progress)},
            )
    except Exception as exc:  # noqa: BLE001 - see the module docstring
        logger.warning("Could not save import progress for #%s: %s", import_id, exc)


class ProgressTracker:
    """Pass `tracker.update` as the `on_progress` of build_preview / apply_import."""

    def __init__(self, import_id: int) -> None:
        self.import_id = import_id
        self.started_at = datetime.now(timezone.utc).isoformat()
        self._stage: str | None = None
        self._stage_started = time.monotonic()
        self._last_write = 0.0

    def update(self, stage: str, done: int, total: int) -> None:
        now = time.monotonic()
        new_stage = stage != self._stage
        if new_stage:
            self._stage = stage
            self._stage_started = now
        finished = done >= total
        if not (new_stage or finished or now - self._last_write >= MIN_SECONDS_BETWEEN_WRITES):
            return
        self._last_write = now
        write_progress(
            self.import_id,
            {
                "stage": stage,
                "done": done,
                "total": total,
                # Seconds spent on this stage so far: the screen works out the
                # time left from how fast it is going.
                "elapsed": round(now - self._stage_started, 1),
                "started_at": self.started_at,
            },
        )

    def clear(self) -> None:
        write_progress(self.import_id, None)
