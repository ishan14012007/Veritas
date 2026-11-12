import re
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.core.config import get_settings


class PastedTextRequest(BaseModel):
    """Payload for submitting pasted conversation text."""
    content: str = Field(min_length=1, description="Raw conversation transcript")
    title: Optional[str] = Field(default=None, max_length=200, description="Optional custom conversation title")


class ParticipantResponse(BaseModel):
    """Participant representation."""
    id: uuid.UUID
    display_name: str
    sender_identifier: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    """Normalized message representation."""
    id: uuid.UUID
    participant_id: Optional[uuid.UUID] = None
    sender_name: Optional[str] = None
    message_body: str
    original_timestamp: Optional[datetime] = None
    order_index: int
    is_system_message: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationSummaryResponse(BaseModel):
    """Concise conversation summary for listings."""
    id: uuid.UUID
    title: str
    source_type: str
    original_filename: Optional[str] = None
    processing_status: str
    participant_count: int
    message_count: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationDetailResponse(BaseModel):
    """Detailed conversation view including participants and messages."""
    id: uuid.UUID
    title: str
    source_type: str
    original_filename: Optional[str] = None
    processing_status: str
    participants: List[ParticipantResponse]
    messages: List[MessageResponse]
    total_messages: int
    total_participants: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaginatedConversationsResponse(BaseModel):
    """Paginated list of conversations."""
    items: List[ConversationSummaryResponse]
    total: int
    page: int
    page_size: int
    pages: int


# ==============================================================================
# Stage 3 Conversation Intelligence Schemas
# ==============================================================================

