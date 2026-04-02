"""Tests for the scheduler module."""

import asyncio
import os
import sys
from datetime import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test_token")
os.environ.setdefault("MOONSHOT_API_KEY", "test_key")
os.environ.setdefault("DATABASE_URL", "postgresql://localhost/test")


class MockJob:
    def __init__(self, name: str = "daily_checkin"):
        self._name = name
        self._removed = False

    def schedule_removal(self):
        self._removed = True


class MockJobQueue:
    def __init__(self):
        self.jobs = []
        self.scheduled_times = []

    def get_jobs_by_name(self, name: str):
        return [j for j in self.jobs if j._name == name and not j._removed]

    def run_daily(self, callback, time: time, name: str):
        self.scheduled_times.append(time)
        job = MockJob(name)
        self.jobs.append(job)
        return job


class MockBot:
    def __init__(self):
        self.sent_messages = []

    async def send_message(self, chat_id: int, text: str, parse_mode: str = None):
        self.sent_messages.append(
            {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
        )


class MockContext:
    def __init__(self):
        self.bot = MockBot()
        self.job_queue = MockJobQueue()


mock_send_fn = None


async def mock_trigger_checkin(chat_id: int, send_fn):
    global mock_send_fn
    mock_send_fn = send_fn
    await send_fn(chat_id, "Mocked checkin message")


class TestScheduleCheckin:
    """Tests for schedule_checkin function."""

    def test_schedule_checkin_creates_job(self):
        """Test that schedule_checkin creates a daily job."""
        app = MagicMock()
        app.job_queue = MockJobQueue()

        with patch.dict(
            sys.modules,
            {
                "placebo_bot.telegram_handler": MagicMock(),
                "placebo_bot.db": MagicMock(),
                "placebo_bot.agent.nodes": MagicMock(),
                "placebo_bot.agent.graph": MagicMock(),
                "placebo_bot.agent.state": MagicMock(),
                "placebo_bot.agent.prompts": MagicMock(),
                "placebo_bot.models": MagicMock(),
                "placebo_bot.config": MagicMock(),
            },
        ):
            with patch("placebo_bot.scheduler.db") as mock_db:
                mock_db.get_bot_setting = AsyncMock(return_value=None)

                from placebo_bot.scheduler import schedule_checkin

                schedule_checkin(app, hour=14, minute=30)

                jobs = app.job_queue.get_jobs_by_name("daily_checkin")
                assert len(jobs) == 1

    def test_schedule_checkin_removes_existing_jobs(self):
        """Test that schedule_checkin removes existing jobs before adding new one."""
        app = MagicMock()
        app.job_queue = MockJobQueue()

        with patch.dict(
            sys.modules,
            {
                "placebo_bot.telegram_handler": MagicMock(),
                "placebo_bot.db": MagicMock(),
                "placebo_bot.agent.nodes": MagicMock(),
                "placebo_bot.agent.graph": MagicMock(),
                "placebo_bot.agent.state": MagicMock(),
                "placebo_bot.agent.prompts": MagicMock(),
                "placebo_bot.models": MagicMock(),
                "placebo_bot.config": MagicMock(),
            },
        ):
            with patch("placebo_bot.scheduler.db") as mock_db:
                mock_db.get_bot_setting = AsyncMock(return_value=None)

                from placebo_bot.scheduler import schedule_checkin

                schedule_checkin(app, hour=10, minute=0)
                assert len(app.job_queue.get_jobs_by_name("daily_checkin")) == 1

                schedule_checkin(app, hour=14, minute=0)
                assert len(app.job_queue.get_jobs_by_name("daily_checkin")) == 1

    def test_schedule_time_is_correct(self):
        """Test that the scheduled time matches the input parameters."""
        app = MagicMock()
        app.job_queue = MockJobQueue()

        test_cases = [(0, 0), (12, 30), (14, 0), (23, 59)]

        with patch.dict(
            sys.modules,
            {
                "placebo_bot.telegram_handler": MagicMock(),
                "placebo_bot.db": MagicMock(),
                "placebo_bot.agent.nodes": MagicMock(),
                "placebo_bot.agent.graph": MagicMock(),
                "placebo_bot.agent.state": MagicMock(),
                "placebo_bot.agent.prompts": MagicMock(),
                "placebo_bot.models": MagicMock(),
                "placebo_bot.config": MagicMock(),
            },
        ):
            with patch("placebo_bot.scheduler.db") as mock_db:
                mock_db.get_bot_setting = AsyncMock(return_value=None)

                from placebo_bot.scheduler import schedule_checkin

                for hour, minute in test_cases:
                    app.job_queue = MockJobQueue()
                    schedule_checkin(app, hour=hour, minute=minute)

                    assert len(app.job_queue.scheduled_times) == 1
                    assert app.job_queue.scheduled_times[0].hour == hour
                    assert app.job_queue.scheduled_times[0].minute == minute


class TestDailyCheckinJob:
    """Tests for _daily_checkin_job function."""

    @pytest.mark.asyncio
    async def test_job_sends_message_when_chat_id_exists(self):
        """Test that job sends message when chat_id is configured."""
        mock_db = MagicMock()
        mock_db.get_bot_setting = AsyncMock(return_value="12345678")

        context = MockContext()

        with patch.dict(
            sys.modules,
            {
                "placebo_bot.telegram_handler": MagicMock(),
                "placebo_bot.db": MagicMock(),
                "placebo_bot.agent.nodes": MagicMock(),
                "placebo_bot.agent.graph": MagicMock(),
                "placebo_bot.agent.state": MagicMock(),
                "placebo_bot.agent.prompts": MagicMock(),
                "placebo_bot.models": MagicMock(),
                "placebo_bot.config": MagicMock(),
            },
        ):
            with patch("placebo_bot.scheduler.db", mock_db):
                with patch(
                    "placebo_bot.scheduler.trigger_checkin", new_callable=AsyncMock
                ) as mock_trigger:
                    mock_trigger.side_effect = mock_trigger_checkin

                    from placebo_bot.scheduler import _daily_checkin_job

                    await _daily_checkin_job(context)

                    mock_trigger.assert_called_once()

    @pytest.mark.asyncio
    async def test_job_skips_when_no_chat_id(self):
        """Test that job skips when no chat_id is configured."""
        mock_db = MagicMock()
        mock_db.get_bot_setting = AsyncMock(return_value=None)

        context = MockContext()

        with patch.dict(
            sys.modules,
            {
                "placebo_bot.telegram_handler": MagicMock(),
                "placebo_bot.db": MagicMock(),
                "placebo_bot.agent.nodes": MagicMock(),
                "placebo_bot.agent.graph": MagicMock(),
                "placebo_bot.agent.state": MagicMock(),
                "placebo_bot.agent.prompts": MagicMock(),
                "placebo_bot.models": MagicMock(),
                "placebo_bot.config": MagicMock(),
            },
        ):
            with patch("placebo_bot.scheduler.db", mock_db):
                with patch(
                    "placebo_bot.scheduler.trigger_checkin", new_callable=AsyncMock
                ) as mock_trigger:
                    from placebo_bot.scheduler import _daily_checkin_job

                    await _daily_checkin_job(context)

                    mock_trigger.assert_not_called()

    @pytest.mark.asyncio
    async def test_job_converts_string_chat_id_to_int(self):
        """Test that job converts string chat_id to int."""
        mock_db = MagicMock()
        mock_db.get_bot_setting = AsyncMock(return_value="98765432")

        context = MockContext()

        captured_chat_id = None

        async def capture_trigger(chat_id, send_fn):
            nonlocal captured_chat_id
            captured_chat_id = chat_id

        with patch.dict(
            sys.modules,
            {
                "placebo_bot.telegram_handler": MagicMock(),
                "placebo_bot.db": MagicMock(),
                "placebo_bot.agent.nodes": MagicMock(),
                "placebo_bot.agent.graph": MagicMock(),
                "placebo_bot.agent.state": MagicMock(),
                "placebo_bot.agent.prompts": MagicMock(),
                "placebo_bot.models": MagicMock(),
                "placebo_bot.config": MagicMock(),
            },
        ):
            with patch("placebo_bot.scheduler.db", mock_db):
                with patch(
                    "placebo_bot.scheduler.trigger_checkin", new_callable=AsyncMock
                ) as mock_trigger:
                    mock_trigger.side_effect = capture_trigger

                    from placebo_bot.scheduler import _daily_checkin_job

                    await _daily_checkin_job(context)

                    assert captured_chat_id == 98765432
                    assert isinstance(captured_chat_id, int)


class TestSendFnBehavior:
    """Tests for the send_fn behavior in scheduled jobs."""

    @pytest.mark.asyncio
    async def test_send_fn_sends_to_correct_chat_id(self):
        """Test that send_fn sends message to the correct chat_id."""
        mock_db = MagicMock()
        mock_db.get_bot_setting = AsyncMock(return_value="55555555")

        context = MockContext()

        with patch.dict(
            sys.modules,
            {
                "placebo_bot.telegram_handler": MagicMock(),
                "placebo_bot.db": MagicMock(),
                "placebo_bot.agent.nodes": MagicMock(),
                "placebo_bot.agent.graph": MagicMock(),
                "placebo_bot.agent.state": MagicMock(),
                "placebo_bot.agent.prompts": MagicMock(),
                "placebo_bot.models": MagicMock(),
                "placebo_bot.config": MagicMock(),
            },
        ):
            with patch("placebo_bot.scheduler.db", mock_db):
                with patch(
                    "placebo_bot.scheduler.trigger_checkin", new_callable=AsyncMock
                ) as mock_trigger:

                    async def trigger_side_effect(chat_id, send_fn):
                        await send_fn(chat_id, "Test message")

                    mock_trigger.side_effect = trigger_side_effect

                    from placebo_bot.scheduler import _daily_checkin_job

                    await _daily_checkin_job(context)

                    assert len(context.bot.sent_messages) == 1
                    assert context.bot.sent_messages[0]["chat_id"] == 55555555

    @pytest.mark.asyncio
    async def test_send_fn_uses_markdown_parse_mode(self):
        """Test that send_fn uses Markdown parse mode."""
        mock_db = MagicMock()
        mock_db.get_bot_setting = AsyncMock(return_value="11111111")

        context = MockContext()

        with patch.dict(
            sys.modules,
            {
                "placebo_bot.telegram_handler": MagicMock(),
                "placebo_bot.db": MagicMock(),
                "placebo_bot.agent.nodes": MagicMock(),
                "placebo_bot.agent.graph": MagicMock(),
                "placebo_bot.agent.state": MagicMock(),
                "placebo_bot.agent.prompts": MagicMock(),
                "placebo_bot.models": MagicMock(),
                "placebo_bot.config": MagicMock(),
            },
        ):
            with patch("placebo_bot.scheduler.db", mock_db):
                with patch(
                    "placebo_bot.scheduler.trigger_checkin", new_callable=AsyncMock
                ) as mock_trigger:

                    async def trigger_side_effect(chat_id, send_fn):
                        await send_fn(chat_id, "Test **bold** message")

                    mock_trigger.side_effect = trigger_side_effect

                    from placebo_bot.scheduler import _daily_checkin_job

                    await _daily_checkin_job(context)

                    assert len(context.bot.sent_messages) == 1
                    assert context.bot.sent_messages[0]["parse_mode"] == "Markdown"


class TestFullScheduledJobFlow:
    """Integration tests for the full scheduled job flow."""

    @pytest.mark.asyncio
    async def test_job_runs_and_sends_message(self):
        """Test that the scheduled job runs and sends a message."""
        mock_db = MagicMock()
        mock_db.get_bot_setting = AsyncMock(return_value="12345678")

        context = MockContext()

        with patch.dict(
            sys.modules,
            {
                "placebo_bot.telegram_handler": MagicMock(),
                "placebo_bot.db": MagicMock(),
                "placebo_bot.agent.nodes": MagicMock(),
                "placebo_bot.agent.graph": MagicMock(),
                "placebo_bot.agent.state": MagicMock(),
                "placebo_bot.agent.prompts": MagicMock(),
                "placebo_bot.models": MagicMock(),
                "placebo_bot.config": MagicMock(),
            },
        ):
            with patch("placebo_bot.scheduler.db", mock_db):
                with patch(
                    "placebo_bot.scheduler.trigger_checkin", new_callable=AsyncMock
                ) as mock_trigger:

                    async def full_flow(chat_id, send_fn):
                        await send_fn(chat_id, "Your daily check-in is ready!")

                    mock_trigger.side_effect = full_flow

                    from placebo_bot.scheduler import _daily_checkin_job

                    await _daily_checkin_job(context)

                    mock_trigger.assert_called_once()
                    call_args = mock_trigger.call_args[0]
                    assert call_args[0] == 12345678

    @pytest.mark.asyncio
    async def test_job_handles_missing_chat_id_gracefully(self):
        """Test that job handles missing chat_id without crashing."""
        mock_db = MagicMock()
        mock_db.get_bot_setting = AsyncMock(return_value=None)

        context = MockContext()

        with patch.dict(
            sys.modules,
            {
                "placebo_bot.telegram_handler": MagicMock(),
                "placebo_bot.db": MagicMock(),
                "placebo_bot.agent.nodes": MagicMock(),
                "placebo_bot.agent.graph": MagicMock(),
                "placebo_bot.agent.state": MagicMock(),
                "placebo_bot.agent.prompts": MagicMock(),
                "placebo_bot.models": MagicMock(),
                "placebo_bot.config": MagicMock(),
            },
        ):
            with patch("placebo_bot.scheduler.db", mock_db):
                with patch(
                    "placebo_bot.scheduler.trigger_checkin", new_callable=AsyncMock
                ) as mock_trigger:
                    from placebo_bot.scheduler import _daily_checkin_job

                    await _daily_checkin_job(context)

                    mock_trigger.assert_not_called()
                    assert len(context.bot.sent_messages) == 0
