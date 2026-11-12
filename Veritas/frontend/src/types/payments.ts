export interface PayPalOrder {
  id: string;
  payment_request_id: string;
  paypal_order_id: string;
  amount: number | string;
  currency: string;
  status: string;
  approval_url?: string | null;
  client_id: string;
  is_mock?: boolean;
  original_amount?: number | string | null;
  original_currency?: string | null;
  exchange_rate?: number | string | null;
  is_converted?: boolean;
}

export interface PaymentCapture {
  id: string;
  payment_request_id: string;
  paypal_order_id: string;
  paypal_capture_id: string;
  amount: number | string;
  currency: string;
  status: string;
  paypal_fee?: number | string | null;
  net_amount?: number | string | null;
  captured_at: string;
}

export interface PaymentRefund {
  id: string;
  payment_capture_id: string;
  payment_request_id: string;
  paypal_refund_id: string;
  amount: number | string;
  currency: string;
  status: string;
  reason?: string | null;
  created_at: string;
}

export interface PaymentHistoryEntry {
  id: string;
  payment_request_id: string;
  action: string;
  from_status?: string | null;
  to_status: string;
  performed_by_user_id?: string | null;
  details: Record<string, any>;
  created_at: string;
}

export interface PaymentRequest {
  id: string;
  agreement_id: string;
  agreement_version: number;
  obligation_id: string;
  debtor_participant_id?: string | null;
  creditor_participant_id?: string | null;
  debtor_name: string;
  creditor_name: string;
  receiver_merchant_account: string;
  amount: number | string;
  currency: string;
  status: string;
  due_date?: string | null;
  paypal_order_id?: string | null;
  created_by_user_id?: string | null;
  created_at: string;
  updated_at: string;
  can_pay: boolean;
  can_cancel: boolean;
  can_refund: boolean;
  is_mock?: boolean;
  active_order?: PayPalOrder | null;
  latest_capture?: PaymentCapture | null;
  paypal_amount?: number | string | null;
  paypal_currency?: string | null;
  exchange_rate?: number | string | null;
  is_converted?: boolean;
}

export interface ObligationPaymentSummary {
  obligation_id: string;
  title: string;
  description: string;
  debtor_name?: string | null;
  creditor_name?: string | null;
  amount: number | string;
  currency: string;
  obligation_status: string;
  is_settled: boolean;
  settled_amount?: number | string;
  outstanding_amount?: number | string;
  is_eligible_for_payment: boolean;
  ineligibility_reason?: string | null;
  payment_request?: PaymentRequest | null;
}

export interface AgreementSettlementSummary {
  agreement_id: string;
  agreement_title: string;
  agreement_version: number;
  agreement_status: string;
  consensus_achieved: boolean;
  total_obligations_amount: number | string;
  currency: string;
  total_completed_amount: number | string;
  total_pending_amount: number | string;
  total_failed_amount: number | string;
  outstanding_balance: number | string;
  settlement_status: 'UNSETTLED' | 'PARTIALLY_SETTLED' | 'FULLY_SETTLED';
  obligations: ObligationPaymentSummary[];
  payment_requests: PaymentRequest[];
}

