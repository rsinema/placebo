"""Tests for gym_bot agent nodes — LLM and DB are mocked."""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

os.environ.setdefault("GYM_TELEGRAM_BOT_TOKEN", "test_token")
os.environ.setdefault("MOONSHOT_API_KEY", "test_key")
os.environ.setdefault("DATABASE_URL", "postgresql://localhost/test")


def _msg_state(text: str, **extra) -> dict:
    return {
        "messages": [SimpleNamespace(content=text)],
        "intent": "",
        "chat_id": 1,
        "last_log_group_id": None,
        "response_text": "",
        **extra,
    }


class TestClassifyIntent:
    @pytest.mark.asyncio
    async def test_classifies_log_workout(self):
        from placebo_gym.agent import nodes

        with patch.object(nodes, "_llm") as mock_llm:
            mock_llm.ainvoke = AsyncMock(
                return_value=SimpleNamespace(content='{"intent": "log_workout"}')
            )
            result = await nodes.classify_intent(_msg_state("squat 3x5 225"))
            assert result == {"intent": "log_workout"}

    @pytest.mark.asyncio
    async def test_falls_back_to_general_on_bad_json(self):
        from placebo_gym.agent import nodes

        with patch.object(nodes, "_llm") as mock_llm:
            mock_llm.ainvoke = AsyncMock(
                return_value=SimpleNamespace(content="not json")
            )
            result = await nodes.classify_intent(_msg_state("hello"))
            assert result == {"intent": "general"}


class TestHandleLogWorkout:
    @pytest.mark.asyncio
    async def test_parses_per_set_weights_and_saves(self):
        from placebo_gym.agent import nodes

        llm_response = (
            '{"exercise": "squat", "sets": ['
            '{"reps": 3, "weight": 225},'
            '{"reps": 3, "weight": 235},'
            '{"reps": 3, "weight": 255}]}'
        )
        fake_exercise = SimpleNamespace(id=uuid4(), name="squat")
        fake_log_group = uuid4()

        with (
            patch.object(nodes, "_llm") as mock_llm,
            patch.object(nodes.db, "upsert_exercise", new_callable=AsyncMock) as mock_upsert,
            patch.object(nodes.db, "save_exercise_sets", new_callable=AsyncMock) as mock_save,
        ):
            mock_llm.ainvoke = AsyncMock(
                return_value=SimpleNamespace(content=llm_response)
            )
            mock_upsert.return_value = fake_exercise
            mock_save.return_value = (fake_log_group, [])

            result = await nodes.handle_log_workout(_msg_state("squat 3x3 225 235 255"))

            mock_upsert.assert_awaited_once_with("squat")
            mock_save.assert_awaited_once()
            saved_sets = mock_save.call_args.args[1]
            assert len(saved_sets) == 3
            assert saved_sets[0]["weight"] == 225
            assert saved_sets[2]["weight"] == 255
            assert result["last_log_group_id"] == fake_log_group
            assert "squat" in result["response_text"]
            assert "undo" in result["response_text"].lower()

    @pytest.mark.asyncio
    async def test_bodyweight_null_weight(self):
        from placebo_gym.agent import nodes

        llm_response = (
            '{"exercise": "pullups", "sets": ['
            '{"reps": 8, "weight": null},'
            '{"reps": 8, "weight": null},'
            '{"reps": 8, "weight": null}]}'
        )
        fake_exercise = SimpleNamespace(id=uuid4(), name="pullups")

        with (
            patch.object(nodes, "_llm") as mock_llm,
            patch.object(nodes.db, "upsert_exercise", new_callable=AsyncMock) as mock_upsert,
            patch.object(nodes.db, "save_exercise_sets", new_callable=AsyncMock) as mock_save,
        ):
            mock_llm.ainvoke = AsyncMock(
                return_value=SimpleNamespace(content=llm_response)
            )
            mock_upsert.return_value = fake_exercise
            mock_save.return_value = (uuid4(), [])

            result = await nodes.handle_log_workout(_msg_state("pullups 3x8"))

            saved_sets = mock_save.call_args.args[1]
            assert all(s["weight"] is None for s in saved_sets)
            assert "pullups" in result["response_text"]

    @pytest.mark.asyncio
    async def test_varying_reps(self):
        from placebo_gym.agent import nodes

        llm_response = (
            '{"exercise": "deadlift", "sets": ['
            '{"reps": 5, "weight": 315},'
            '{"reps": 3, "weight": 335},'
            '{"reps": 1, "weight": 365}]}'
        )
        fake_exercise = SimpleNamespace(id=uuid4(), name="deadlift")

        with (
            patch.object(nodes, "_llm") as mock_llm,
            patch.object(nodes.db, "upsert_exercise", new_callable=AsyncMock) as mock_upsert,
            patch.object(nodes.db, "save_exercise_sets", new_callable=AsyncMock) as mock_save,
        ):
            mock_llm.ainvoke = AsyncMock(
                return_value=SimpleNamespace(content=llm_response)
            )
            mock_upsert.return_value = fake_exercise
            mock_save.return_value = (uuid4(), [])

            await nodes.handle_log_workout(_msg_state("deadlift 5/3/1 315 335 365"))

            saved_sets = mock_save.call_args.args[1]
            assert [s["reps"] for s in saved_sets] == [5, 3, 1]
            assert [s["weight"] for s in saved_sets] == [315, 335, 365]

    @pytest.mark.asyncio
    async def test_unparseable_returns_help_message(self):
        from placebo_gym.agent import nodes

        with patch.object(nodes, "_llm") as mock_llm:
            mock_llm.ainvoke = AsyncMock(
                return_value=SimpleNamespace(content="not json at all")
            )
            result = await nodes.handle_log_workout(_msg_state("???"))
            assert "couldn't parse" in result["response_text"].lower()
            assert "last_log_group_id" not in result


