from __future__ import annotations

import asyncio
import logging

from feishu_campus_longmemory.proactive.dispatcher import ReminderDispatcher

logger = logging.getLogger(__name__)


class ReminderScheduler:
    def __init__(self, dispatcher: ReminderDispatcher, *, poll_interval_seconds: int) -> None:
        self._dispatcher = dispatcher
        self._poll_interval_seconds = poll_interval_seconds

    async def run(self) -> None:
        logger.info("Reminder scheduler started")
        try:
            while True:
                try:
                    self._dispatcher.trigger_due()
                except Exception as exc:  # pragma: no cover - defensive guard for background loop
                    logger.exception("Reminder scheduler tick failed", exc_info=exc)
                await asyncio.sleep(self._poll_interval_seconds)
        except asyncio.CancelledError:
            logger.info("Reminder scheduler stopped")
            raise

