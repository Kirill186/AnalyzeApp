from __future__ import annotations

from dataclasses import dataclass
from queue import Empty, Queue
from threading import Event, Thread
from time import sleep
from typing import Callable, Any


@dataclass(slots=True)
class Job:
    job_type: str
    key: str
    payload: dict[str, Any]


class AnalysisQueue:
    def __init__(self) -> None:
        self._queue: Queue[Job] = Queue()
        self._seen_keys: set[str] = set()

    def enqueue(self, job: Job) -> bool:
        if job.key in self._seen_keys:
            return False
        self._seen_keys.add(job.key)
        self._queue.put(job)
        return True

    def get(self, timeout: float = 0.2) -> Job | None:
        try:
            return self._queue.get(timeout=timeout)
        except Empty:
            return None


class QueueWorker:
    def __init__(self, queue: AnalysisQueue, handlers: dict[str, Callable[[Job], None]]) -> None:
        self.queue = queue
        self.handlers = handlers
        self._stop = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)

    def _run(self) -> None:
        while not self._stop.is_set():
            job = self.queue.get()
            if not job:
                sleep(0.05)
                continue
            handler = self.handlers.get(job.job_type)
            if handler:
                handler(job)