class TestHandleUndo:
    @pytest.mark.asyncio
    async def test_undo_uses_state_log_group(self):
        from placebo_gym.agent import nodes

        log_group = uuid4()
        with (
            patch.object(nodes.db, "get_log_group_sets", new_callable=AsyncMock) as mock_get,
            patch.object(nodes.db, "delete_log_group", new_callable=AsyncMock) as mock_del,
        ):
            mock_get.return_value = [SimpleNamespace()]
            mock_del.return_value = 3

            result = await nodes.handle_undo(
                _msg_state("undo", last_log_group_id=log_group)
            )

            mock_del.assert_awaited_once_with(log_group)
            assert "removed 3" in result["response_text"].lower()
            assert result["last_log_group_id"] is None

    @pytest.mark.asyncio
    async def test_undo_falls_back_to_db_lookup(self):
        from placebo_gym.agent import nodes

        log_group = uuid4()
        with (
            patch.object(nodes.db, "get_last_log_group", new_callable=AsyncMock) as mock_last,
            patch.object(nodes.db, "get_log_group_sets", new_callable=AsyncMock) as mock_get,
            patch.object(nodes.db, "delete_log_group", new_callable=AsyncMock) as mock_del,
        ):
            mock_last.return_value = log_group
            mock_get.return_value = []
            mock_del.return_value = 1

            result = await nodes.handle_undo(_msg_state("undo"))

            mock_last.assert_awaited_once()
            mock_del.assert_awaited_once_with(log_group)
            assert "removed 1" in result["response_text"].lower()

    @pytest.mark.asyncio
    async def test_undo_with_no_sets(self):
        from placebo_gym.agent import nodes

        with patch.object(nodes.db, "get_last_log_group", new_callable=AsyncMock) as mock_last:
            mock_last.return_value = None
            result = await nodes.handle_undo(_msg_state("undo"))
            assert result["response_text"] == "Nothing to undo."


class TestFormatHelpers:
    def test_format_set_with_weight(self):
        from placebo_gym.agent.nodes import _format_set

        assert _format_set({"reps": 5, "weight": 225}) == "5@225"

    def test_format_set_bodyweight(self):
        from placebo_gym.agent.nodes import _format_set

        assert _format_set({"reps": 8, "weight": None}) == "8"

    def test_format_log_summary(self):
        from placebo_gym.agent.nodes import _format_log_summary

        sets = [{"reps": 3, "weight": 225}, {"reps": 3, "weight": 235}]
        result = _format_log_summary("bench_press", sets)
        assert "bench press" in result
        assert "3@225" in result
        assert "3@235" in result
