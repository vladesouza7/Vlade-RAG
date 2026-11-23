"""Ingestion worker (docs/ARCHITECTURE.md section 10.1).

The worker claims jobs with a lease, renews the lease while a job runs, and returns expired
jobs of crashed workers to the queue.
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
from contextlib import suppress

from vlade_rag.bootstrap import Runtime
from vlade_rag.core.application import RunIngestionJob
from vlade_rag.core.domain import JobKind
from vlade_rag.core.ports import ClaimedJob

logger = logging.getLogger(__name__)
REQUEUE_EVERY_SECONDS = 30.0


class Worker:
    def __init__(
        self,
        runtime: Runtime,
        *,
        worker_id: str | None = None,
        concurrency: int | None = None,
        poll_interval: float | None = None,
        lease_seconds: int | None = None,
    ) -> None:
        cfg = runtime.settings.worker
        self.runtime = runtime
        self.queue = runtime.deps.job_queue
        self.runner = RunIngestionJob(runtime.deps)
        self.worker_id = worker_id or f"{socket.gethostname()}-{os.getpid()}"
        self.concurrency = concurrency or cfg.concurrency
        self.poll_interval = poll_interval or cfg.poll_interval
        self.lease_seconds = lease_seconds or cfg.lease_seconds
        self.max_attempts = runtime.deps.limits.job_max_attempts

    async def _heartbeat(self, job_id: object) -> None:
        interval = max(1.0, self.lease_seconds / 3)
        while True:
            await asyncio.sleep(interval)
            await self.queue.heartbeat(job_id, self.worker_id, self.lease_seconds)  # type: ignore[arg-type]

    async def process(self, claimed: ClaimedJob) -> None:
        beat = asyncio.create_task(self._heartbeat(claimed.job.id))
        try:
            await self.runner.execute(claimed)
        except Exception:
            logger.exception("Job %s crashed", claimed.job.id)
            await self.queue.fail(
                claimed.ctx,
                claimed.job.id,
                {"code": "internal", "message": "The worker crashed while running the job."},
                retry=True,
                max_attempts=self.max_attempts,
            )
        finally:
            beat.cancel()
            with suppress(asyncio.CancelledError):
                await beat

    async def _record_queue_depth(self) -> None:
        metrics = self.runtime.deps.metrics
        for kind in JobKind:
            metrics.gauge(
                "vlade_ingestion_queue_depth",
                await self.queue.pending_count(kind),
                {"kind": kind.value},
            )

    async def run_until_idle(self) -> int:
        """Run pending jobs one by one until the queue is empty. Returns the number of jobs."""
        count = 0
        while (claimed := await self.queue.claim(self.worker_id, self.lease_seconds)) is not None:
            await self.process(claimed)
            count += 1
        await self._record_queue_depth()
        return count

    async def run(self, stop: asyncio.Event | None = None) -> None:
        """Run until ``stop`` is set (or the task is cancelled)."""
        stop = stop or asyncio.Event()
        active: set[asyncio.Task[None]] = set()
        loop = asyncio.get_running_loop()
        next_requeue = 0.0
        logger.info("Worker %s started (concurrency=%d)", self.worker_id, self.concurrency)
        try:
            while not stop.is_set():
                if loop.time() >= next_requeue:
                    requeued = await self.queue.requeue_expired(self.max_attempts)
                    if requeued:
                        logger.warning("Requeued %d expired jobs", requeued)
                    next_requeue = loop.time() + REQUEUE_EVERY_SECONDS
                    await self._record_queue_depth()
                claimed = None
                if len(active) < self.concurrency:
                    claimed = await self.queue.claim(self.worker_id, self.lease_seconds)
                if claimed is not None:
                    task = asyncio.create_task(self.process(claimed))
                    active.add(task)
                    task.add_done_callback(active.discard)
                    continue
                with suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=self.poll_interval)
        finally:
            if active:
                await asyncio.gather(*active, return_exceptions=True)
            logger.info("Worker %s stopped", self.worker_id)
