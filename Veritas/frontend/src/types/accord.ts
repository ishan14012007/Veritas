export interface Participant {
  id: string;
  display_name: string;
  sender_identifier: string;
  created_at: string;
}

export interface Message {
  id: string;
  participant_id: string | null;
  sender_name: string | null;
  message_body: string;
  original_timestamp: string | null;
  order_index: number;
  is_system_message: boolean;
  created_at: string;
}

export interface ConversationSummary {
  id: string;
  title: string;
  source_type: 'PASTED_TEXT' | 'WHATSAPP_EXPORT';
  original_filename: string | null;
  processing_status: string;
  participant_count: number;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface ConversationDetail {
  id: string;
  title: string;
  source_type: 'PASTED_TEXT' | 'WHATSAPP_EXPORT';
  original_filename: string | null;
  processing_status: string;
  participants: Participant[];
  messages: Message[];
  total_messages: number;
  total_participants: number;
  created_at: string;
  updated_at: string;
}

export interface PaginatedConversations {
  items: ConversationSummary[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

// Stage 3 Conversation Intelligence Types

export interface FinancialFact {
  id: string;
  amount: number;
  currency: string;
  classification: 'PAID' | 'PROMISED' | 'REQUESTED' | 'PROPOSED' | 'MENTIONED' | 'UNCLEAR';
  payer_name: string | null;
  recipient_name: string | null;
  description: string;
  evidence_quote: string;
  message_indices: number[];
  confidence: number;
  is_explicit: boolean;
  created_at: string;
}

export interface Obligation {
  id: string;
  title: string;
  description: string;
  debtor_name: string | null;
  creditor_name: string | null;
  amount: number | null;
  currency: string;
  due_date_raw: string | null;
  due_date: string | null;
  status: string;
  is_freelance_milestone: boolean;
  deliverable: string | null;
  condition: string | null;
  evidence_quote: string;
  message_indices: number[];
  created_at: string;
}

export interface SplitShare {
  id: string;
  participant_name: string;
  share_value: number;
  computed_amount: number;
  paid_amount: number;
  net_balance: number;
  status: string;
  created_at: string;
}

export interface ExpenseSplit {
  id: string;
  title: string;
  total_amount: number;
  currency: string;
  split_method: string;
  proposer_name: string | null;
  status: string;
  shares: SplitShare[];
  created_at: string;
}

export interface Ambiguity {
  id: string;
  ambiguity_type: string;
  description: string;
  severity: 'HIGH' | 'MEDIUM' | 'LOW';
  clarification_question: string;
  suggested_options: string[];
  related_participants: string[];
  evidence_quote: string;
  message_indices: number[];
  status: 'UNRESOLVED' | 'RESOLVED' | 'DISMISSED';
  resolution_text: string | null;
  resolved_at: string | null;
  created_at: string;
}

export interface AgreementParticipant {
  id: string;
  participant_id?: string | null;
  user_id?: string | null;
  name: string;
  stated_role: string;
  consent_status: 'PENDING' | 'ACCEPTED' | 'REJECTED' | 'REQUESTED_CHANGES';
  responded_version: number | null;
  responded_at: string | null;
  comment: string | null;
  is_confirmed: boolean;
  confirmed_at: string | null;
  bound_at?: string | null;
  bound_method?: string | null;
  bound_user_email?: string | null;
  bound_user_name?: string | null;
  has_pending_invitation?: boolean;
  created_at: string;
  can_respond?: boolean;
}

export interface ParticipantInvitationResponse {
  id: string;
  agreement_participant_id: string;
  agreement_id: string;
  participant_name: string;
  invitation_token: string;
  invitation_url: string;
  expires_at: string;
  is_claimed: boolean;
  created_at: string;
}

export interface InvitationDetailsResponse {
  id: string;
  agreement_id: string;
  agreement_title: string;
  participant_id: string;
  participant_name: string;
  stated_role: string;
  expires_at: string;
  is_expired: boolean;
  is_claimed: boolean;
  is_valid: boolean;
}

export interface AgreementVersion {
  id: string;
  agreement_id: string;
  version: number;
  title: string;
  summary: string;
  terms: string[];
  total_value: number;
  currency: string;
  created_by_user_id: string;
  created_at: string;
}

export interface AgreementConsensus {
  agreement_id: string;
  version: number;
  status: 'DRAFT' | 'UNDER_REVIEW' | 'PARTIALLY_ACCEPTED' | 'CONFIRMED' | 'REJECTED' | 'CHANGES_REQUESTED';
  is_confirmed: boolean;
  total_participants: number;
  accepted_count: number;
  pending_count: number;
  rejected_count: number;
  changes_requested_count: number;
  consensus_achieved: boolean;
  status_message: string;
  participants: AgreementParticipant[];
  pending_participant_names: string[];
}

export interface AgreementHistory {
  id: string;
  user_id: string;
  action: string;
  notes: string | null;
  changes: Record<string, any>;
  created_at: string;
}

export interface Agreement {
  id: string;
  conversation_id: string;
  analysis_id: string | null;
  title: string;
  summary: string;
  version: number;
  status: 'DRAFT' | 'UNDER_REVIEW' | 'PARTIALLY_ACCEPTED' | 'CONFIRMED' | 'REJECTED' | 'CHANGES_REQUESTED';
  total_value: number;
  currency: string;
  terms: string[];
  is_confirmed: boolean;
  confirmed_at: string | null;
  rejection_reason: string | null;
  rejection_notes: string | null;
  submitted_for_review_at: string | null;
  participants: AgreementParticipant[];
  versions?: AgreementVersion[];
  obligations: Obligation[];
  expense_splits: ExpenseSplit[];
  history: AgreementHistory[];
  created_at: string;
  updated_at: string;
}

export interface ConversationAnalysis {
  id: string;
  conversation_id: string;
  status: 'QUEUED' | 'PROCESSING' | 'COMPLETED' | 'FAILED';
  ai_model: string;
  overall_summary: string | null;
  error_message: string | null;
  execution_duration_ms: number | null;
  financial_facts: FinancialFact[];
  ambiguities: Ambiguity[];
  agreements: Agreement[];
  created_at: string;
  updated_at: string;
}

export interface ParticipantNetShare {
  participant_name: string;
  paid_amount: number;
  fair_share: number;
  net_balance: number;
  status: string;
}

export interface SettlementTransfer {
  from_participant: string;
  to_participant: string;
  amount: number;
  currency: string;
}

export interface FinancialSummary {
  total_expenses: number;
  currency: string;
  split_method: string;
  participant_shares: ParticipantNetShare[];
  settlement_transfers: SettlementTransfer[];
  discrepancy_cents: number;
  disclaimer: string;
}

// Stage 5 WhatsApp Business Integration Types

export interface WhatsAppAccount {
  id: string;
  user_id: string;
  phone_number: string;
  display_name: string | null;
  provider: string;
  phone_number_id: string | null;
  business_account_id: string | null;
  connection_status: 'PENDING_VERIFICATION' | 'CONNECTED' | 'DISCONNECTED';
  consent_status: 'OPTED_IN' | 'OPTED_OUT';
  verification_token?: string | null;
  verified_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface WhatsAppMessage {
  id: string;
  user_id?: string | null;
  account_id: string | null;
  conversation_id: string | null;
  accord_message_id: string | null;
  provider_message_id: string;
  sender_number: string;
  recipient_number: string;
  direction: 'INBOUND' | 'OUTBOUND';
  message_type: 'TEXT' | 'TEMPLATE' | 'INTERACTIVE' | 'MEDIA';
  content: string;
  raw_payload?: Record<string, any> | null;
  provider: string;
  delivery_status: 'QUEUED' | 'SENT' | 'DELIVERED' | 'READ' | 'FAILED';
  error_code?: string | null;
  error_message?: string | null;
  is_mock: boolean;
  created_at: string;
  updated_at: string;
}

export interface WhatsAppStatus {
  provider: string;
  mock_mode: boolean;
  phone_number_id: string;
  webhook_url: string;
  linked_accounts_count: number;
  total_messages_count: number;
  registered_templates: string[];
}

