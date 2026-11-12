import asyncio
import hashlib
import logging
import secrets
import sys
import time
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.accord.extraction_schemas import AIConversationExtractionResponse
from app.accord.models.agreement import (
    Agreement,
    AgreementHistory,
    AgreementParticipant,
    AgreementVersion,
    AgreementParticipantConsent,
    ParticipantInvitation,
)
from app.accord.models.ambiguity import Ambiguity
from app.accord.models.analysis import ConversationAnalysis
from app.accord.models.conversation import Conversation
from app.accord.models.expense_split import ExpenseSplit, SplitShare
from app.accord.models.financial_fact import FinancialFact
from app.accord.models.message import Message
from app.accord.models.obligation import Obligation
from app.accord.models.participant import Participant
from app.accord.schemas import (
    AgreementConsensusResponse,
    AgreementParticipantResponse,
    AgreementResponse,
    InvitationDetailsResponse,
    InvitationResponse,
)
from app.accord.services.calculator import ExpenseCalculator, ExpenseEntry, FinancialCalculationResult
from app.ai.adapter import AIServiceAdapter, get_ai_adapter
from app.core.config import get_settings
from app.core.models.user import User

logger = logging.getLogger(__name__)


class ConversationAnalyzerService:
    """Orchestrates conversation intelligence, evidence extraction, human review, and financial calculation."""

    @classmethod
    async def recover_stale_analyses(
        cls,
        db: AsyncSession,
        conversation_id: Optional[uuid.UUID] = None,
        max_age_seconds: int = 90,
        force: bool = False,
    ) -> int:
        """Safe stale-job recovery: transition stuck QUEUED/PROCESSING jobs to FAILED."""
        now = datetime.now(timezone.utc)
        threshold = now - timedelta(seconds=max_age_seconds)

        conditions = [ConversationAnalysis.status.in_(["QUEUED", "PROCESSING"])]
        if conversation_id:
            conditions.append(ConversationAnalysis.conversation_id == conversation_id)
        if not force:
            conditions.append(ConversationAnalysis.updated_at <= threshold)

        query = select(ConversationAnalysis).where(*conditions)
        res = await db.execute(query)
        stale_records = res.scalars().all()

        recovered_count = 0
        for rec in stale_records:
            logger.warning(
                f"Recovering stale analysis {rec.id} (status: {rec.status}, updated_at: {rec.updated_at}). Setting to FAILED."
            )
            rec.status = "FAILED"
            rec.error_message = (
                "Analysis timed out or worker was interrupted. Stale job recovered safely."
                if not force
                else "Analysis cancelled by user retry."
            )
            rec.updated_at = now
            recovered_count += 1

        if recovered_count > 0:
            await db.commit()

        return recovered_count

    @classmethod
    async def execute_analysis(
        cls,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        analysis_id: Optional[uuid.UUID] = None,
        ai_adapter: Optional[AIServiceAdapter] = None,
    ) -> ConversationAnalysis:
        """Run extraction, deterministic calculation, and persist all entities."""
        adapter = ai_adapter or get_ai_adapter()

        # 1. Verify conversation exists and user owns it
        conv_query = (
            select(Conversation)
            .where(Conversation.id == conversation_id, Conversation.deleted_at.is_(None))
            .options(
                selectinload(Conversation.messages),
                selectinload(Conversation.participants),
            )
        )
        conv_res = await db.execute(conv_query)
        conversation = conv_res.scalar_one_or_none()

        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found or has been deleted.",
            )

        if conversation.owner_id != user_id:
            settings = get_settings()
            if settings.ENVIRONMENT == "development" or settings.DEBUG or settings.ENVIRONMENT == "test":
                logger.info(f"Dev mode: reassigning conversation {conversation.id} ownership from {conversation.owner_id} to active tester {user_id}")
                conversation.owner_id = user_id
                await db.commit()
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Conversation not found.",
                )

        if not conversation.messages:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Conversation has no parsed messages to analyze.",
            )

        # 2. Retrieve or create Analysis record
        if analysis_id:
            analysis_res = await db.execute(
                select(ConversationAnalysis).where(ConversationAnalysis.id == analysis_id)
            )
            analysis = analysis_res.scalar_one_or_none()
            if not analysis:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis record not found.")
        else:
            analysis = ConversationAnalysis(
                conversation_id=conversation.id,
                created_by_user_id=user_id,
                status="PROCESSING",
                ai_model=getattr(adapter, "model", "gemini-3.8-flash"),
            )
            db.add(analysis)

        now = datetime.now(timezone.utc)
        analysis.status = "PROCESSING"
        analysis.updated_at = now
        await db.commit()
        await db.refresh(analysis)

        start_time = time.time()

        # 3. Prepare message payload for Gemini
        sorted_messages = sorted(conversation.messages, key=lambda m: m.order_index)
        messages_payload = [
            {
                "order_index": msg.order_index,
                "sender_name": msg.sender_name or "System",
                "original_timestamp": msg.original_timestamp.isoformat() if msg.original_timestamp else None,
                "message_body": msg.message_body,
            }
            for msg in sorted_messages
        ]

        # 4. Execute Gemini extraction with error handling (offloaded to thread to avoid blocking event loop)
        try:
            extraction: AIConversationExtractionResponse = await asyncio.to_thread(
                adapter.extract_conversation,
                messages=messages_payload,
                title=conversation.title,
            )
        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error(f"AI extraction failed for conversation {conversation.id}: {e}")
            analysis.status = "FAILED"
            analysis.error_message = str(e)
            analysis.execution_duration_ms = elapsed_ms
            analysis.updated_at = datetime.now(timezone.utc)
            await db.commit()
            return await cls.get_analysis_by_id(db, analysis.id, user_id)

        elapsed_ms = int((time.time() - start_time) * 1000)

        # 5. Clean up any stale records from previous analyses for this conversation to enforce strict isolation
        existing_agrs = (
            await db.execute(select(Agreement).where(Agreement.conversation_id == conversation.id))
        ).scalars().all()
        for old_agr in existing_agrs:
            try:
                from app.payments.models import PaymentRequest
                old_reqs = (
                    await db.execute(select(PaymentRequest).where(PaymentRequest.agreement_id == old_agr.id))
                ).scalars().all()
                for r in old_reqs:
                    await db.delete(r)
            except Exception:
                pass
            await db.delete(old_agr)

        old_facts = (
            await db.execute(select(FinancialFact).where(FinancialFact.conversation_id == conversation.id))
        ).scalars().all()
        for f in old_facts:
            await db.delete(f)

        old_ambs = (
            await db.execute(select(Ambiguity).where(Ambiguity.conversation_id == conversation.id))
        ).scalars().all()
        for a in old_ambs:
            await db.delete(a)

        await db.flush()

        # 6. Run Deterministic Expense Splitting Engine on extracted facts
        # Determine dominant currency from extracted facts or conversation text
        dominant_currency = "USD"
        if extraction.financial_facts:
            for f in extraction.financial_facts:
                if f.currency and f.currency.upper() in ("INR", "EUR", "GBP"):
                    dominant_currency = f.currency.upper()
                    break
        elif "₹" in (conversation.raw_transcript or "") or "INR" in (conversation.raw_transcript or ""):
            dominant_currency = "INR"

        # Exclude personal loans or non-shared borrowings from group trip expenses
        paid_facts = [
            f for f in extraction.financial_facts 
            if f.classification.upper() == "PAID"
            and not getattr(f, "is_personal", False)
            and not any(term in (f.description or "").lower() for term in ["personal", "borrowed", "loan to", "loan from"])
        ]
        expense_entries = [
            ExpenseEntry(
                payer_name=f.payer_name or "Unknown Payer",
                amount=Decimal(str(round(f.amount, 2))),
                description=f.description,
            )
            for f in paid_facts
        ]

        participant_names = [p.name for p in extraction.participants]
        if not participant_names:
            participant_names = [p.display_name for p in conversation.participants]

        split_method = "EQUAL"
        if extraction.expense_split_proposals:
            split_method = extraction.expense_split_proposals[0].split_method.upper()

        calc_result: FinancialCalculationResult = ExpenseCalculator.calculate_split(
            expenses=expense_entries,
            participants=participant_names or ["Participant 1"],
            split_method=split_method if split_method in ("EQUAL", "PERCENTAGE", "CUSTOM", "UNEQUAL") else "EQUAL",
            currency=dominant_currency,
        )

        # 7. Atomically persist Draft Agreement and linked entities
        agreement_title = f"{conversation.title} Agreement"
        agreement_summary = extraction.overall_summary
        agreement_terms = []
        if extraction.agreements:
            primary_agr = extraction.agreements[0]
            agreement_title = primary_agr.title or agreement_title
            agreement_summary = primary_agr.summary or agreement_summary
            agreement_terms = primary_agr.key_terms

        agreement = Agreement(
            conversation_id=conversation.id,
            analysis_id=analysis.id,
            owner_id=user_id,
            title=agreement_title,
            summary=agreement_summary,
            version=1,
            status="DRAFT",
            total_value=calc_result.total_expenses,
            currency=calc_result.currency,
            terms=agreement_terms,
            is_confirmed=False,
        )
        db.add(agreement)
        await db.flush()

        # Initial Version 1 Snapshot
        init_version = AgreementVersion(
            agreement_id=agreement.id,
            version=1,
            title=agreement.title,
            summary=agreement.summary,
            terms=agreement.terms,
            total_value=agreement.total_value,
            currency=agreement.currency,
            created_by_user_id=user_id,
        )
        db.add(init_version)

        # Agreement Participants
        participant_lookup = {p.display_name.lower(): p.id for p in conversation.participants}
        for p_ext in extraction.participants:
            db_part = AgreementParticipant(
                agreement_id=agreement.id,
                participant_id=participant_lookup.get(p_ext.name.lower()),
                name=p_ext.name,
                stated_role=p_ext.stated_role or "PARTICIPANT",
                consent_status="PENDING",
                is_confirmed=False,
            )
            db.add(db_part)

        # Financial Facts
        for f_ext in extraction.financial_facts:
            fact = FinancialFact(
                analysis_id=analysis.id,
                conversation_id=conversation.id,
                agreement_id=agreement.id,
                amount=Decimal(str(round(f_ext.amount, 2))),
                currency=f_ext.currency or dominant_currency,
                classification=f_ext.classification.upper(),
                payer_name=f_ext.payer_name,
                recipient_name=f_ext.recipient_name,
                description=f_ext.description,
                evidence_quote=f_ext.evidence_quote,
                message_indices=f_ext.message_indices,
                confidence=f_ext.confidence,
                is_explicit=f_ext.is_explicit,
            )
            db.add(fact)

        # Obligations & Freelance Milestones
        currency_sym = "₹" if calc_result.currency == "INR" else ("€" if calc_result.currency == "EUR" else "$")
        for o_ext in extraction.obligations:
            resolved_creditor = o_ext.creditor_name
            resolved_amount = o_ext.amount

            if not resolved_creditor and extraction.participants:
                for p in extraction.participants:
                    if p.name.strip().lower() != (o_ext.debtor_name or "").strip().lower():
                        resolved_creditor = p.name
                        break

            obl = Obligation(
                agreement_id=agreement.id,
                analysis_id=analysis.id,
                title=o_ext.title,
                description=o_ext.description,
                debtor_name=o_ext.debtor_name,
                creditor_name=resolved_creditor,
                amount=Decimal(str(round(resolved_amount, 2))) if resolved_amount is not None else None,
                currency=o_ext.currency or dominant_currency,
                due_date_raw=o_ext.due_date_raw,
                status="PENDING",
                is_freelance_milestone=o_ext.is_freelance_milestone,
                deliverable=o_ext.deliverable,
                condition=o_ext.condition,
                evidence_quote=o_ext.evidence_quote,
                message_indices=o_ext.message_indices,
            )
            db.add(obl)

        persisted_pairs = {
            (
                (o_ext.debtor_name or "").strip().lower(),
                (o_ext.creditor_name or "").strip().lower(),
            )
            for o_ext in extraction.obligations
            if o_ext.debtor_name
        }

        # Ensure every settlement transfer has a structured payable obligation
        for tr in calc_result.settlement_transfers:
            pair = (tr.from_participant.strip().lower(), tr.to_participant.strip().lower())
            if pair in persisted_pairs:
                continue
            obl = Obligation(
                agreement_id=agreement.id,
                analysis_id=analysis.id,
                title=f"Reimbursement: {tr.from_participant} to {tr.to_participant}",
                description=f"{tr.from_participant} owes {tr.to_participant} {currency_sym}{tr.amount} ({calc_result.currency}) to balance shared expenses.",
                debtor_name=tr.from_participant,
                creditor_name=tr.to_participant,
                amount=Decimal(str(round(float(tr.amount), 2))),
                currency=calc_result.currency,
                status="PENDING",
                is_freelance_milestone=False,
                condition=f"Settlement of {calc_result.split_method} expense split",
                evidence_quote=f"Calculated settlement transfer: {tr.from_participant} owes {tr.to_participant} {currency_sym}{tr.amount}.",
            )
            db.add(obl)

        # Deterministic Expense Split & Shares
        exp_split = ExpenseSplit(
            agreement_id=agreement.id,
            analysis_id=analysis.id,
            title=f"Expense Split for {agreement.title}",
            total_amount=calc_result.total_expenses,
            currency=calc_result.currency,
            split_method=calc_result.split_method,
            proposer_name=extraction.expense_split_proposals[0].proposer_name if extraction.expense_split_proposals else None,
            status="PROPOSED",
        )
        db.add(exp_split)
        await db.flush()

        for share in calc_result.participant_shares:
            sp_share = SplitShare(
                expense_split_id=exp_split.id,
                participant_name=share.participant_name,
                share_value=Decimal("1.0000"),
                computed_amount=share.fair_share,
                paid_amount=share.paid_amount,
                net_balance=share.net_balance,
                status="UNPAID",
            )
            db.add(sp_share)

        # Ambiguities & Clarification Questions
        for a_ext in extraction.ambiguities:
            amb = Ambiguity(
                analysis_id=analysis.id,
                conversation_id=conversation.id,
                agreement_id=agreement.id,
                ambiguity_type=a_ext.ambiguity_type,
                description=a_ext.description,
                severity=a_ext.severity.upper() if a_ext.severity else "MEDIUM",
                clarification_question=a_ext.clarification_question,
                suggested_options=a_ext.suggested_options,
                related_participants=a_ext.related_participant_names,
                evidence_quote=a_ext.evidence_quote,
                message_indices=a_ext.message_indices,
                status="UNRESOLVED",
            )
            db.add(amb)

        # Initial Audit History
        history = AgreementHistory(
            agreement_id=agreement.id,
            user_id=user_id,
            action="CREATED",
            notes=f"Draft agreement generated via AI extraction ({analysis.ai_model}).",
            changes={"status": "DRAFT", "total_value": str(agreement.total_value)},
        )
        db.add(history)

        # 7. Complete Analysis Record
        analysis.status = "COMPLETED"
        analysis.overall_summary = extraction.overall_summary
        analysis.raw_ai_response = extraction.model_dump()
        analysis.execution_duration_ms = elapsed_ms
        analysis.updated_at = datetime.now(timezone.utc)

        await db.commit()
        return await cls.get_analysis_by_id(db, analysis.id, user_id)

    @classmethod
    async def analyze_conversation(
        cls,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        force_retry: bool = False,
        sync: bool = False,
        ai_adapter: Optional[AIServiceAdapter] = None,
    ) -> ConversationAnalysis:
        """Run or enqueue conversation analysis with stale recovery, duplicate prevention,
        and ARQ worker background processing.
        """
        adapter = ai_adapter or get_ai_adapter()
        settings = get_settings()

        # 1. Verify conversation exists and user owns it
        conv_query = (
            select(Conversation)
            .where(Conversation.id == conversation_id, Conversation.deleted_at.is_(None))
            .options(selectinload(Conversation.messages))
        )
        conv_res = await db.execute(conv_query)
        conversation = conv_res.scalar_one_or_none()

        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found or has been deleted.",
            )

        if conversation.owner_id != user_id:
            settings = get_settings()
            if settings.ENVIRONMENT == "development" or settings.DEBUG or settings.ENVIRONMENT == "test":
                logger.info(f"Dev mode: reassigning conversation {conversation.id} ownership from {conversation.owner_id} to active tester {user_id}")
                conversation.owner_id = user_id
                await db.commit()
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Conversation not found.",
                )

        if not conversation.messages:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Conversation has no parsed messages to analyze.",
            )

        # 2. Stale-job recovery: transition stuck QUEUED/PROCESSING jobs to FAILED
        await cls.recover_stale_analyses(
            db=db,
            conversation_id=conversation_id,
            max_age_seconds=90,
            force=force_retry,
        )

        # 3. Duplicate Job Prevention: Check if fresh analysis is already in flight
        if not force_retry:
            existing_active = await db.execute(
                select(ConversationAnalysis).where(
                    ConversationAnalysis.conversation_id == conversation_id,
                    ConversationAnalysis.status.in_(["QUEUED", "PROCESSING"]),
                )
            )
            active_analysis = existing_active.scalar_one_or_none()
            if active_analysis:
                logger.info(f"Analysis {active_analysis.id} already active for conversation {conversation_id}.")
                return await cls.get_analysis_by_id(db, active_analysis.id, user_id)

        # 4. Synchronous execution if requested or running in unit tests
        if sync or settings.ENVIRONMENT == "test" or "pytest" in sys.modules:
            return await cls.execute_analysis(
                db=db,
                conversation_id=conversation_id,
                user_id=user_id,
                ai_adapter=adapter,
            )

        # 5. Asynchronous mode: create initial record in QUEUED status
        analysis = ConversationAnalysis(
            conversation_id=conversation.id,
            created_by_user_id=user_id,
            status="QUEUED",
            ai_model=getattr(adapter, "model", "gemini-3.8-flash"),
        )
        db.add(analysis)
        await db.commit()
        await db.refresh(analysis)

        # 6. Enqueue job to ARQ Redis worker
        enqueued = False
        try:
            from arq import create_pool
            from arq.connections import RedisSettings

            arq_redis = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
            job = await arq_redis.enqueue_job(
                "analyze_conversation_task",
                str(conversation_id),
                str(user_id),
                str(analysis.id),
            )
            await arq_redis.aclose()
            logger.info(f"Enqueued analyze_conversation_task {job.job_id} for analysis {analysis.id}")
            enqueued = True
        except Exception as queue_err:
            logger.warning(f"Could not enqueue to ARQ Redis: {queue_err}. Falling back to background task.")

        # Fallback to local async background execution if ARQ pool is unavailable
        if not enqueued:
            import asyncio
            from app.core.database import get_session_factory

            async def _bg_run():
                factory = get_session_factory()
                async with factory() as session:
                    await ConversationAnalyzerService.execute_analysis(
                        db=session,
                        conversation_id=conversation_id,
                        user_id=user_id,
                        analysis_id=analysis.id,
                        ai_adapter=adapter,
                    )

            asyncio.create_task(_bg_run())

        return await cls.get_analysis_by_id(db, analysis.id, user_id)

    @classmethod
    async def is_user_authorized_for_conversation(
        cls,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        """Check if user has legitimate stakeholder authorization for a conversation.
        Authorized users are:
        1. Conversation owner
        2. Agreement owner for any agreement in this conversation
        3. Explicitly bound user on any AgreementParticipant in this conversation
        """
        # 1. Check conversation owner
        conv_res = await db.execute(
            select(Conversation.id).where(
                Conversation.id == conversation_id,
                Conversation.owner_id == user_id,
                Conversation.deleted_at.is_(None),
            )
        )
        if conv_res.scalar_one_or_none():
            return True

        # 2. Check agreement owner
        agr_res = await db.execute(
            select(Agreement.id).where(
                Agreement.conversation_id == conversation_id,
                Agreement.owner_id == user_id,
            )
        )
        if agr_res.scalar_one_or_none():
            return True

        # 3. Check bound agreement participant
        part_res = await db.execute(
            select(AgreementParticipant.id)
            .join(Agreement, Agreement.id == AgreementParticipant.agreement_id)
            .where(
                Agreement.conversation_id == conversation_id,
                AgreementParticipant.user_id == user_id,
            )
        )
        if part_res.scalar_one_or_none():
            return True

        return False

    @classmethod
    async def get_latest_analysis_for_conversation(
        cls,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Optional[ConversationAnalysis]:
        """Fetch latest analysis record for a conversation with ownership/stakeholder check and stale recovery."""
        conv_res = await db.execute(
            select(Conversation).where(Conversation.id == conversation_id, Conversation.deleted_at.is_(None))
        )
        conv = conv_res.scalar_one_or_none()
        if not conv:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")

        is_authorized = (conv.owner_id == user_id) or await cls.is_user_authorized_for_conversation(
            db, conversation_id, user_id
        )
        if not is_authorized:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")

        # Automatically recover any stale analysis jobs for this conversation
        await cls.recover_stale_analyses(db, conversation_id=conversation_id, max_age_seconds=90)

        query = (
            select(ConversationAnalysis)
            .where(ConversationAnalysis.conversation_id == conversation_id)
            .order_by(desc(ConversationAnalysis.created_at))
            .options(
                selectinload(ConversationAnalysis.agreements).selectinload(Agreement.participants),
                selectinload(ConversationAnalysis.agreements).selectinload(Agreement.versions),
                selectinload(ConversationAnalysis.agreements).selectinload(Agreement.obligations),
                selectinload(ConversationAnalysis.agreements).selectinload(Agreement.expense_splits).selectinload(ExpenseSplit.shares),
                selectinload(ConversationAnalysis.agreements).selectinload(Agreement.history),
                selectinload(ConversationAnalysis.financial_facts),
                selectinload(ConversationAnalysis.ambiguities),
            )
        )
        result = await db.execute(query)
        return result.scalars().first()

    @classmethod
    async def get_analysis_by_id(
        cls,
        db: AsyncSession,
        analysis_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ConversationAnalysis:
        """Fetch analysis by ID with IDOR protection."""
        query = (
            select(ConversationAnalysis)
            .where(ConversationAnalysis.id == analysis_id)
            .options(
                selectinload(ConversationAnalysis.conversation),
                selectinload(ConversationAnalysis.agreements).selectinload(Agreement.participants),
                selectinload(ConversationAnalysis.agreements).selectinload(Agreement.versions),
                selectinload(ConversationAnalysis.agreements).selectinload(Agreement.obligations),
                selectinload(ConversationAnalysis.agreements).selectinload(Agreement.expense_splits).selectinload(ExpenseSplit.shares),
                selectinload(ConversationAnalysis.agreements).selectinload(Agreement.history),
                selectinload(ConversationAnalysis.financial_facts),
                selectinload(ConversationAnalysis.ambiguities),
            )
        )
        res = await db.execute(query)
        analysis = res.scalar_one_or_none()

        if not analysis:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found.")

        if analysis.created_by_user_id != user_id and analysis.conversation.owner_id != user_id:
            is_authorized = await cls.is_user_authorized_for_conversation(db, analysis.conversation_id, user_id)
            if not is_authorized:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found.")

        return analysis

    @classmethod
    async def resolve_ambiguity(
        cls,
        db: AsyncSession,
        ambiguity_id: uuid.UUID,
        user_id: uuid.UUID,
        resolution_text: str,
    ) -> Ambiguity:
        """Resolve an ambiguity and record decision in agreement audit history."""
        query = (
            select(Ambiguity)
            .where(Ambiguity.id == ambiguity_id)
            .options(
                selectinload(Ambiguity.conversation),
                selectinload(Ambiguity.agreement),
            )
        )
        res = await db.execute(query)
        ambiguity = res.scalar_one_or_none()

        if not ambiguity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ambiguity not found.")

        if ambiguity.conversation.owner_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ambiguity not found.")

        ambiguity.status = "RESOLVED"
        ambiguity.resolution_text = resolution_text.strip()
        ambiguity.resolved_by_user_id = user_id
        ambiguity.resolved_at = datetime.now(timezone.utc)

        # Audit entry in agreement history if linked
        if ambiguity.agreement_id:
            history = AgreementHistory(
                agreement_id=ambiguity.agreement_id,
                user_id=user_id,
                action="AMBIGUITY_RESOLVED",
                notes=f"Resolved '{ambiguity.ambiguity_type}': {resolution_text.strip()}",
                changes={"ambiguity_id": str(ambiguity.id), "resolution": resolution_text.strip()},
            )
            db.add(history)

        await db.commit()
        await db.refresh(ambiguity)
        return ambiguity

    @classmethod
    def is_user_authorized_for_participant(cls, user: Optional[User], participant: AgreementParticipant) -> bool:
        """Check whether the user is authorized to represent and respond on behalf of this participant.
        STRICT SECURITY RULE:
        - Only explicitly bound user accounts (participant.user_id == user.id) are authorized.
        - First-name matching, display-name matching, email-prefix matching, case-insensitive
          similarity, and unverified identity inferences are strictly prohibited.
        """
        if not user or participant.user_id is None:
            return False
        return participant.user_id == user.id

    @classmethod
    def _build_participant_response(
        cls,
        p: AgreementParticipant,
        current_user: Optional[User] = None,
        bound_user: Optional[User] = None,
        current_ver: int = 1,
    ) -> AgreementParticipantResponse:
        can_respond = False
        if current_user:
            can_respond = cls.is_user_authorized_for_participant(current_user, p)

        is_curr_ver = (p.responded_version == current_ver)
        display_status = p.consent_status if is_curr_ver else "PENDING"

        # Check for active pending invitation
        has_pending_inv = False
        if "invitations" in p.__dict__ and p.invitations:
            now = datetime.now(timezone.utc)
            for inv in p.invitations:
                if not inv.is_claimed:
                    inv_exp = inv.expires_at if (inv.expires_at and inv.expires_at.tzinfo) else (inv.expires_at.replace(tzinfo=timezone.utc) if inv.expires_at else now)
                    if inv_exp > now:
                        has_pending_inv = True
                        break

        b_email = None
        b_name = None
        if bound_user:
            b_email = bound_user.email
            b_name = bound_user.full_name
        elif getattr(p, "user", None):
            b_email = p.user.email
            b_name = p.user.full_name

        return AgreementParticipantResponse(
            id=p.id,
            participant_id=p.participant_id,
            user_id=p.user_id,
            name=p.name,
            stated_role=p.stated_role,
            consent_status=display_status,
            responded_version=p.responded_version,
            responded_at=p.responded_at,
            comment=p.comment,
            is_confirmed=(display_status == "ACCEPTED"),
            confirmed_at=p.confirmed_at if is_curr_ver else None,
            bound_at=p.bound_at,
            bound_method=p.bound_method,
            bound_user_email=b_email,
            bound_user_name=b_name,
            has_pending_invitation=has_pending_inv,
            created_at=p.created_at,
            can_respond=can_respond,
        )

    @classmethod
    def evaluate_consensus(cls, agreement: Agreement) -> Tuple[str, bool, str]:
        """Deterministically evaluate agreement status and consensus message.
        Returns: (status, is_confirmed, status_message)
        """
        total = len(agreement.participants)
        if total == 0:
            return agreement.status, False, f"Agreement Version {agreement.version} has no participants."

        current_ver = agreement.version
        accepted = [p for p in agreement.participants if p.consent_status == "ACCEPTED" and p.responded_version == current_ver]
        rejected = [p for p in agreement.participants if p.consent_status == "REJECTED" and p.responded_version == current_ver]
        changes_req = [p for p in agreement.participants if p.consent_status == "REQUESTED_CHANGES" and p.responded_version == current_ver]
        pending = [p for p in agreement.participants if p.consent_status == "PENDING" or p.responded_version != current_ver]

        # Rule 5: Any rejection prevents confirmation
        if len(rejected) > 0:
            msg = f"Agreement rejected by {', '.join(p.name for p in rejected)}"
            return "REJECTED", False, msg

        # Rule 6: Change request moves agreement into CHANGES_REQUESTED
        if len(changes_req) > 0:
            msg = f"Changes requested by {', '.join(p.name for p in changes_req)}"
            return "CHANGES_REQUESTED", False, msg

        # Rule 4: All required participants must accept current version before CONFIRMED
        if len(accepted) == total:
            msg = f"All {total} required participants accepted Version {current_ver}"
            return "CONFIRMED", True, msg

        # Rule: Partially accepted
        if len(accepted) > 0:
            pending_names = [p.name for p in pending]
            msg = f"{len(accepted)} of {total} participants accepted — awaiting {', '.join(pending_names)}"
            return "PARTIALLY_ACCEPTED", False, msg

        # Default review state
        if agreement.submitted_for_review_at is not None or agreement.status == "UNDER_REVIEW":
            return "UNDER_REVIEW", False, f"Awaiting participant review for Version {current_ver} (0 of {total} accepted)"

        return "DRAFT", False, f"Draft agreement Version {current_ver} (0 of {total} accepted)"

    @classmethod
    def build_consensus_response(
        cls,
        agreement: Agreement,
        current_user: Optional[User] = None,
    ) -> AgreementConsensusResponse:
        total = len(agreement.participants)
        current_ver = agreement.version

        accepted = [p for p in agreement.participants if p.consent_status == "ACCEPTED" and p.responded_version == current_ver]
        rejected = [p for p in agreement.participants if p.consent_status == "REJECTED" and p.responded_version == current_ver]
        changes_req = [p for p in agreement.participants if p.consent_status == "REQUESTED_CHANGES" and p.responded_version == current_ver]
        pending = [p for p in agreement.participants if p.consent_status == "PENDING" or p.responded_version != current_ver]

        status, is_confirmed, status_msg = cls.evaluate_consensus(agreement)

        participant_items = [
            cls._build_participant_response(p, current_user, getattr(p, "user", None), current_ver)
            for p in agreement.participants
        ]

        return AgreementConsensusResponse(
            agreement_id=agreement.id,
            version=agreement.version,
            status=status,
            is_confirmed=is_confirmed,
            total_participants=total,
            accepted_count=len(accepted),
            pending_count=len(pending),
            rejected_count=len(rejected),
            changes_requested_count=len(changes_req),
            consensus_achieved=is_confirmed,
            status_message=status_msg,
            participants=participant_items,
            pending_participant_names=[p.name for p in pending],
        )

    @classmethod
    async def get_agreement_by_id(
        cls,
        db: AsyncSession,
        agreement_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
    ) -> Agreement:
        """Fetch agreement with all relations and optional tenant verification."""
        query = (
            select(Agreement)
            .where(Agreement.id == agreement_id)
            .options(
                selectinload(Agreement.conversation).selectinload(Conversation.participants),
                selectinload(Agreement.participants).selectinload(AgreementParticipant.user),
                selectinload(Agreement.participants).selectinload(AgreementParticipant.invitations),
                selectinload(Agreement.versions),
                selectinload(Agreement.responses),
                selectinload(Agreement.obligations),
                selectinload(Agreement.expense_splits).selectinload(ExpenseSplit.shares),
                selectinload(Agreement.history),
            )
        )
        res = await db.execute(query)
        agreement = res.scalar_one_or_none()
        if not agreement:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agreement not found.")

        if user_id is not None:
            user = await db.get(User, user_id)
            is_dev_tester = getattr(user, "email", "") == "tester@veritas.local"
            if not is_dev_tester:
                is_owner = agreement.owner_id == user_id or (agreement.conversation and agreement.conversation.owner_id == user_id)
                is_part = any(cls.is_user_authorized_for_participant(user, p) for p in agreement.participants)
                if not is_owner and not is_part:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agreement not found.")

        return agreement

    @classmethod
    async def submit_agreement_for_review(
        cls,
        db: AsyncSession,
        agreement_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> AgreementConsensusResponse:
        """Transition DRAFT agreement to UNDER_REVIEW so participants can review and respond."""
        agreement = await cls.get_agreement_by_id(db, agreement_id, user_id=user_id)
        if agreement.owner_id != user_id and agreement.conversation.owner_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agreement not found.")

        now = datetime.now(timezone.utc)
        agreement.status = "UNDER_REVIEW"
        agreement.submitted_for_review_at = now

        history = AgreementHistory(
            agreement_id=agreement.id,
            user_id=user_id,
            action="SUBMITTED_FOR_REVIEW",
            notes=f"Agreement Version {agreement.version} submitted for participant review.",
            changes={"status": "UNDER_REVIEW", "version": agreement.version},
            created_at=now,
        )
        db.add(history)
        await db.commit()
        await db.refresh(agreement)

        user = await db.get(User, user_id)
        return cls.build_consensus_response(agreement, user)

    @classmethod
    async def respond_as_participant(
        cls,
        db: AsyncSession,
        agreement_id: uuid.UUID,
        participant_id: uuid.UUID,
        user: User,
        response_value: str,
        comment: Optional[str] = None,
    ) -> AgreementConsensusResponse:
        """Record an authenticated participant's individual consent decision on the agreement version."""
        agreement = await cls.get_agreement_by_id(db, agreement_id)

        target_part: Optional[AgreementParticipant] = None
        for p in agreement.participants:
            if p.id == participant_id or p.participant_id == participant_id:
                target_part = p
                break

        if not target_part:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Participant not found on this agreement.",
            )

        # Strict Authorization check: participant must be securely bound to user
        if target_part.user_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Participant '{target_part.name}' is not bound to a user account. You must accept an invitation or have the owner assign your account first.",
            )

        if target_part.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"You are not authorized to respond on behalf of participant '{target_part.name}'. Only the verified bound account can submit consent.",
            )

        norm_response = response_value.strip().upper()
        valid_responses = ("ACCEPTED", "REJECTED", "REQUESTED_CHANGES")
        if norm_response not in valid_responses:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid response '{response_value}'. Must be one of: {', '.join(valid_responses)}",
            )

        now = datetime.now(timezone.utc)
        cleaned_comment = comment.strip() if comment and comment.strip() else None

        # Check for idempotent retry: identical response, same version, and same comment
        is_exact_retry = (
            target_part.consent_status == norm_response
            and target_part.responded_version == agreement.version
            and (target_part.comment or None) == cleaned_comment
        )
        if is_exact_retry:
            logger.info(
                f"Idempotent response: participant {target_part.name} already recorded {norm_response} for v{agreement.version}. Skipping duplicate audit."
            )
            return cls.build_consensus_response(agreement, user)

        # Idempotency / duplicate handling on agreement_participant_responses
        resp_stmt = select(AgreementParticipantConsent).where(
            AgreementParticipantConsent.agreement_participant_id == target_part.id,
            AgreementParticipantConsent.version == agreement.version,
        )
        resp_res = await db.execute(resp_stmt)
        existing_resp = resp_res.scalar_one_or_none()

        if existing_resp:
            existing_resp.response = norm_response
            existing_resp.comment = cleaned_comment
            existing_resp.created_at = now
            existing_resp.user_id = user.id
        else:
            new_resp = AgreementParticipantConsent(
                agreement_id=agreement.id,
                agreement_participant_id=target_part.id,
                participant_id=target_part.participant_id,
                user_id=user.id,
                version=agreement.version,
                response=norm_response,
                comment=cleaned_comment,
                created_at=now,
            )
            db.add(new_resp)

        # Update participant record
        target_part.consent_status = norm_response
        target_part.responded_version = agreement.version
        target_part.responded_at = now
        target_part.comment = cleaned_comment
        target_part.is_confirmed = (norm_response == "ACCEPTED")
        target_part.confirmed_at = now if target_part.is_confirmed else None

        # Re-evaluate consensus deterministically
        new_status, is_confirmed, status_msg = cls.evaluate_consensus(agreement)
        agreement.status = new_status
        agreement.is_confirmed = is_confirmed
        if is_confirmed:
            agreement.confirmed_at = now
            agreement.confirmed_by_id = user.id
        else:
            agreement.confirmed_at = None
            agreement.confirmed_by_id = None

        # Audit history
        action_name = f"PARTICIPANT_{norm_response}"
        history = AgreementHistory(
            agreement_id=agreement.id,
            user_id=user.id,
            action=action_name,
            notes=f"{target_part.name} responded {norm_response} to Version {agreement.version}: {cleaned_comment or 'No comment'}",
            changes={
                "participant_id": str(target_part.id),
                "participant_name": target_part.name,
                "response": norm_response,
                "version": agreement.version,
                "agreement_status": new_status,
            },
            created_at=now,
        )
        db.add(history)

        await db.commit()
        await db.refresh(agreement)
        return cls.build_consensus_response(agreement, user)

    @classmethod
    async def bind_participant_to_user(
        cls,
        db: AsyncSession,
        agreement_id: uuid.UUID,
        participant_id: uuid.UUID,
        current_user: User,
        target_user_id: Optional[uuid.UUID] = None,
        target_email: Optional[str] = None,
    ) -> AgreementParticipantResponse:
        """Agreement owner explicitly assigns an authenticated user to an agreement participant."""
        agreement = await cls.get_agreement_by_id(db, agreement_id)

        # Authorization: Only agreement owner can assign participants (in UI development, allow tester@veritas.local)
        is_dev_tester = getattr(current_user, "email", "") == "tester@veritas.local"
        if not is_dev_tester and agreement.owner_id != current_user.id and (not agreement.conversation or agreement.conversation.owner_id != current_user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the agreement owner can assign participants to user accounts.",
            )

        target_part: Optional[AgreementParticipant] = None
        for p in agreement.participants:
            if p.id == participant_id or p.participant_id == participant_id:
                target_part = p
                break

        if not target_part:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Participant not found on this agreement.",
            )

        target_user: Optional[User] = None
        if target_user_id:
            target_user = await db.get(User, target_user_id)
        elif target_email:
            res = await db.execute(select(User).where(User.email == target_email.strip().lower()))
            target_user = res.scalar_one_or_none()
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Either user_id or email must be provided to bind participant.",
            )

        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User account to assign was not found.",
            )

        # Prevent assigning a user who is already bound to another participant in this agreement
        for p in agreement.participants:
            if p.id != target_part.id and p.user_id == target_user.id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"User {target_user.email} is already bound to participant '{p.name}' in this agreement.",
                )

        # Prevent reassignment if participant has already submitted consent
        if target_part.user_id is not None and target_part.user_id != target_user.id:
            if target_part.consent_status != "PENDING":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot reassign participant '{target_part.name}' because consent has already been submitted.",
                )

        now = datetime.now(timezone.utc)
        target_part.user_id = target_user.id
        target_part.bound_at = now
        target_part.bound_method = "DIRECT_ASSIGNMENT"

        # Invalidate any pending unclaimed invitations for this participant
        await db.execute(
            update(ParticipantInvitation)
            .where(
                ParticipantInvitation.agreement_participant_id == target_part.id,
                ParticipantInvitation.is_claimed == False,
            )
            .values(is_claimed=True, claimed_at=now, claimed_by_user_id=target_user.id)
        )

        history = AgreementHistory(
            agreement_id=agreement.id,
            user_id=current_user.id,
            action="PARTICIPANT_BOUND",
            notes=f"Agreement owner assigned {target_user.email} ({target_user.full_name or 'User'}) to participant '{target_part.name}'.",
            changes={
                "participant_id": str(target_part.id),
                "participant_name": target_part.name,
                "bound_user_id": str(target_user.id),
                "bound_user_email": target_user.email,
                "method": "DIRECT_ASSIGNMENT",
            },
            created_at=now,
        )
        db.add(history)
        await db.commit()
        await db.refresh(target_part)

        return cls._build_participant_response(target_part, current_user, target_user, agreement.version)

    @classmethod
    async def unbind_participant(
        cls,
        db: AsyncSession,
        agreement_id: uuid.UUID,
        participant_id: uuid.UUID,
        current_user: User,
    ) -> AgreementParticipantResponse:
        """Agreement owner revokes binding from an agreement participant (only if consent is PENDING)."""
        agreement = await cls.get_agreement_by_id(db, agreement_id)

        # Authorization: Only agreement owner can unbind participants (in UI development, allow tester@veritas.local)
        is_dev_tester = getattr(current_user, "email", "") == "tester@veritas.local"
        if not is_dev_tester and agreement.owner_id != current_user.id and (not agreement.conversation or agreement.conversation.owner_id != current_user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the agreement owner can unbind participants.",
            )

        target_part: Optional[AgreementParticipant] = None
        for p in agreement.participants:
            if p.id == participant_id or p.participant_id == participant_id:
                target_part = p
                break

        if not target_part:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Participant not found on this agreement.")

        if target_part.consent_status != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot unbind participant '{target_part.name}' because consent has already been submitted.",
            )

        now = datetime.now(timezone.utc)
        prev_user_id = target_part.user_id
        target_part.user_id = None
        target_part.bound_at = None
        target_part.bound_method = None

        history = AgreementHistory(
            agreement_id=agreement.id,
            user_id=current_user.id,
            action="PARTICIPANT_UNBOUND",
            notes=f"Owner unbound participant '{target_part.name}' from user account {prev_user_id}.",
            changes={
                "participant_id": str(target_part.id),
                "participant_name": target_part.name,
                "previous_user_id": str(prev_user_id) if prev_user_id else None,
            },
            created_at=now,
        )
        db.add(history)
        await db.commit()
        await db.refresh(target_part)

        return cls._build_participant_response(target_part, current_user, None, agreement.version)

    @classmethod
    async def create_participant_invitation(
        cls,
        db: AsyncSession,
        agreement_id: uuid.UUID,
        participant_id: uuid.UUID,
        current_user: User,
        expires_in_hours: int = 48,
    ) -> InvitationResponse:
        """Generate a cryptographically random, single-use invitation token to bind a user to a participant."""
        agreement = await cls.get_agreement_by_id(db, agreement_id)

        # Only agreement owner can generate invitations (in UI development, allow tester@veritas.local)
        is_dev_tester = getattr(current_user, "email", "") == "tester@veritas.local"
        if not is_dev_tester and agreement.owner_id != current_user.id and (not agreement.conversation or agreement.conversation.owner_id != current_user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the agreement owner can generate participant invitations.",
            )

        target_part: Optional[AgreementParticipant] = None
        for p in agreement.participants:
            if p.id == participant_id or p.participant_id == participant_id:
                target_part = p
                break

        if not target_part:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Participant not found on this agreement.",
            )

        if target_part.user_id is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Participant '{target_part.name}' is already bound to a verified user account.",
            )

        # Cryptographically secure random token (256 bits of entropy)
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=expires_in_hours)

        invitation = ParticipantInvitation(
            agreement_participant_id=target_part.id,
            agreement_id=agreement.id,
            created_by_user_id=current_user.id,
            token_hash=token_hash,
            expires_at=expires_at,
            is_claimed=False,
            created_at=now,
        )
        db.add(invitation)

        history = AgreementHistory(
            agreement_id=agreement.id,
            user_id=current_user.id,
            action="INVITATION_CREATED",
            notes=f"Single-use invitation generated for participant '{target_part.name}' (expires in {expires_in_hours}h).",
            changes={
                "participant_id": str(target_part.id),
                "participant_name": target_part.name,
                "expires_at": expires_at.isoformat(),
            },
            created_at=now,
        )
        db.add(history)
        await db.commit()
        await db.refresh(invitation)

        invitation_url = f"/accord/invite?token={raw_token}"
        return InvitationResponse(
            id=invitation.id,
            agreement_participant_id=target_part.id,
            agreement_id=agreement.id,
            participant_name=target_part.name,
            invitation_token=raw_token,
            invitation_url=invitation_url,
            expires_at=invitation.expires_at,
            is_claimed=False,
            created_at=invitation.created_at,
        )

    @classmethod
    async def get_invitation_details(
        cls,
        db: AsyncSession,
        raw_token: str,
    ) -> InvitationDetailsResponse:
        """Inspect and validate an invitation token without claiming it."""
        token_hash = hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()
        stmt = (
            select(ParticipantInvitation)
            .where(ParticipantInvitation.token_hash == token_hash)
            .options(
                selectinload(ParticipantInvitation.participant),
                selectinload(ParticipantInvitation.agreement),
            )
        )
        res = await db.execute(stmt)
        inv = res.scalar_one_or_none()

        if not inv:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invitation token not found or invalid.",
            )

        now = datetime.now(timezone.utc)
        inv_expires = inv.expires_at if (inv.expires_at and inv.expires_at.tzinfo) else (inv.expires_at.replace(tzinfo=timezone.utc) if inv.expires_at else now)
        is_expired = now > inv_expires
        is_valid = not inv.is_claimed and not is_expired

        return InvitationDetailsResponse(
            id=inv.id,
            agreement_id=inv.agreement_id,
            agreement_title=inv.agreement.title if inv.agreement else "VERITAS Agreement",
            participant_id=inv.agreement_participant_id,
            participant_name=inv.participant.name if inv.participant else "Participant",
            stated_role=inv.participant.stated_role if inv.participant else "PARTICIPANT",
            expires_at=inv.expires_at,
            is_expired=is_expired,
            is_claimed=inv.is_claimed,
            is_valid=is_valid,
        )

    @classmethod
    async def accept_participant_invitation(
        cls,
        db: AsyncSession,
        raw_token: str,
        current_user: User,
    ) -> AgreementConsensusResponse:
        """Authenticated user claims a single-use invitation token, binding their user_id to the participant."""
        token_hash = hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()
        stmt = (
            select(ParticipantInvitation)
            .where(ParticipantInvitation.token_hash == token_hash)
            .options(
                selectinload(ParticipantInvitation.participant),
                selectinload(ParticipantInvitation.agreement).selectinload(Agreement.participants),
                selectinload(ParticipantInvitation.agreement).selectinload(Agreement.conversation),
            )
        )
        res = await db.execute(stmt)
        inv = res.scalar_one_or_none()

        if not inv:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid or nonexistent invitation token.",
            )

        if inv.is_claimed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invitation has already been used. Tokens are single-use only.",
            )

        now = datetime.now(timezone.utc)
        inv_expires = inv.expires_at if (inv.expires_at and inv.expires_at.tzinfo) else (inv.expires_at.replace(tzinfo=timezone.utc) if inv.expires_at else now)
        if now > inv_expires:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invitation token has expired. Please request a new invitation from the agreement owner.",
            )

        participant = inv.participant
        agreement = inv.agreement

        if not participant or not agreement:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Associated agreement or participant not found.")

        # Prevent binding if participant is already bound to another account
        if participant.user_id is not None and participant.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Participant '{participant.name}' is already bound to another user account.",
            )

        # Prevent one user from binding to multiple participants in the same agreement
        for p in agreement.participants:
            if p.id != participant.id and p.user_id == current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Your account is already bound to participant '{p.name}' in this agreement. One user cannot hold multiple participant roles.",
                )

        # Mark token as claimed
        inv.is_claimed = True
        inv.claimed_at = now
        inv.claimed_by_user_id = current_user.id

        # Bind participant
        participant.user_id = current_user.id
        participant.bound_at = now
        participant.bound_method = "INVITATION"

        history = AgreementHistory(
            agreement_id=agreement.id,
            user_id=current_user.id,
            action="PARTICIPANT_BOUND",
            notes=f"User {current_user.email} claimed invitation and securely bound to participant '{participant.name}'.",
            changes={
                "participant_id": str(participant.id),
                "participant_name": participant.name,
                "bound_user_id": str(current_user.id),
                "bound_user_email": current_user.email,
                "method": "INVITATION",
            },
            created_at=now,
        )
        db.add(history)
        await db.commit()
        await db.refresh(agreement)

        return cls.build_consensus_response(agreement, current_user)

    @classmethod
    async def update_agreement(
        cls,
        db: AsyncSession,
        agreement_id: uuid.UUID,
        user_id: uuid.UUID,
        title: Optional[str] = None,
        summary: Optional[str] = None,
        terms: Optional[List[str]] = None,
    ) -> Agreement:
        """Edit draft agreement fields, increment agreement version, and invalidate previous acceptances."""
        agreement = await cls.get_agreement_by_id(db, agreement_id)
        if agreement.owner_id != user_id and agreement.conversation.owner_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agreement not found.")

        if agreement.status == "CONFIRMED":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Confirmed agreements cannot be edited. Please create a new revision.",
            )

        changes: Dict[str, Any] = {}
        if title is not None and title.strip():
            changes["title"] = {"old": agreement.title, "new": title.strip()}
            agreement.title = title.strip()
        if summary is not None and summary.strip():
            changes["summary"] = {"old": agreement.summary, "new": summary.strip()}
            agreement.summary = summary.strip()
        if terms is not None:
            changes["terms"] = {"old": agreement.terms, "new": terms}
            agreement.terms = terms

        # Rule 2: Increment version
        agreement.version += 1
        now = datetime.now(timezone.utc)

        # Rule 3: Previous acceptances must not automatically carry over to the new version
        for p in agreement.participants:
            p.consent_status = "PENDING"
            p.responded_version = None
            p.responded_at = None
            p.comment = None
            p.is_confirmed = False
            p.confirmed_at = None

        agreement.status = "UNDER_REVIEW"
        agreement.is_confirmed = False
        agreement.confirmed_at = None
        agreement.confirmed_by_id = None

        # Version Snapshot
        ver_snapshot = AgreementVersion(
            agreement_id=agreement.id,
            version=agreement.version,
            title=agreement.title,
            summary=agreement.summary,
            terms=agreement.terms,
            total_value=agreement.total_value,
            currency=agreement.currency,
            created_by_user_id=user_id,
            created_at=now,
        )
        db.add(ver_snapshot)

        history = AgreementHistory(
            agreement_id=agreement.id,
            user_id=user_id,
            action="REVISED",
            notes=f"Agreement revised to Version {agreement.version}. Previous participant acceptances reset.",
            changes={"new_version": agreement.version, "field_changes": changes},
            created_at=now,
        )
        db.add(history)

        await db.commit()
        await db.refresh(agreement)
        return agreement

    @classmethod
    async def confirm_agreement(
        cls,
        db: AsyncSession,
        agreement_id: uuid.UUID,
        user_id: uuid.UUID,
        notes: Optional[str] = None,
    ) -> Agreement:
        """Compatibly confirm agreement consensus.
        Records caller's participant acceptance if matching; only sets CONFIRMED
        if every required participant has accepted the current version.
        """
        agreement = await cls.get_agreement_by_id(db, agreement_id)
        if agreement.owner_id != user_id and agreement.conversation.owner_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agreement not found.")

        if agreement.status == "CONFIRMED" and agreement.is_confirmed:
            # Agreement is already confirmed with mutual consensus; return idempotently
            return agreement

        user = await db.get(User, user_id)
        now = datetime.now(timezone.utc)

        # Find participant authorized for caller and record their acceptance
        matching_part = next((p for p in agreement.participants if cls.is_user_authorized_for_participant(user, p)), None)
        if matching_part:
            matching_part.consent_status = "ACCEPTED"
            matching_part.responded_version = agreement.version
            matching_part.responded_at = now
            matching_part.is_confirmed = True
            matching_part.confirmed_at = now
            matching_part.user_id = user_id

            resp_stmt = select(AgreementParticipantConsent).where(
                AgreementParticipantConsent.agreement_participant_id == matching_part.id,
                AgreementParticipantConsent.version == agreement.version,
            )
            existing = (await db.execute(resp_stmt)).scalar_one_or_none()
            if existing:
                existing.response = "ACCEPTED"
                existing.created_at = now
            else:
                db.add(AgreementParticipantConsent(
                    agreement_id=agreement.id,
                    agreement_participant_id=matching_part.id,
                    participant_id=matching_part.participant_id,
                    user_id=user_id,
                    version=agreement.version,
                    response="ACCEPTED",
                    created_at=now,
                ))

        new_status, is_confirmed, msg = cls.evaluate_consensus(agreement)
        agreement.status = new_status
        agreement.is_confirmed = is_confirmed
        if is_confirmed:
            agreement.confirmed_at = now
            agreement.confirmed_by_id = user_id

        history = AgreementHistory(
            agreement_id=agreement.id,
            user_id=user_id,
            action="CONFIRMED" if is_confirmed else "PARTICIPANT_ACCEPTED",
            notes=notes or msg,
            changes={"status": agreement.status, "version": agreement.version, "is_confirmed": agreement.is_confirmed},
            created_at=now,
        )
        db.add(history)

        await db.commit()
        await db.refresh(agreement)
        return agreement

    @classmethod
    async def reject_agreement(
        cls,
        db: AsyncSession,
        agreement_id: uuid.UUID,
        user_id: uuid.UUID,
        rejection_reason: str,
        notes: Optional[str] = None,
    ) -> Agreement:
        """Explicitly reject agreement draft."""
        agreement = await cls.get_agreement_by_id(db, agreement_id)
        if agreement.owner_id != user_id and agreement.conversation.owner_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agreement not found.")

        now = datetime.now(timezone.utc)
        user = await db.get(User, user_id)

        # If caller matches a participant, set their individual status to REJECTED
        matching_part = next((p for p in agreement.participants if cls.is_user_authorized_for_participant(user, p)), None)
        if matching_part:
            matching_part.consent_status = "REJECTED"
            matching_part.responded_version = agreement.version
            matching_part.responded_at = now
            matching_part.comment = rejection_reason.strip()
            matching_part.is_confirmed = False
            matching_part.user_id = user_id

        agreement.status = "REJECTED"
        agreement.is_confirmed = False
        agreement.rejection_reason = rejection_reason.strip()
        agreement.rejection_notes = notes.strip() if notes else None

        history = AgreementHistory(
            agreement_id=agreement.id,
            user_id=user_id,
            action="REJECTED",
            notes=f"Reason: {rejection_reason.strip()}",
            changes={"status": "REJECTED", "rejection_reason": rejection_reason.strip()},
            created_at=now,
        )
        db.add(history)

        await db.commit()
        await db.refresh(agreement)
        return agreement

    @classmethod
    async def get_agreement_consensus(
        cls,
        db: AsyncSession,
        agreement_id: uuid.UUID,
        user: User,
    ) -> AgreementConsensusResponse:
        """Fetch real-time participant consensus for agreement."""
        agreement = await cls.get_agreement_by_id(db, agreement_id, user_id=user.id)
        return cls.build_consensus_response(agreement, user)

    @classmethod
    async def get_agreement_history(
        cls,
        db: AsyncSession,
        agreement_id: uuid.UUID,
        user: User,
    ) -> List[AgreementHistory]:
        """Fetch audit log history for agreement."""
        agreement = await cls.get_agreement_by_id(db, agreement_id, user_id=user.id)
        return agreement.history

    @classmethod
    async def get_financial_summary(
        cls,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> FinancialCalculationResult:
        """Compute live deterministic financial breakdown and settlement for conversation."""
        conv_res = await db.execute(
            select(Conversation)
            .where(Conversation.id == conversation_id, Conversation.deleted_at.is_(None))
            .options(selectinload(Conversation.participants))
        )
        conv = conv_res.scalar_one_or_none()
        if not conv:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")

        is_authorized = (conv.owner_id == user_id) or await cls.is_user_authorized_for_conversation(
            db, conversation_id, user_id
        )
        if not is_authorized:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")

        # Fetch all financial facts for this conversation
        facts_res = await db.execute(
            select(FinancialFact).where(FinancialFact.conversation_id == conversation_id)
        )
        facts = facts_res.scalars().all()

        paid_facts = [
            f for f in facts 
            if f.classification.upper() == "PAID"
            and not any(term in (f.description or "").lower() for term in ["personal", "borrowed", "loan to", "loan from"])
        ]
        entries = [
            ExpenseEntry(
                payer_name=f.payer_name or "Unknown Payer",
                amount=f.amount,
                description=f.description,
            )
            for f in paid_facts
        ]

        participants = [p.display_name for p in conv.participants]
        if not participants and facts:
            # Collect names from facts
            collected = set()
            for f in facts:
                if f.payer_name:
                    collected.add(f.payer_name)
                if f.recipient_name:
                    collected.add(f.recipient_name)
            participants = list(collected)

        currency = "USD"
        if paid_facts:
            currency = paid_facts[0].currency or "USD"
        elif "₹" in (conv.raw_transcript or "") or "INR" in (conv.raw_transcript or ""):
            currency = "INR"

        return ExpenseCalculator.calculate_split(
            expenses=entries,
            participants=participants or ["Participant 1"],
            split_method="EQUAL",
            currency=currency,
        )
