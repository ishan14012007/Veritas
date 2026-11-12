import logging
from typing import Any, Dict
from arq.connections import RedisSettings
from app.core.config import get_settings

logger = logging.getLogger(__name__)


async def sample_task(ctx: Dict[Any, Any], message: str) -> str:
    """Sample background task for testing ARQ queue infrastructure."""
    logger.info(f"Processing background task with message: {message}")
    return f"Processed: {message}"


async def analyze_conversation_task(
    ctx: Dict[Any, Any],
    conversation_id_str: str,
    user_id_str: str,
    analysis_id_str: str | None = None,
) -> str:
    """ARQ background task for asynchronous Gemini conversation analysis."""
    import uuid
    import app.payments.models  # Ensure payment models are registered with SQLAlchemy
    import app.whatsapp.models  # Ensure whatsapp models are registered with SQLAlchemy
    from app.core.database import get_session_factory
    from app.accord.services.analyzer import ConversationAnalyzerService

    conv_id = uuid.UUID(conversation_id_str)
    user_id = uuid.UUID(user_id_str)
    analysis_id = uuid.UUID(analysis_id_str) if analysis_id_str else None

    factory = get_session_factory()
    try:
        async with factory() as session:
            analysis = await ConversationAnalyzerService.execute_analysis(
                db=session,
                conversation_id=conv_id,
                user_id=user_id,
                analysis_id=analysis_id,
            )
            return str(analysis.id)
    except Exception as exc:
        logger.error(f"Error executing analyze_conversation_task: {exc}", exc_info=True)
        if analysis_id:
            try:
                from app.accord.models import ConversationAnalysis
                async with factory() as err_session:
                    rec = await err_session.get(ConversationAnalysis, analysis_id)
                    if rec and rec.status in ("PROCESSING", "QUEUED"):
                        rec.status = "FAILED"
                        rec.error_message = f"Task failure: {exc}"
                        await err_session.commit()
            except Exception:
                pass
        raise


async def process_whatsapp_inbound_task(
    ctx: Dict[Any, Any],
    event_id_str: str,
    trigger_analysis: bool = False,
) -> str:
    """ARQ background task for asynchronous inbound WhatsApp webhook processing."""
    import uuid
    import app.whatsapp.models
    from app.core.database import get_session_factory
    from app.whatsapp.service import WhatsAppService

    event_id = uuid.UUID(event_id_str)
    factory = get_session_factory()
    async with factory() as session:
        messages = await WhatsAppService.process_webhook_event(
            db=session,
            event_id=event_id,
            trigger_analysis=trigger_analysis,
        )
        return f"Processed {len(messages)} WhatsApp messages from event {event_id_str}"


async def send_whatsapp_outbound_task(
    ctx: Dict[Any, Any],
    recipient_number: str,
    content: str,
    message_type: str = "TEXT",
    template_name: str | None = None,
    conversation_id_str: str | None = None,
) -> str:
    """ARQ background task for asynchronous outbound WhatsApp message dispatch."""
    import uuid
    import app.whatsapp.models
    from app.core.database import get_session_factory
    from app.whatsapp.service import WhatsAppService

    conv_id = uuid.UUID(conversation_id_str) if conversation_id_str else None
    factory = get_session_factory()
    async with factory() as session:
        msg = await WhatsAppService.send_message(
            db=session,
            recipient_number=recipient_number,
            content=content,
            message_type=message_type,
            template_name=template_name,
            conversation_id=conv_id,
        )
        return str(msg.id)


async def on_startup(ctx: Dict[Any, Any]) -> None:
    """Invoked when ARQ worker process starts up."""
    logger.info("ARQ background worker initialized and listening for jobs.")


async def on_shutdown(ctx: Dict[Any, Any]) -> None:
    """Invoked when ARQ worker process terminates."""
    logger.info("ARQ background worker shutting down.")


async def on_job_end(ctx: Dict[Any, Any]) -> None:
    """Custom Failure & Dead-Letter Recording Hook.
    ARQ does not provide a native Dead Letter Queue. When job retries are
    exhausted, this hook captures the terminal failure, logs it, and pushes
    the job metadata to a Redis dead-letter stream for audit and inspection.
    """
    job_id = ctx.get("job_id")
    job_try = ctx.get("job_try", 1)
    max_tries = 3

    if job_try >= max_tries:
        redis = ctx.get("redis")
        if redis:
            try:
                await redis.xadd(
                    "veritas:arq:dead_letter_queue",
                    {
                        "job_id": str(job_id),
                        "attempts": str(job_try),
                        "status": "RETRY_EXHAUSTED",
                    },
                )
                logger.warning(f"Job {job_id} exceeded max retries and was moved to dead_letter_queue.")
            except Exception as e:
                logger.error(f"Failed to record dead-letter job {job_id}: {e}")


class WorkerSettings:
    """ARQ Worker configuration settings."""

    settings = get_settings()

    # Parse Redis connection string from settings
    functions = [
        sample_task,
        analyze_conversation_task,
        process_whatsapp_inbound_task,
        send_whatsapp_outbound_task,
    ]
    on_startup = on_startup
    on_shutdown = on_shutdown
    on_job_end = on_job_end

    max_tries = 3
    job_timeout = 60  # seconds

    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)

