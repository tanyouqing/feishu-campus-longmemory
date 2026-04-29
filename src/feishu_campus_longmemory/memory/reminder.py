from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from feishu_campus_longmemory.memory.types import ReminderSchedule

DEFAULT_TIMEZONE = "Asia/Shanghai"

WEEKDAY_MAP = {
    "一": 0,
    "二": 1,
    "三": 2,
    "四": 3,
    "五": 4,
    "六": 5,
    "日": 6,
    "天": 6,
}


class ReminderParser:
    def parse(self, text: str, *, now: datetime | None = None, timezone: str = DEFAULT_TIMEZONE) -> ReminderSchedule | None:
        local_tz = ZoneInfo(timezone)
        current = now.astimezone(local_tz) if now else datetime.now(local_tz)
        reminder_text = _extract_reminder_text(text)

        weekly_match = re.search(r"每周([一二三四五六日天])", text)
        if weekly_match:
            target_weekday = WEEKDAY_MAP[weekly_match.group(1)]
            hour, minute = _extract_time(text)
            next_run_at = _next_weekday(current, target_weekday, hour, minute)
            return ReminderSchedule(
                schedule_type="weekly",
                timezone=timezone,
                next_run_at=next_run_at,
                payload_json={
                    "reminder_text": reminder_text,
                    "source_text": text,
                    "weekday": target_weekday,
                    "hour": hour,
                    "minute": minute,
                },
            )

        if "每天" in text or "每日" in text:
            hour, minute = _extract_time(text)
            next_run_at = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if next_run_at <= current:
                next_run_at += timedelta(days=1)
            return ReminderSchedule(
                schedule_type="daily",
                timezone=timezone,
                next_run_at=next_run_at,
                payload_json={
                    "reminder_text": reminder_text,
                    "source_text": text,
                    "hour": hour,
                    "minute": minute,
                },
            )

        if "明天" in text or "今天" in text:
            hour, minute = _extract_time(text)
            days = 1 if "明天" in text else 0
            next_run_at = (current + timedelta(days=days)).replace(hour=hour, minute=minute, second=0, microsecond=0)
            if next_run_at <= current:
                next_run_at += timedelta(days=1)
            return ReminderSchedule(
                schedule_type="once",
                timezone=timezone,
                next_run_at=next_run_at,
                payload_json={
                    "reminder_text": reminder_text,
                    "source_text": text,
                    "hour": hour,
                    "minute": minute,
                },
            )

        date_match = re.search(r"(\d{4}-\d{1,2}-\d{1,2})", text)
        if date_match:
            hour, minute = _extract_time(text)
            date_value = datetime.strptime(date_match.group(1), "%Y-%m-%d")
            next_run_at = datetime(
                date_value.year,
                date_value.month,
                date_value.day,
                hour,
                minute,
                tzinfo=local_tz,
            )
            return ReminderSchedule(
                schedule_type="once",
                timezone=timezone,
                next_run_at=next_run_at,
                payload_json={
                    "reminder_text": reminder_text,
                    "source_text": text,
                    "hour": hour,
                    "minute": minute,
                },
            )

        return None


def _next_weekday(current: datetime, weekday: int, hour: int, minute: int) -> datetime:
    days_ahead = (weekday - current.weekday()) % 7
    next_run_at = (current + timedelta(days=days_ahead)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    if next_run_at <= current:
        next_run_at += timedelta(days=7)
    return next_run_at


def _extract_time(text: str) -> tuple[int, int]:
    time_match = re.search(r"(\d{1,2})\s*[:：点号]\s*(\d{1,2})?", text)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or 0)
        if ("下午" in text or "晚上" in text or "晚间" in text) and hour < 12:
            hour += 12
        return hour, minute

    if "下午" in text:
        return 15, 0
    if "晚上" in text or "晚间" in text:
        return 20, 0
    return 9, 0


def _extract_reminder_text(text: str) -> str:
    marker = "提醒我"
    if marker not in text:
        return text.strip()
    after = text.split(marker, 1)[1].strip("，,。 ")
    after = re.sub(r"^(每天|每日|每周[一二三四五六日天]|今天|明天)?(上午|下午|晚上|晚间)?\d{0,2}[:：点]?\d{0,2}", "", after)
    return after.strip("，,。 ") or text.strip()

