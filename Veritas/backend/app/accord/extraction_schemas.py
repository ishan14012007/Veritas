from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AIExtractedParticipant(BaseModel):
    """Participant extracted from conversation."""
    name: str = Field(description="Participant name or identifier as stated in the conversation")
    stated_role: Optional[str] = Field(default=None, description="Explicit role if stated (e.g. Organizer, Payer, Freelancer, Client)")
    relationship_summary: Optional[str] = Field(default=None, description="Relationship context supported by evidence")


class AIFinancialFact(BaseModel):
    """Financial claim or fact extracted from conversation."""
    amount: float = Field(description="Numerical amount")
    currency: str = Field(default="USD", description="Currency code (e.g. USD, EUR, GBP)")
    classification: str = Field(
        description="One of: PAID (already transferred), PROMISED (will pay), REQUESTED (asked for payment), PROPOSED (suggested split), MENTIONED (cited without obligation), UNCLEAR"
    )
    payer_name: Optional[str] = Field(default=None, description="Person who paid or would pay")
    recipient_name: Optional[str] = Field(default=None, description="Person or entity receiving the funds")
    description: str = Field(description="Description of what the expense or payment was for")
    evidence_quote: str = Field(description="Direct verbatim quote from transcript supporting this fact")
    message_indices: List[int] = Field(default_factory=list, description="0-indexed order indices of supporting messages")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score from 0.0 to 1.0")
    is_explicit: bool = Field(default=True, description="True if explicitly stated, False if inferred")
    is_personal: bool = Field(default=False, description="True if this is a personal loan, personal borrowing, or 1-on-1 debt that should be excluded from shared group trip expenses")


class AIObligation(BaseModel):
    """Obligation, deliverable, or commitment extracted from conversation."""
    title: str = Field(description="Short title of the obligation or commitment")
    description: str = Field(description="Full description of the commitment")
    debtor_name: Optional[str] = Field(default=None, description="Party responsible for fulfilling the obligation")
    creditor_name: Optional[str] = Field(default=None, description="Beneficiary party")
    amount: Optional[float] = Field(default=None, description="Monetary value if financial")
    currency: str = Field(default="USD", description="Currency code")
    due_date_raw: Optional[str] = Field(default=None, description="Deadline or due date as mentioned in text")
    evidence_quote: str = Field(description="Direct verbatim quote from transcript")
    message_indices: List[int] = Field(default_factory=list, description="0-indexed order indices of supporting messages")
    is_freelance_milestone: bool = Field(default=False, description="True if this is a freelance milestone or project deliverable")
    deliverable: Optional[str] = Field(default=None, description="Deliverable or work product expected")
    condition: Optional[str] = Field(default=None, description="Condition or dependency required before fulfillment")


class AISuggestedShare(BaseModel):
    """Share for a participant in an expense split."""
    participant_name: str
    share_amount: Optional[float] = None
    share_weight: Optional[float] = None
    share_percentage: Optional[float] = None
    is_fronted: bool = False


class AIExpenseSplitProposal(BaseModel):
    """Expense-sharing proposal or calculation found in the conversation."""
    title: str = Field(description="Title of the expense sharing proposal")
    total_amount: float = Field(description="Total amount to be divided")
    currency: str = Field(default="USD", description="Currency code")
    split_method: str = Field(default="EQUAL", description="One of: EQUAL, PERCENTAGE, CUSTOM, UNEQUAL")
    proposer_name: Optional[str] = Field(default=None, description="Person who proposed the split")
    payer_names: List[str] = Field(default_factory=list, description="Persons who fronted the initial payment")
    suggested_shares: List[AISuggestedShare] = Field(default_factory=list, description="Proposed shares per participant")
    evidence_quote: str = Field(description="Direct verbatim quote proposing or discussing the split")
    message_indices: List[int] = Field(default_factory=list, description="0-indexed order indices of supporting messages")


class AIAgreement(BaseModel):
    """Overall agreement or consensus extracted from conversation."""
    title: str = Field(description="Title of agreement")
    summary: str = Field(description="Concise summary of consensus reached or proposed")
    status: str = Field(default="DRAFT", description="One of: ACCEPTED, PROPOSED, PENDING, DISPUTED")
    key_terms: List[str] = Field(default_factory=list, description="Bullet points of key agreed terms")
    evidence_quote: str = Field(description="Direct verbatim quotes supporting consensus")
    message_indices: List[int] = Field(default_factory=list, description="0-indexed order indices of supporting messages")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class AIAmbiguity(BaseModel):
    """Uncertainty, contradiction, or missing term requiring human clarification."""
    ambiguity_type: str = Field(
        description="One of: CONFLICTING_AMOUNTS, UNCLEAR_PARTICIPANT, MISSING_CURRENCY, UNCLEAR_RECIPIENT, CONFLICTING_DEADLINE, UNCERTAIN_AGREEMENT_STATUS, AMBIGUOUS_SPLIT_INSTRUCTION, PAYMENT_VS_PROMISE"
    )
    description: str = Field(description="Detailed explanation of the ambiguity or contradiction")
    severity: str = Field(default="MEDIUM", description="One of: HIGH, MEDIUM, LOW")
    clarification_question: str = Field(description="Actionable question to ask human reviewer to resolve this ambiguity")
    suggested_options: List[str] = Field(default_factory=list, description="Possible resolution choices")
    related_participant_names: List[str] = Field(default_factory=list, description="Participants involved in the ambiguity")
    evidence_quote: str = Field(description="Verbatim excerpt where ambiguity appears")
    message_indices: List[int] = Field(default_factory=list, description="0-indexed order indices of supporting messages")


class AIConversationExtractionResponse(BaseModel):
    """Root structured extraction response from Gemini."""
    overall_summary: str = Field(description="Comprehensive summary of the conversation context, participants, and goals")
    participants: List[AIExtractedParticipant] = Field(default_factory=list)
    agreements: List[AIAgreement] = Field(default_factory=list)
    financial_facts: List[AIFinancialFact] = Field(default_factory=list)
    obligations: List[AIObligation] = Field(default_factory=list)
    expense_split_proposals: List[AIExpenseSplitProposal] = Field(default_factory=list)
    ambiguities: List[AIAmbiguity] = Field(default_factory=list)

