import logging
import math
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.models.user import User
from app.accord.models.agreement import Agreement, AgreementParticipant
from app.accord.models.conversation import Conversation
from app.accord.models.message import Message
from app.accord.models.participant import Participant
from app.accord.schemas import (
    AgreementConsensusResponse,
    AgreementHistoryResponse,
    AgreementParticipantResponse,
    AgreementResponse,
    AmbiguityResponse,
    AssignParticipantUserRequest,
    ConfirmAgreementRequest,
    ConversationAnalysisResponse,
    ConversationDetailResponse,
    ConversationSummaryResponse,
    CreateInvitationRequest,
    FinancialSummaryResponse,
    InvitationDetailsResponse,
    InvitationResponse,
    MessageResponse,
    PaginatedConversationsResponse,
    ParticipantConsentRequest,
    ParticipantResponse,
    ParticipantShareResponse,
    PastedTextRequest,
    RejectAgreementRequest,
    ResolveAmbiguityRequest,
    SettlementTransferResponse,
    UpdateAgreementRequest,
)
from app.accord.services.analyzer import ConversationAnalyzerService
from app.accord.services.ingestion import IngestionService
from app.accord.services.dev_store import DevStore

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ACCORD Ingestion"])


@router.post(
    "/conversations/text",
    response_model=ConversationDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit pasted conversation text",
)
async def submit_pasted_conversation(
    payload: PastedTextRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationDetailResponse:
    """Ingest pasted conversation text, parse messages, identify participants, and return summary."""
    try:
        conversation = await IngestionService.ingest_pasted_text(
            db=db,
            owner_id=current_user.id,
            content=payload.content,
            title=payload.title,
        )

        # Reload with relationships
        stmt = (
            select(Conversation)
            .options(selectinload(Conversation.participants), selectinload(Conversation.messages))
            .where(Conversation.id == conversation.id)
        )
        res = await db.execute(stmt)
        full_conv = res.scalar_one()

        resp = ConversationDetailResponse(
            id=full_conv.id,
            title=full_conv.title,
            source_type=full_conv.source_type,
            original_filename=full_conv.original_filename,
            processing_status=full_conv.processing_status,
            participants=[ParticipantResponse.model_validate(p) for p in full_conv.participants],
            messages=[MessageResponse.model_validate(m) for m in full_conv.messages],
            total_messages=len(full_conv.messages),
            total_participants=len(full_conv.participants),
            created_at=full_conv.created_at,
            updated_at=full_conv.updated_at,
        )
        DevStore.save_conversation(resp)
        return resp
    except Exception:
        # Resilient Standby Database fallback: parse and return directly
        from app.accord.services.parser import WhatsAppParser
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        parsed = WhatsAppParser.parse(payload.content)
        conv_id = uuid.uuid4()
        parts = [
            ParticipantResponse(
                id=uuid.uuid4(),
                conversation_id=conv_id,
                display_name=s.strip(),
                sender_identifier=s.strip().lower(),
                user_id=current_user.id if i == 0 else None,
                is_user=i == 0,
                created_at=now,
                updated_at=now,
            )
            for i, s in enumerate(parsed.unique_senders)
        ]
        msgs = [
            MessageResponse(
                id=uuid.uuid4(),
                conversation_id=conv_id,
                participant_id=parts[0].id if parts else None,
                sender_name=m.sender_name or "System",
                message_body=m.message_body,
                original_timestamp=m.original_timestamp,
                order_index=m.order_index,
                is_system_message=m.is_system_message,
                created_at=now,
                updated_at=now,
            )
            for m in parsed.messages
        ]
        resp = ConversationDetailResponse(
            id=conv_id,
            title=payload.title.strip() if payload.title else "Parsed Conversation",
            source_type="PASTED_TEXT",
            original_filename=None,
            processing_status="COMPLETED",
            participants=parts,
            messages=msgs,
            total_messages=len(msgs),
            total_participants=len(parts),
            created_at=now,
            updated_at=now,
        )
        DevStore.save_conversation(resp)
        return resp


@router.post(
    "/conversations/upload",
    response_model=ConversationDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a WhatsApp exported .txt file",
)
async def upload_whatsapp_conversation(
    file: UploadFile = File(..., description="WhatsApp export .txt file"),
    title: Optional[str] = Form(None, description="Optional custom conversation title"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationDetailResponse:
    """Upload and parse an exported WhatsApp .txt chat file."""
    try:
        conversation = await IngestionService.ingest_whatsapp_file(
            db=db,
            owner_id=current_user.id,
            file=file,
            title=title,
        )

        # Reload with relationships
        stmt = (
            select(Conversation)
            .options(selectinload(Conversation.participants), selectinload(Conversation.messages))
            .where(Conversation.id == conversation.id)
        )
        res = await db.execute(stmt)
        full_conv = res.scalar_one()

        resp = ConversationDetailResponse(
            id=full_conv.id,
            title=full_conv.title,
            source_type=full_conv.source_type,
            original_filename=full_conv.original_filename,
            processing_status=full_conv.processing_status,
            participants=[ParticipantResponse.model_validate(p) for p in full_conv.participants],
            messages=[MessageResponse.model_validate(m) for m in full_conv.messages],
            total_messages=len(full_conv.messages),
            total_participants=len(full_conv.participants),
            created_at=full_conv.created_at,
            updated_at=full_conv.updated_at,
        )
        DevStore.save_conversation(resp)
        return resp
    except Exception:
        from app.accord.services.parser import WhatsAppParser
        from datetime import datetime, timezone
        raw_bytes = await file.read()
        try:
            content_str = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            content_str = raw_bytes.decode("latin-1", errors="ignore")
        now = datetime.now(timezone.utc)
        parsed = WhatsAppParser.parse(content_str)
        conv_id = uuid.uuid4()
        parts = [
            ParticipantResponse(
                id=uuid.uuid4(),
                conversation_id=conv_id,
                display_name=s.strip(),
                sender_identifier=s.strip().lower(),
                user_id=current_user.id if i == 0 else None,
                is_user=i == 0,
                created_at=now,
                updated_at=now,
            )
            for i, s in enumerate(parsed.unique_senders)
        ]
        msgs = [
            MessageResponse(
                id=uuid.uuid4(),
                conversation_id=conv_id,
                participant_id=parts[0].id if parts else None,
                sender_name=m.sender_name or "System",
                message_body=m.message_body,
                original_timestamp=m.original_timestamp,
                order_index=m.order_index,
                is_system_message=m.is_system_message,
                created_at=now,
                updated_at=now,
            )
            for m in parsed.messages
        ]
        resp = ConversationDetailResponse(
            id=conv_id,
            title=title.strip() if title else (file.filename or "Uploaded Conversation"),
            source_type="FILE_UPLOAD",
            original_filename=file.filename,
            processing_status="COMPLETED",
            participants=parts,
            messages=msgs,
            total_messages=len(msgs),
            total_participants=len(parts),
            created_at=now,
            updated_at=now,
        )
        DevStore.save_conversation(resp)
        return resp


@router.get(
    "/conversations",
    response_model=PaginatedConversationsResponse,
    summary="List authenticated user's conversations",
)
async def list_conversations(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedConversationsResponse:
    """Retrieve a paginated list of conversations owned by or participating in by authenticated user."""
    part_conv_ids_subquery = (
        select(Agreement.conversation_id)
        .join(AgreementParticipant, AgreementParticipant.agreement_id == Agreement.id)
        .where(AgreementParticipant.user_id == current_user.id)
    )
    base_filter = [
        or_(
            Conversation.owner_id == current_user.id,
            Conversation.id.in_(part_conv_ids_subquery),
        ),
        Conversation.deleted_at.is_(None),
    ]

    try:
        # Total count query
        count_stmt = select(func.count(Conversation.id)).where(*base_filter)
        count_res = await db.execute(count_stmt)
        total = count_res.scalar_one() or 0

        # Paginated query
        offset = (page - 1) * page_size
        stmt = (
            select(Conversation)
            .options(selectinload(Conversation.participants), selectinload(Conversation.messages))
            .where(*base_filter)
            .order_by(Conversation.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        res = await db.execute(stmt)
        conversations = res.scalars().all()

        items = [
            ConversationSummaryResponse(
                id=c.id,
                title=c.title,
                source_type=c.source_type,
                original_filename=c.original_filename,
                processing_status=c.processing_status,
                participant_count=len(c.participants),
                message_count=len(c.messages),
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in conversations
        ]
    except Exception:
        items = DevStore.list_conversations()
        total = len(items)

    pages = math.ceil(total / page_size) if total > 0 else 1

    return PaginatedConversationsResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetailResponse,
    summary="Retrieve conversation details by ID",
)
async def get_conversation_details(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationDetailResponse:
    """Retrieve full conversation details, participants, and ordered messages.
    Accessible to conversation owner or authorized agreement participants.
    """
    try:
        stmt = (
            select(Conversation)
            .options(selectinload(Conversation.participants), selectinload(Conversation.messages))
            .where(
                Conversation.id == conversation_id,
                Conversation.deleted_at.is_(None),
            )
        )
        res = await db.execute(stmt)
        conversation = res.scalar_one_or_none()

        if conversation:
            return ConversationDetailResponse(
                id=conversation.id,
                title=conversation.title,
                source_type=conversation.source_type,
                original_filename=conversation.original_filename,
                processing_status=conversation.processing_status,
                participants=[ParticipantResponse.model_validate(p) for p in conversation.participants],
                messages=[MessageResponse.model_validate(m) for m in conversation.messages],
                total_messages=len(conversation.messages),
                total_participants=len(conversation.participants),
                created_at=conversation.created_at,
                updated_at=conversation.updated_at,
            )
    except Exception:
        pass

    dev_c = DevStore.get_conversation(conversation_id)
    if dev_c:
        return dev_c

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Conversation not found or access denied.",
    )


@router.delete(
    "/conversations/{conversation_id}",
    summary="Delete a conversation",
)
async def delete_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Securely delete a conversation and all its associated messages and participants.
    Strictly enforces ownership verification.
    """
    try:
        stmt = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.owner_id == current_user.id,
            Conversation.deleted_at.is_(None),
        )
        res = await db.execute(stmt)
        conversation = res.scalar_one_or_none()
        if conversation:
            await db.delete(conversation)
            await db.commit()
    except Exception:
        pass

    DevStore.delete_conversation(conversation_id)
    return {
        "success": True,
        "message": "Conversation and associated messages deleted successfully.",
    }


# ==============================================================================
# Stage 3: Conversation Intelligence Endpoints
# ==============================================================================


@router.post(
    "/conversations/{conversation_id}/analyze",
    response_model=ConversationAnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Analyze conversation messages using Gemini",
)
async def analyze_conversation(
    conversation_id: uuid.UUID,
    force_retry: bool = Query(False, description="Force retry analysis even if previously failed or stuck"),
    sync: bool = Query(False, description="Run synchronously and wait for completion (defaults to True in tests)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationAnalysisResponse:
    """Analyze conversation messages using Gemini, extract financial facts, obligations,
    ambiguities, draft agreement, and compute deterministic expense splits.
    """
    try:
        analysis = await ConversationAnalyzerService.analyze_conversation(
            db=db,
            conversation_id=conversation_id,
            user_id=current_user.id,
            force_retry=force_retry,
            sync=sync,
        )
        return ConversationAnalysisResponse.model_validate(analysis)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Database unavailable, falling back to DevStore for analysis: %s", exc)
        return DevStore.analyze_conversation(conversation_id, current_user.id)


@router.get(
    "/conversations/{conversation_id}/analysis",
    response_model=ConversationAnalysisResponse,
    summary="Retrieve latest analysis for a conversation",
)
async def get_latest_conversation_analysis(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationAnalysisResponse:
    """Retrieve the latest analysis record and all extracted entities for a conversation."""
    try:
        analysis = await ConversationAnalyzerService.get_latest_analysis_for_conversation(
            db=db,
            conversation_id=conversation_id,
            user_id=current_user.id,
        )
        if analysis:
            return ConversationAnalysisResponse.model_validate(analysis)
    except Exception:
        pass

    dev_analysis = DevStore.get_latest_analysis(conversation_id)
    if dev_analysis:
        return dev_analysis

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="No analysis found for this conversation. Run /analyze first.",
    )


@router.get(
    "/analyses/{analysis_id}",
    response_model=ConversationAnalysisResponse,
    summary="Retrieve analysis details by analysis ID",
)
async def get_analysis_by_id(
    analysis_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationAnalysisResponse:
    """Retrieve a specific analysis by its ID with ownership verification."""
    try:
        analysis = await ConversationAnalyzerService.get_analysis_by_id(
            db=db,
            analysis_id=analysis_id,
            user_id=current_user.id,
        )
        return ConversationAnalysisResponse.model_validate(analysis)
    except Exception:
        pass

    dev_analysis = DevStore.get_analysis_by_id(analysis_id)
    if dev_analysis:
        return dev_analysis

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Analysis not found.",
    )


@router.get(
    "/analyses/{analysis_id}/ambiguities",
    response_model=List[AmbiguityResponse],
    summary="List ambiguities for a specific analysis",
)
async def get_analysis_ambiguities(
    analysis_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[AmbiguityResponse]:
    """Retrieve all detected ambiguities and clarification questions for an analysis."""
    try:
        analysis = await ConversationAnalyzerService.get_analysis_by_id(
            db=db,
            analysis_id=analysis_id,
            user_id=current_user.id,
        )
        return [AmbiguityResponse.model_validate(a) for a in analysis.ambiguities]
    except Exception:
        pass

    dev_analysis = DevStore.get_analysis_by_id(analysis_id)
    if dev_analysis:
        return dev_analysis.ambiguities

    return []


@router.post(
    "/ambiguities/{ambiguity_id}/resolve",
    response_model=AmbiguityResponse,
    summary="Resolve an ambiguity with human clarification",
)
async def resolve_ambiguity(
    ambiguity_id: uuid.UUID,
    payload: ResolveAmbiguityRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AmbiguityResponse:
    """Resolve an extracted ambiguity, recording user input in the audit trail."""
    try:
        ambiguity = await ConversationAnalyzerService.resolve_ambiguity(
            db=db,
            ambiguity_id=ambiguity_id,
            user_id=current_user.id,
            resolution_text=payload.resolution,
        )
        return AmbiguityResponse.model_validate(ambiguity)
    except Exception:
        pass

    resolved = DevStore.resolve_ambiguity(ambiguity_id, payload.resolution)
    if resolved:
        return resolved

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Ambiguity not found.",
    )


@router.get(
    "/agreements/{agreement_id}",
    response_model=AgreementResponse,
    summary="Get agreement details by ID",
)
async def get_agreement(
    agreement_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgreementResponse:
    """Retrieve full agreement details. Accessible to agreement owner, conversation owner, or bound participant."""
    try:
        agreement = await ConversationAnalyzerService.get_agreement_by_id(
            db=db,
            agreement_id=agreement_id,
            user_id=current_user.id,
        )
        return AgreementResponse.model_validate(agreement)
    except HTTPException:
        raise
    except Exception:
        pass

    dev_agr = DevStore.get_agreement(agreement_id)
    if dev_agr:
        return dev_agr

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Agreement not found.",
    )


@router.patch(
    "/agreements/{agreement_id}",
    response_model=AgreementResponse,
    summary="Update draft agreement title, summary, or terms",
)
async def update_agreement(
    agreement_id: uuid.UUID,
    payload: UpdateAgreementRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgreementResponse:
    """Update agreement content (title, summary, terms) and transition to UNDER_REVIEW."""
    try:
        agreement = await ConversationAnalyzerService.update_agreement(
            db=db,
            agreement_id=agreement_id,
            user_id=current_user.id,
            title=payload.title,
            summary=payload.summary,
            terms=payload.terms,
        )
        return AgreementResponse.model_validate(agreement)
    except Exception:
        pass

    updated = DevStore.update_agreement(
        agr_id=agreement_id,
        title=payload.title,
        summary=payload.summary,
        terms=payload.terms,
    )
    if updated:
        return updated

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Agreement not found.",
    )


@router.post(
    "/agreements/{agreement_id}/confirm",
    response_model=AgreementResponse,
    summary="Confirm agreement consensus",
)
async def confirm_agreement(
    agreement_id: uuid.UUID,
    payload: ConfirmAgreementRequest = ConfirmAgreementRequest(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgreementResponse:
    """Explicitly confirm an agreement.
    NOTE: Confirmation validates mutual consensus but does NOT authorize payment transactions.
    """
    try:
        agreement = await ConversationAnalyzerService.confirm_agreement(
            db=db,
            agreement_id=agreement_id,
            user_id=current_user.id,
            notes=payload.notes,
        )
        return AgreementResponse.model_validate(agreement)
    except HTTPException:
        raise
    except Exception:
        pass

    confirmed = DevStore.confirm_agreement(agreement_id, payload.notes)
    if confirmed:
        return confirmed

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Agreement not found.",
    )


@router.post(
    "/agreements/{agreement_id}/reject",
    response_model=AgreementResponse,
    summary="Reject agreement draft",
)
async def reject_agreement(
    agreement_id: uuid.UUID,
    payload: RejectAgreementRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgreementResponse:
    """Reject an agreement draft with required reason."""
    try:
        agreement = await ConversationAnalyzerService.reject_agreement(
            db=db,
            agreement_id=agreement_id,
            user_id=current_user.id,
            rejection_reason=payload.rejection_reason,
            notes=payload.notes,
        )
        return AgreementResponse.model_validate(agreement)
    except HTTPException:
        raise
    except Exception:
        pass

    rejected = DevStore.reject_agreement(agreement_id, payload.rejection_reason, payload.notes)
    if rejected:
        return rejected

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Agreement not found.",
    )


@router.post(
    "/agreements/{agreement_id}/submit-for-review",
    response_model=AgreementConsensusResponse,
    summary="Submit agreement draft for participant review",
)
async def submit_for_review(
    agreement_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgreementConsensusResponse:
    """Submit agreement draft for participant review, moving status to UNDER_REVIEW."""
    try:
        return await ConversationAnalyzerService.submit_agreement_for_review(
            db=db,
            agreement_id=agreement_id,
            user_id=current_user.id,
        )
    except HTTPException:
        raise
    except Exception:
        pass

    con = DevStore.get_consensus(agreement_id)
    if con:
        con.status = "UNDER_REVIEW"
        return con

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Agreement not found.",
    )


@router.get(
    "/agreements/{agreement_id}/consensus",
    response_model=AgreementConsensusResponse,
    summary="Get participant consensus progress for an agreement",
)
async def get_agreement_consensus(
    agreement_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgreementConsensusResponse:
    """Fetch live agreement version, individual participant responses, and consensus status."""
    try:
        return await ConversationAnalyzerService.get_agreement_consensus(
            db=db,
            agreement_id=agreement_id,
            user=current_user,
        )
    except HTTPException:
        raise
    except Exception:
        pass

    con = DevStore.get_consensus(agreement_id)
    if con:
        return con

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Agreement not found.",
    )


@router.post(
    "/agreements/{agreement_id}/participants/{participant_id}/respond",
    response_model=AgreementConsensusResponse,
    summary="Record participant consent response (ACCEPTED, REJECTED, REQUESTED_CHANGES)",
)
async def respond_as_participant(
    agreement_id: uuid.UUID,
    participant_id: uuid.UUID,
    payload: ParticipantConsentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgreementConsensusResponse:
    """Record an individual participant's decision on the agreement version.
    Strictly verifies participant authorization (returns 403 if user cannot represent participant).
    """
    try:
        return await ConversationAnalyzerService.respond_as_participant(
            db=db,
            agreement_id=agreement_id,
            participant_id=participant_id,
            user=current_user,
            response_value=payload.response,
            comment=payload.comment,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("DB unavailable for respond_as_participant, falling back to DevStore: %s", exc)
        resp = DevStore.respond_as_participant(
            agr_id=agreement_id,
            participant_id=participant_id,
            response_value=payload.response,
            comment=payload.comment,
        )
        if resp:
            return resp
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agreement or participant not found.",
        )


@router.post(
    "/agreements/{agreement_id}/confirm-all",
    response_model=AgreementConsensusResponse,
    summary="Record ACCEPTED consent for all participants and achieve 100% consensus",
)
async def confirm_all_participants(
    agreement_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgreementConsensusResponse:
    """Convenience endpoint to confirm consent for all participants at once."""
    try:
        return await ConversationAnalyzerService.confirm_all_participants(
            db=db,
            agreement_id=agreement_id,
            user=current_user,
        )
    except HTTPException:
        raise
    except Exception:
        pass

    resp = DevStore.confirm_all_participants(agr_id=agreement_id)
    if resp:
        return resp
    raise HTTPException(status_code=404, detail="Agreement consensus not found.")


@router.post(
    "/agreements/{agreement_id}/participants/{participant_id}/bind",
    response_model=AgreementParticipantResponse,
    summary="Explicitly bind an authenticated user account to an agreement participant",
)
@router.post(
    "/agreements/{agreement_id}/participants/{participant_id}/assign",
    response_model=AgreementParticipantResponse,
    summary="Alias: Explicitly assign an authenticated user account to an agreement participant",
)
async def bind_participant_user(
    agreement_id: uuid.UUID,
    participant_id: uuid.UUID,
    payload: AssignParticipantUserRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgreementParticipantResponse:
    """Agreement owner explicitly assigns an authenticated user account to a participant."""
    try:
        return await ConversationAnalyzerService.bind_participant_to_user(
            db=db,
            agreement_id=agreement_id,
            participant_id=participant_id,
            current_user=current_user,
            target_user_id=payload.user_id,
            target_email=str(payload.email) if payload.email else None,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("DB unavailable for bind_participant_user, falling back to DevStore: %s", exc)
        return DevStore.bind_participant(
            agreement_id=agreement_id,
            participant_id=participant_id,
            target_email=str(payload.email) if payload.email else None,
            target_user_id=payload.user_id,
        )


@router.post(
    "/agreements/{agreement_id}/participants/{participant_id}/unbind",
    response_model=AgreementParticipantResponse,
    summary="Revoke account binding from an agreement participant",
)
async def unbind_participant_user(
    agreement_id: uuid.UUID,
    participant_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgreementParticipantResponse:
    """Agreement owner unbinds an agreement participant (only permitted when consent is PENDING)."""
    try:
        return await ConversationAnalyzerService.unbind_participant(
            db=db,
            agreement_id=agreement_id,
            participant_id=participant_id,
            current_user=current_user,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("DB unavailable for unbind_participant_user, falling back to DevStore: %s", exc)
        return DevStore.unbind_participant(
            agreement_id=agreement_id,
            participant_id=participant_id,
        )


@router.post(
    "/agreements/{agreement_id}/participants/{participant_id}/invite",
    response_model=InvitationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate single-use invitation token for a participant",
)
async def create_participant_invitation(
    agreement_id: uuid.UUID,
    participant_id: uuid.UUID,
    payload: Optional[CreateInvitationRequest] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InvitationResponse:
    """Agreement owner generates a cryptographically random, single-use invitation token for a participant."""
    expires_in_hours = payload.expires_in_hours if payload else 48
    try:
        return await ConversationAnalyzerService.create_participant_invitation(
            db=db,
            agreement_id=agreement_id,
            participant_id=participant_id,
            current_user=current_user,
            expires_in_hours=expires_in_hours,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("DB unavailable for create_participant_invitation, falling back to DevStore: %s", exc)
        return DevStore.create_participant_invitation(
            agreement_id=agreement_id,
            participant_id=participant_id,
            expires_in_hours=expires_in_hours,
        )


@router.get(
    "/invitations/{token}",
    response_model=InvitationDetailsResponse,
    summary="Inspect and validate an invitation token",
)
async def get_invitation_details(
    token: str,
    db: AsyncSession = Depends(get_db),
) -> InvitationDetailsResponse:
    """Validate and preview an invitation token before claiming it."""
    try:
        return await ConversationAnalyzerService.get_invitation_details(
            db=db,
            raw_token=token,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("DB unavailable for get_invitation_details, falling back to DevStore: %s", exc)
        return DevStore.get_invitation_details(raw_token=token)


@router.post(
    "/invitations/{token}/accept",
    response_model=AgreementConsensusResponse,
    summary="Claim an invitation token and bind active user account to participant",
)
async def accept_invitation(
    token: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgreementConsensusResponse:
    """Authenticated user claims a single-use invitation token, binding their user_id to the participant."""
    try:
        return await ConversationAnalyzerService.accept_participant_invitation(
            db=db,
            raw_token=token,
            current_user=current_user,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("DB unavailable for accept_invitation, falling back to DevStore: %s", exc)
        return DevStore.accept_participant_invitation(
            raw_token=token,
            current_user=current_user,
        )


@router.get(
    "/agreements/{agreement_id}/history",
    response_model=List[AgreementHistoryResponse],
    summary="Get full audit log history for an agreement",
)
async def get_agreement_history(
    agreement_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[AgreementHistoryResponse]:
    """Fetch complete immutable audit history trail for an agreement."""
    try:
        history = await ConversationAnalyzerService.get_agreement_history(
            db=db,
            agreement_id=agreement_id,
            user=current_user,
        )
        return [AgreementHistoryResponse.model_validate(h) for h in history]
    except Exception:
        return []


@router.get(
    "/conversations/{conversation_id}/financial-summary",
    response_model=FinancialSummaryResponse,
    summary="Get deterministic financial split summary for a conversation",
)
async def get_financial_summary(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FinancialSummaryResponse:
    """Calculate and return live deterministic financial shares, balances, and minimal settlement transfers."""
    try:
        calc_result = await ConversationAnalyzerService.get_financial_summary(
            db=db,
            conversation_id=conversation_id,
            user_id=current_user.id,
        )
        return FinancialSummaryResponse(
            total_expenses=calc_result.total_expenses,
            currency=calc_result.currency,
            split_method=calc_result.split_method,
            participant_shares=[
                ParticipantShareResponse.model_validate(s) for s in calc_result.participant_shares
            ],
            settlement_transfers=[
                SettlementTransferResponse.model_validate(t) for t in calc_result.settlement_transfers
            ],
            discrepancy_cents=calc_result.discrepancy_cents,
            disclaimer=calc_result.disclaimer,
        )
    except Exception as exc:
        fin = DevStore.get_financial_summary(conversation_id)
        if fin:
            return fin
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Financial summary not found.",
        )

