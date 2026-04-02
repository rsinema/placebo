"""Tests for the telegram_handler module."""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test_token")
os.environ.setdefault("MOONSHOT_API_KEY", "test_key")
os.environ.setdefault("DATABASE_URL", "postgresql://localhost/test")


class TestTriggerCheckin:
    """Tests for trigger_checkin function."""

    @pytest.fixture(autouse=True)
    def reset_state(self):
        """Reset the state store before each test."""
        import placebo_bot.telegram_handler

        placebo_bot.telegram_handler._state_store = {}
        yield
        placebo_bot.telegram_handler._state_store = {}

    @pytest.mark.asyncio
    async def test_trigger_checkin_sends_message(self):
        """Test that trigger_checkin sends a message when checkin is started."""
        mock_result = {
            "response_text": "Test checkin message",
            "checkin_active": True,
            "checkin_metrics": [{"id": "1", "name": "test_metric"}],
            "checkin_current_index": 0,
            "checkin_responses": [],
        }

        with patch(
            "placebo_bot.agent.nodes.start_checkin", new_callable=AsyncMock
        ) as mock_start:
            mock_start.return_value = mock_result

            chat_id = 12345678
            send_fn = AsyncMock()

            from placebo_bot.telegram_handler import trigger_checkin

            await trigger_checkin(chat_id, send_fn)

            send_fn.assert_called_once_with(chat_id, "Test checkin message")

    @pytest.mark.asyncio
    async def test_trigger_checkin_does_not_send_when_no_response_text(self):
        """Test that trigger_checkin doesn't send when response_text is empty."""
        with patch(
            "placebo_bot.agent.nodes.start_checkin", new_callable=AsyncMock
        ) as mock_start:
            mock_start.return_value = {
                "response_text": "",
                "checkin_active": False,
            }

            chat_id = 99999999
            send_fn = AsyncMock()

            from placebo_bot.telegram_handler import trigger_checkin

            await trigger_checkin(chat_id, send_fn)

            send_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_trigger_checkin_creates_state_for_new_chat_id(self):
        """Test that trigger_checkin creates state if it doesn't exist for chat_id."""
        import placebo_bot.telegram_handler

        with patch(
            "placebo_bot.agent.nodes.start_checkin", new_callable=AsyncMock
        ) as mock_start:
            mock_start.return_value = {
                "response_text": "Hello!",
                "checkin_active": False,
            }

            chat_id = 55555555
            send_fn = AsyncMock()

            assert chat_id not in placebo_bot.telegram_handler._state_store

            from placebo_bot.telegram_handler import trigger_checkin

            await trigger_checkin(chat_id, send_fn)

            assert chat_id in placebo_bot.telegram_handler._state_store

    @pytest.mark.asyncio
    async def test_trigger_checkin_updates_state(self):
        """Test that trigger_checkin updates state with result."""
        import placebo_bot.telegram_handler

        with patch(
            "placebo_bot.agent.nodes.start_checkin", new_callable=AsyncMock
        ) as mock_start:
            mock_start.return_value = {
                "response_text": "Check-in started!",
                "checkin_active": True,
                "checkin_metrics": [{"id": "2", "name": "mood"}],
                "checkin_current_index": 0,
                "checkin_responses": [],
            }

            chat_id = 66666666
            send_fn = AsyncMock()

            from placebo_bot.telegram_handler import trigger_checkin

            await trigger_checkin(chat_id, send_fn)

            state = placebo_bot.telegram_handler._state_store.get(chat_id)
            assert state["checkin_active"] is True
            assert len(state["checkin_metrics"]) == 1


class TestGetState:
    """Tests for _get_state function."""

    @pytest.fixture(autouse=True)
    def reset_state(self):
        """Reset the state store before each test."""
        import placebo_bot.telegram_handler

        placebo_bot.telegram_handler._state_store = {}
        yield
        placebo_bot.telegram_handler._state_store = {}

    def test_get_state_creates_new_state_with_defaults(self):
        """Test that _get_state creates new state with correct defaults."""
        from placebo_bot.telegram_handler import _get_state

        chat_id = 11111111
        state = _get_state(chat_id)

        assert state["chat_id"] == chat_id
        assert state["checkin_active"] is False
        assert state["messages"] == []
        assert state["checkin_metrics"] == []
        assert state["checkin_current_index"] == 0
        assert state["checkin_responses"] == []
        assert state["pending_metric"] is None
        assert state["response_text"] == ""

    def test_get_state_returns_existing_state(self):
        """Test that _get_state returns same state for same chat_id."""
        from placebo_bot.telegram_handler import _get_state

        chat_id = 22222222
        state1 = _get_state(chat_id)
        state1["custom_field"] = "test"

        state2 = _get_state(chat_id)

        assert state2 is state1
        assert state2["custom_field"] == "test"


class TestUpdateState:
    """Tests for _update_state function."""

    @pytest.fixture(autouse=True)
    def reset_state(self):
        """Reset the state store before each test."""
        import placebo_bot.telegram_handler

        placebo_bot.telegram_handler._state_store = {}
        yield
        placebo_bot.telegram_handler._state_store = {}

    def test_update_state_updates_existing_fields(self):
        """Test that _update_state updates existing fields."""
        from placebo_bot.telegram_handler import _get_state, _update_state

        chat_id = 33333333
        _get_state(chat_id)

        _update_state(chat_id, {"checkin_active": True, "response_text": "updated"})

        state = _get_state(chat_id)
        assert state["checkin_active"] is True
        assert state["response_text"] == "updated"

    def test_update_state_creates_state_if_not_exists(self):
        """Test that _update_state creates state if it doesn't exist."""
        from placebo_bot.telegram_handler import _get_state, _update_state

        chat_id = 44444444

        _update_state(chat_id, {"checkin_active": True})

        state = _get_state(chat_id)
        assert state["checkin_active"] is True


