import logging
from datetime import time

from telegram.ext import Application

from placebo_analytics.charts import (
    metric_time_series,
)
from placebo_analytics.agent.prompts import GENERATE_DIGEST_NARRATIVE
from placebo_analytics.agent.nodes import _llm_general, _parse_json

logger = logging.getLogger(__name__)


async def _weekly_digest_job(context) -> None:
    """Job callback: send weekly digest to the stored analytics_chat_id."""
    from placebo_analytics import db as analytics_db

    chat_id_str = await analytics_db.get_bot_setting("analytics_chat_id")
    if not chat_id_str:
        logger.warning("No analytics_chat_id configured — skipping digest.")
        return

    chat_id = int(chat_id_str)

    try:
        metrics = await analytics_db.get_active_metrics()
        if not metrics:
            await context.bot.send_message(
                chat_id=chat_id,
                text="📊 *Weekly Digest*\n\nNo active metrics to analyze yet.",
                parse_mode="Markdown",
            )
            return

        metric_ids = [m.id for m in metrics]
        summaries = await analytics_db.get_multi_metric_summary(metric_ids, days=7)

        # Generate time series charts per metric
        chart_bytes_list: list[bytes] = []
        for metric in metrics:
            if metric.response_type == "numeric":
                rolling = await analytics_db.get_rolling_avg(metric.id, days=14)
                if rolling:
                    img_bytes = metric_time_series(metric, rolling)
                    chart_bytes_list.append(img_bytes)

        # Active experiments
        active_exps = await analytics_db.get_active_experiments()
        experiment_status = ""
        if active_exps:
            exp_names = ", ".join(f"**{e.name}**" for e in active_exps)
            experiment_status = f"Active experiments: {exp_names}\n"
        else:
            experiment_status = "No active experiments.\n"

        # Top correlations
        pairs = await analytics_db.get_all_numeric_metric_pairs(days=7)
        correlation_top = ""
        if len(pairs) >= 2:
            # Simple Pearson computation for top pairs
            try:
                from collections import defaultdict
                import statistics

                pair_data: dict[tuple, list] = defaultdict(list)
                for row in pairs:
                    key = (row["metric_a_id"], row["metric_b_id"])
                    pair_data[key].append((row["value_a"], row["value_b"]))

                correlations = []
                for (id_a, id_b), data in pair_data.items():
                    if len(data) >= 3:
                        vals_a = [d[0] for d in data]
                        vals_b = [d[1] for d in data]
                        try:
                            r = statistics.correlation(vals_a, vals_b)
                            correlations.append((abs(r), r, data[0]))
                        except Exception:
                            pass

                correlations.sort(reverse=True)
                if correlations[:2]:
                    lines = []
                    for abs_r, r, (val_a, val_b) in correlations[:2]:
                        for row in pairs:
                            if row["value_a"] == val_a and row["value_b"] == val_b:
                                lines.append(
                                    f"• {row['metric_a_name']} ↔ {row['metric_b_name']}: r={r:.2f}"
                                )
                                break
                    correlation_top = "Top correlations this week:\n" + "\n".join(lines) + "\n"
            except Exception:
                correlation_top = ""

        # LLM narrative
        narrative = ""
        try:
            prompt = GENERATE_DIGEST_NARRATIVE.format(
                summaries=repr(summaries),
                experiment_status=experiment_status,
                correlation_top=correlation_top,
            )
            resp = await _llm_general.ainvoke([__import__("langchain_core.messages").HumanMessage(content=prompt)])
            narrative = _parse_json(resp.content).get("narrative", "")
        except Exception as e:
            logger.warning("Failed to generate digest narrative: %s", e)
            narrative = ""

        # Send text intro
        intro = f"📊 *Weekly Digest* — week ending today\n\n{experiment_status}{correlation_top}"
        if narrative:
            intro += f"\n{narrative}"

        try:
            await context.bot.send_message(chat_id=chat_id, text=intro, parse_mode="Markdown")
        except Exception:
            await context.bot.send_message(chat_id=chat_id, text="📊 Weekly Digest — some charts and data are on the way!")

        # Send charts as media group (album)
        if chart_bytes_list:
            from io import BytesIO
            from telegram import InputFile

            # Telegram allows max 10 in a media group
            for i in range(0, min(len(chart_bytes_list), 10), 2):
                batch = chart_bytes_list[i : i + 2]
                media = [
                    {"type": "photo", "media": InputFile(BytesIO(cb), filename=f"chart_{j}.png")}
                    for j, cb in enumerate(batch, start=i)
                ]
                try:
                    await context.bot.send_media_group(chat_id=chat_id, media=media)
                except Exception:
                    # Fallback: send individually
                    for cb in batch:
                        bio = BytesIO(cb)
                        bio.name = "chart.png"
                        await context.bot.send_photo(chat_id=chat_id, photo=InputFile(bio, filename="chart.png"))

    except Exception:
        logger.exception("Weekly digest job failed")
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text="📊 Weekly digest generation failed. I'll try again next week!",
            )
        except Exception:
            pass


def schedule_digest(app: Application, day: int, hour: int, minute: int) -> None:
    """Schedule the weekly digest job — fires once per week on the given day."""
    job_queue = app.job_queue

    existing = job_queue.get_jobs_by_name("weekly_digest")
    for job in existing:
        job.schedule_removal()

    job_queue.run_daily(
        _weekly_digest_job,
        time=time(hour=hour, minute=minute),
        days=(day,),  # tuple of weekdays: 0=Monday, 6=Sunday
        name="weekly_digest",
    )
    logger.info("Scheduled weekly digest on day %d at %02d:%02d UTC", day, hour, minute)
