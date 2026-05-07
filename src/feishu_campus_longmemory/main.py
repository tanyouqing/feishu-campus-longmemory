from __future__ import annotations

import logging
import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from feishu_campus_longmemory.api.events import router as events_router
from feishu_campus_longmemory.api.feishu import router as feishu_router
from feishu_campus_longmemory.api.health import router as health_router
from feishu_campus_longmemory.api.memory import router as memory_router
from feishu_campus_longmemory.api.proactive import router as proactive_router
from feishu_campus_longmemory.api.profile import router as profile_router
from feishu_campus_longmemory.config import Settings, get_settings
from feishu_campus_longmemory.db import check_database, create_database_engine, run_migrations
from feishu_campus_longmemory.errors import register_error_handlers
from feishu_campus_longmemory.logging import setup_logging
from feishu_campus_longmemory.proactive.dispatcher import ReminderDispatcher
from feishu_campus_longmemory.proactive.feishu import FeishuMessageSender
from feishu_campus_longmemory.proactive.scheduler import ReminderScheduler

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    setup_logging(resolved_settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger.info("Starting service")
        run_migrations(resolved_settings)
        engine = create_database_engine(resolved_settings)
        check_database(engine)
        app.state.settings = resolved_settings
        app.state.db_engine = engine
        scheduler_task: asyncio.Task[None] | None = None
        if resolved_settings.reminder_scheduler_enabled:
            if not resolved_settings.feishu_app_id or not resolved_settings.feishu_app_secret:
                logger.error(
                    "Reminder scheduler disabled because Feishu sender is not configured. "
                    "Set LONGMEMORY_FEISHU_APP_ID and LONGMEMORY_FEISHU_APP_SECRET, "
                    "and confirm the Feishu app has im:message:send_as_bot permission."
                )
            else:
                app.state.reminder_sender = FeishuMessageSender(resolved_settings)
                dispatcher = ReminderDispatcher(engine, resolved_settings, sender=app.state.reminder_sender)
                scheduler = ReminderScheduler(
                    dispatcher,
                    poll_interval_seconds=resolved_settings.reminder_poll_interval_seconds,
                )
                scheduler_task = asyncio.create_task(scheduler.run())
                scheduler_task.add_done_callback(
                    lambda t: logger.error(f"Reminder Scheduler CRASHED: {t.exception()}", exc_info=t.exception()) if not t.cancelled() and t.exception() else None
                )
        try:
            yield
        finally:
            if scheduler_task is not None:
                scheduler_task.cancel()
                try:
                    await scheduler_task
                except asyncio.CancelledError:
                    pass
            engine.dispose()
            logger.info("Service stopped")

    app = FastAPI(
        title=resolved_settings.service_name,
        version=resolved_settings.version,
        lifespan=lifespan,
    )
    register_error_handlers(app)
    app.include_router(health_router)
    app.include_router(events_router)
    app.include_router(feishu_router)
    app.include_router(memory_router)
    app.include_router(proactive_router)
    app.include_router(profile_router)
    return app


app = create_app()
