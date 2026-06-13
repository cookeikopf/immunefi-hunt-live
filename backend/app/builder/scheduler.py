"""Hintergrund-Scheduler für zeitgesteuerte Automationen.

Ein einfacher asyncio-Task mit 60-Sekunden-Tick — bewusst in-process
(genau 1 Uvicorn-Worker, siehe Deployment-Doku). Abschaltbar über
KMUOS_SCHEDULER_ENABLED=false (z. B. in Tests oder beim Scale-out).
"""

import asyncio
import logging

from .automations import run_scheduled

logger = logging.getLogger(__name__)

TICK_SECONDS = 60

_task: asyncio.Task | None = None


async def _loop() -> None:
    while True:
        try:
            executed = await asyncio.to_thread(run_scheduled)
            if executed:
                logger.info("Scheduler: %d Automation(en) ausgeführt", executed)
        except Exception:
            logger.exception("Scheduler-Tick fehlgeschlagen")
        await asyncio.sleep(TICK_SECONDS)


def start() -> None:
    global _task
    if _task is None or _task.done():
        _task = asyncio.get_event_loop().create_task(_loop())


def stop() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        _task = None