class FinancialFactResponse(BaseModel):
    id: uuid.UUID
    amount: Decimal
    currency: str
    classification: str
    payer_name: Optional[str] = None
    recipient_name: Optional[str] = None
    description: str
    evidence_quote: str
    message_indices: List[int]
    confidence: float
    is_explicit: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ObligationResponse(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    debtor_name: Optional[str] = None
    creditor_name: Optional[str] = None
    amount: Optional[Decimal] = None
    currency: str
    due_date_raw: Optional[str] = None
    due_date: Optional[datetime] = None
    status: str
    is_freelance_milestone: bool
    deliverable: Optional[str] = None
    condition: Optional[str] = None
    evidence_quote: str
    message_indices: List[int]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SplitShareResponse(BaseModel):
    id: uuid.UUID
    participant_name: str
    share_value: Decimal
    computed_amount: Decimal
    paid_amount: Decimal
    net_balance: Decimal
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExpenseSplitResponse(BaseModel):
    id: uuid.UUID
    title: str
    total_amount: Decimal
    currency: str
    split_method: str
    proposer_name: Optional[str] = None
    status: str
    shares: List[SplitShareResponse] = []
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AmbiguityResponse(BaseModel):
    id: uuid.UUID
    ambiguity_type: str
    description: str
    severity: str
    clarification_question: str
    suggested_options: List[str]
    related_participants: List[str]
    evidence_quote: str
    message_indices: List[int]
    status: str
    resolution_text: Optional[str] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgreementParticipantResponse(BaseModel):
    id: uuid.UUID
    participant_id: Optional[uuid.UUID] = None
    user_id: Optional[uuid.UUID] = None
    name: str
    stated_role: str
    consent_status: str = "PENDING"
    responded_version: Optional[int] = None
    responded_at: Optional[datetime] = None
    comment: Optional[str] = None
    is_confirmed: bool
    confirmed_at: Optional[datetime] = None
    bound_at: Optional[datetime] = None
    bound_method: Optional[str] = None
    bound_user_email: Optional[str] = None
    bound_user_name: Optional[str] = None
    has_pending_invitation: bool = False
    created_at: datetime
    can_respond: bool = False

    model_config = ConfigDict(from_attributes=True)


class AgreementVersionResponse(BaseModel):
    id: uuid.UUID
    agreement_id: uuid.UUID
    version: int
    title: str
    summary: str
    terms: List[str]
    total_value: Decimal
    currency: str
    created_by_user_id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgreementHistoryResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    action: str
    notes: Optional[str] = None
    changes: Dict[str, Any] = {}
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgreementResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    analysis_id: Optional[uuid.UUID] = None
    title: str
    summary: str
    version: int = 1
    status: str
    total_value: Decimal
    currency: str
    terms: List[str]
    is_confirmed: bool
    confirmed_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    rejection_notes: Optional[str] = None
    submitted_for_review_at: Optional[datetime] = None
    participants: List[AgreementParticipantResponse] = []
    versions: List[AgreementVersionResponse] = []
    obligations: List[ObligationResponse] = []
    expense_splits: List[ExpenseSplitResponse] = []
    history: List[AgreementHistoryResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgreementConsensusResponse(BaseModel):
    agreement_id: uuid.UUID
    version: int
    status: str
    is_confirmed: bool
    total_participants: int
    accepted_count: int
    pending_count: int
    rejected_count: int
    changes_requested_count: int
    consensus_achieved: bool
    status_message: str
    participants: List[AgreementParticipantResponse]
    pending_participant_names: List[str]

    model_config = ConfigDict(from_attributes=True)


class ParticipantConsentRequest(BaseModel):
    response: str = Field(description="ACCEPTED, REJECTED, or REQUESTED_CHANGES")
    comment: Optional[str] = Field(default=None, max_length=1000)


class ConversationAnalysisResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    status: str
    ai_model: str
    overall_summary: Optional[str] = None
    error_message: Optional[str] = None
    execution_duration_ms: Optional[int] = None
    financial_facts: List[FinancialFactResponse] = []
    ambiguities: List[AmbiguityResponse] = []
    agreements: List[AgreementResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ResolveAmbiguityRequest(BaseModel):
    resolution: str = Field(min_length=1, description="Selected option or custom resolution text")


class UpdateAgreementRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    summary: Optional[str] = Field(default=None)
    terms: Optional[List[str]] = Field(default=None)


class ConfirmAgreementRequest(BaseModel):
    notes: Optional[str] = Field(default=None, description="Optional confirmation notes")


class RejectAgreementRequest(BaseModel):
    rejection_reason: str = Field(min_length=2, description="Reason for rejecting the agreement draft")
    notes: Optional[str] = Field(default=None)


class ParticipantShareResponse(BaseModel):
    participant_name: str
    paid_amount: Decimal
    fair_share: Decimal
    net_balance: Decimal
    status: str

    model_config = ConfigDict(from_attributes=True)


class SettlementTransferResponse(BaseModel):
    from_participant: str
    to_participant: str
    amount: Decimal
    currency: str = "USD"

    model_config = ConfigDict(from_attributes=True)


class FinancialSummaryResponse(BaseModel):
    total_expenses: Decimal
    currency: str
    split_method: str
    participant_shares: List[ParticipantShareResponse]
    settlement_transfers: List[SettlementTransferResponse]
    discrepancy_cents: Decimal
    disclaimer: str

    model_config = ConfigDict(from_attributes=True)


class AssignParticipantUserRequest(BaseModel):
    user_id: Optional[uuid.UUID] = None
    email: Optional[str] = None

    @field_validator("email")
    @classmethod
    def validate_assignee_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        clean = v.strip().lower()
        if not clean:
            return None
        settings = get_settings()
        if settings.ENVIRONMENT != "production" and (clean.endswith(".local") or clean.endswith(".test")):
            if re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", clean):
                return clean
            raise ValueError("Invalid development email address format")
        try:
            validated = validate_email(clean, check_deliverability=False)
            return validated.normalized
        except EmailNotValidError as e:
            raise ValueError(str(e))


class CreateInvitationRequest(BaseModel):
    expires_in_hours: int = Field(default=48, ge=1, le=720)


class InvitationResponse(BaseModel):
    id: uuid.UUID
    agreement_participant_id: uuid.UUID
    agreement_id: uuid.UUID
    participant_name: str
    invitation_token: str
    invitation_url: str
    expires_at: datetime
    is_claimed: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InvitationDetailsResponse(BaseModel):
    id: uuid.UUID
    agreement_id: uuid.UUID
    agreement_title: str
    participant_id: uuid.UUID
    participant_name: str
    stated_role: str
    expires_at: datetime
    is_expired: bool
    is_claimed: bool
    is_valid: bool

    model_config = ConfigDict(from_attributes=True)