class TestMdToHtml:
    """Tests for _md_to_html function."""

    def test_md_to_html_converts_bold(self):
        """Test conversion of **bold** to <b>bold</b>."""
        from placebo_bot.telegram_handler import _md_to_html

        result = _md_to_html("This is **bold** text")
        assert result == "This is <b>bold</b> text"

    def test_md_to_html_handles_multiple_bold(self):
        """Test multiple bold sections."""
        from placebo_bot.telegram_handler import _md_to_html

        result = _md_to_html("**one** and **two**")
        assert result == "<b>one</b> and <b>two</b>"

    def test_md_to_html_preserves_non_bold(self):
        """Test that non-bold text is preserved."""
        from placebo_bot.telegram_handler import _md_to_html

        result = _md_to_html("plain text without bold")
        assert result == "plain text without bold"


class TestTriggerCheckinEdgeCases:
    """Edge case tests for trigger_checkin."""

    @pytest.fixture(autouse=True)
    def reset_state(self):
        """Reset the state store before each test."""
        import placebo_bot.telegram_handler

        placebo_bot.telegram_handler._state_store = {}
        yield
        placebo_bot.telegram_handler._state_store = {}

    @pytest.mark.asyncio
    async def test_trigger_checkin_with_no_metrics_message(self):
        """Test trigger_checkin when start_checkin returns 'no metrics' message."""
        with patch(
            "placebo_bot.agent.nodes.start_checkin", new_callable=AsyncMock
        ) as mock_start:
            mock_start.return_value = {
                "response_text": "You don't have any active metrics yet. Try adding one with something like 'add a metric for sleep quality'.",
                "checkin_active": False,
            }

            chat_id = 12345678
            send_fn = AsyncMock()

            from placebo_bot.telegram_handler import trigger_checkin

            await trigger_checkin(chat_id, send_fn)

            send_fn.assert_called_once()
            call_args = send_fn.call_args[0]
            assert call_args[0] == chat_id
            assert "active metrics" in call_args[1]

    @pytest.mark.asyncio
    async def test_trigger_checkin_preserves_existing_state(self):
        """Test that trigger_checkin doesn't overwrite unrelated state fields."""
        import placebo_bot.telegram_handler

        chat_id = 77777777
        placebo_bot.telegram_handler._state_store[chat_id] = {
            "messages": ["old message"],
            "intent": "old_intent",
            "chat_id": chat_id,
            "checkin_active": False,
            "checkin_metrics": [],
            "checkin_current_index": 0,
            "checkin_responses": [],
            "pending_metric": None,
            "response_text": "",
        }

        with patch(
            "placebo_bot.agent.nodes.start_checkin", new_callable=AsyncMock
        ) as mock_start:
            mock_start.return_value = {
                "response_text": "New checkin!",
                "checkin_active": True,
                "checkin_metrics": [{"id": "1", "name": "test"}],
                "checkin_current_index": 0,
                "checkin_responses": [],
            }

            send_fn = AsyncMock()

            from placebo_bot.telegram_handler import trigger_checkin

            await trigger_checkin(chat_id, send_fn)

            state = placebo_bot.telegram_handler._state_store.get(chat_id)
            assert state["messages"] == ["old message"]


class TestScheduledCheckinFlow:
    """Integration tests for the scheduled checkin flow."""

    @pytest.fixture(autouse=True)
    def reset_state(self):
        """Reset the state store before each test."""
        import placebo_bot.telegram_handler

        placebo_bot.telegram_handler._state_store = {}
        yield
        placebo_bot.telegram_handler._state_store = {}

    @pytest.mark.asyncio
    async def test_scheduled_checkin_flow_with_metrics(self):
        """Test the full scheduled checkin flow when metrics exist."""
        captured_send_fn = None
        captured_chat_id = None

        async def capture_send_fn(cid, text):
            nonlocal captured_send_fn, captured_chat_id
            captured_send_fn = text
            captured_chat_id = cid

        with patch(
            "placebo_bot.agent.nodes.start_checkin", new_callable=AsyncMock
        ) as mock_start:
            mock_start.return_value = {
                "response_text": "Let's do your check-in! (2 questions)\n\nHow did you sleep?",
                "checkin_active": True,
                "checkin_metrics": [
                    {
                        "id": "1",
                        "name": "sleep",
                        "question_prompt": "How did you sleep?",
                    },
                    {"id": "2", "name": "mood", "question_prompt": "How's your mood?"},
                ],
                "checkin_current_index": 0,
                "checkin_responses": [],
            }

            from placebo_bot.telegram_handler import trigger_checkin

            await trigger_checkin(12345678, capture_send_fn)

            assert captured_chat_id == 12345678
            assert "check-in" in captured_send_fn

    @pytest.mark.asyncio
    async def test_scheduled_checkin_flow_without_metrics(self):
        """Test the full scheduled checkin flow when no metrics exist."""
        captured_send_fn = None
        captured_chat_id = None

        async def capture_send_fn(cid, text):
            nonlocal captured_send_fn, captured_chat_id
            captured_send_fn = text
            captured_chat_id = cid

        with patch(
            "placebo_bot.agent.nodes.start_checkin", new_callable=AsyncMock
        ) as mock_start:
            mock_start.return_value = {
                "response_text": "You don't have any active metrics yet. Try adding one with something like 'add a metric for sleep quality'.",
                "checkin_active": False,
            }

            from placebo_bot.telegram_handler import trigger_checkin

            await trigger_checkin(12345678, capture_send_fn)

            assert captured_chat_id == 12345678
            assert "active metrics" in captured_send_fn
