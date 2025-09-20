from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional


ProgressReporter = Callable[[str], None]


@dataclass
class JobRecord:
    id: str
    user_id: Optional[str]
    status: str = "queued"  # queued | running | done | error
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    result: Optional[dict | str] = None
    error: Optional[str] = None
    message: Optional[str] = None
    log: list[str] = field(default_factory=list)


class JobStore:
    def __init__(self) -> None:
        self._jobs: Dict[str, JobRecord] = {}

    def get(self, job_id: str) -> Optional[JobRecord]:
        return self._jobs.get(job_id)

    def start(
        self,
        coro_factory: Callable[[], Awaitable[Any]],
        *,
        user_id: Optional[str] = None,
        on_progress: Optional[ProgressReporter] = None,
        bind_progress: Optional[Callable[[ProgressReporter], None]] = None,
        on_finalize: Optional[Callable[[], None]] = None,
    ) -> str:
        job_id = str(uuid.uuid4())
        rec = JobRecord(id=job_id, user_id=user_id)
        self._jobs[job_id] = rec

        async def _runner() -> None:
            j = self._jobs.get(job_id)
            if not j:
                return
            j.status = "running"
            j.started_at = datetime.now(timezone.utc)

            def _report(msg: str) -> None:
                jj = self._jobs.get(job_id)
                if not jj:
                    return
                jj.log.append(msg)
                jj.message = msg
                if on_progress:
                    try:
                        on_progress(msg)
                    except Exception:
                        pass

            try:
                if bind_progress:
                    try:
                        bind_progress(_report)
                    except Exception:
                        pass
                res = await coro_factory()
                j.result = res
                j.status = "done"
            except Exception as e:  # noqa: BLE001 - capture into record
                j.error = str(e)
                j.status = "error"
            finally:
                j.finished_at = datetime.now(timezone.utc)
                if on_finalize:
                    try:
                        on_finalize()
                    except Exception:
                        pass

        asyncio.create_task(_runner())
        return job_id


# Singleton store for simple use-cases
job_store = JobStore()
