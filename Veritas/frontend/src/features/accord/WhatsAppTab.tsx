import React, { useState, useEffect } from 'react';
import type { WhatsAppAccount, WhatsAppMessage, WhatsAppStatus } from '../../types/accord';
import {
  getWhatsAppStatus,
  linkWhatsAppNumber,
  verifyWhatsAppNumber,
  listWhatsAppAccounts,
  unlinkWhatsAppAccount,
  sendWhatsAppMessage,
  listWhatsAppMessages,
  simulateMockInboundWhatsApp,
  simulateMockStatusUpdate,
} from '../../lib/api';

interface WhatsAppTabProps {
  token: string | null;
  onOpenConversation?: (conversationId: string) => void;
}

export const WhatsAppTab: React.FC<WhatsAppTabProps> = ({ token, onOpenConversation }) => {
  const [status, setStatus] = useState<WhatsAppStatus | null>(null);
  const [accounts, setAccounts] = useState<WhatsAppAccount[]>([]);
  const [messages, setMessages] = useState<WhatsAppMessage[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Phone Linking form
  const [linkPhone, setLinkPhone] = useState<string>('+14155550199');
  const [linkDisplayName, setLinkDisplayName] = useState<string>('My WhatsApp Phone');
  const [pendingVerificationToken, setPendingVerificationToken] = useState<string | null>(null);
  const [verifyTokenInput, setVerifyTokenInput] = useState<string>('');
  const [verifyPhoneTarget, setVerifyPhoneTarget] = useState<string>('');

  // Simulator: Inbound Message
  const [inboundFrom, setInboundFrom] = useState<string>('+14155550199');
  const [inboundContent, setInboundContent] = useState<string>(
    'Alice, Bob, and I agreed to split the cabin rental equally. Bob paid $450 and Alice paid $180.'
  );
  const [inboundTriggerAnalysis, setInboundTriggerAnalysis] = useState<boolean>(true);
  const [simulatingInbound, setSimulatingInbound] = useState<boolean>(false);

  // Outbound Message
  const [outboundRecipient, setOutboundRecipient] = useState<string>('+14155550199');
  const [outboundType, setOutboundType] = useState<'TEXT' | 'TEMPLATE'>('TEXT');
  const [outboundTemplate, setOutboundTemplate] = useState<string>('accord_agreement_review_v1');
  const [outboundText, setOutboundText] = useState<string>('Hello! Please review your pending ACCORD agreement.');
  const [sendingOutbound, setSendingOutbound] = useState<boolean>(false);

  // Live Meta Instructions toggle
  const [showMetaGuide, setShowMetaGuide] = useState<boolean>(false);

  const fetchAllData = async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const [statusRes, accountsRes, messagesRes] = await Promise.all([
        getWhatsAppStatus(token).catch(() => null),
        listWhatsAppAccounts(token).catch(() => []),
        listWhatsAppMessages(token).catch(() => []),
      ]);
      if (statusRes) setStatus(statusRes);
      setAccounts(accountsRes || []);
      setMessages(messagesRes || []);
    } catch (err: any) {
      setError(err?.message || 'Failed to load WhatsApp data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAllData();
  }, [token]);

  const handleLinkPhone = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !linkPhone.trim()) return;
    setError(null);
    setSuccessMsg(null);
    try {
      const res = await linkWhatsAppNumber(token, {
        phone_number: linkPhone.trim(),
        display_name: linkDisplayName.trim() || undefined,
      });
      setVerifyPhoneTarget(res.phone_number);
      if (res.verification_token) {
        setPendingVerificationToken(res.verification_token);
        setVerifyTokenInput(res.verification_token);
      }
      setSuccessMsg(`Linking initiated for ${res.phone_number}. Please verify.`);
      await fetchAllData();
    } catch (err: any) {
      setError(err?.message || 'Failed to initiate linking');
    }
  };

  const handleVerifyPhone = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !verifyPhoneTarget || !verifyTokenInput.trim()) return;
    setError(null);
    setSuccessMsg(null);
    try {
      await verifyWhatsAppNumber(token, {
        phone_number: verifyPhoneTarget,
        verification_token: verifyTokenInput.trim(),
      });
      setSuccessMsg(`Phone ${verifyPhoneTarget} successfully verified & opted in!`);
      setPendingVerificationToken(null);
      setVerifyTokenInput('');
      setVerifyPhoneTarget('');
      await fetchAllData();
    } catch (err: any) {
      setError(err?.message || 'Verification failed');
    }
  };

  const handleUnlink = async (accountId: string) => {
    if (!token) return;
    if (!window.confirm('Are you sure you want to unlink this WhatsApp number?')) return;
    setError(null);
    setSuccessMsg(null);
    try {
      await unlinkWhatsAppAccount(token, accountId);
      setSuccessMsg('WhatsApp account unlinked successfully.');
      await fetchAllData();
    } catch (err: any) {
      setError(err?.message || 'Failed to unlink account');
    }
  };

  const handleSimulateInbound = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !inboundFrom.trim() || !inboundContent.trim()) return;
    setSimulatingInbound(true);
    setError(null);
    setSuccessMsg(null);
    try {
      const res = await simulateMockInboundWhatsApp(token, {
        from_number: inboundFrom.trim(),
        content: inboundContent.trim(),
        trigger_analysis: inboundTriggerAnalysis,
      });
      setSuccessMsg(
        `Inbound message simulated successfully! Delivered ${res.length} message(s).`
      );
      await fetchAllData();
      if (res.length > 0 && res[0].conversation_id && onOpenConversation) {
        onOpenConversation(res[0].conversation_id);
      }
    } catch (err: any) {
      setError(err?.message || 'Failed to simulate inbound message');
    } finally {
      setSimulatingInbound(false);
    }
  };

  const handleSendOutbound = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !outboundRecipient.trim()) return;
    setSendingOutbound(true);
    setError(null);
    setSuccessMsg(null);
    try {
      await sendWhatsAppMessage(token, {
        recipient_number: outboundRecipient.trim(),
        message_type: outboundType,
        template_name: outboundType === 'TEMPLATE' ? outboundTemplate : undefined,
        content: outboundType === 'TEXT' ? outboundText : undefined,
      });
      setSuccessMsg('Outbound WhatsApp message dispatched successfully!');
      await fetchAllData();
    } catch (err: any) {
      setError(err?.message || 'Failed to dispatch outbound message');
    } finally {
      setSendingOutbound(false);
    }
  };

  const handleSimulateStatus = async (
    providerMessageId: string,
    targetStatus: 'DELIVERED' | 'READ' | 'FAILED'
  ) => {
    if (!token) return;
    try {
      await simulateMockStatusUpdate(token, {
        provider_message_id: providerMessageId,
        status: targetStatus,
        error_code: targetStatus === 'FAILED' ? '131056' : undefined,
        error_message: targetStatus === 'FAILED' ? 'Delivery timed out' : undefined,
      });
      await fetchAllData();
    } catch (err: any) {
      setError(err?.message || 'Failed to update status');
    }
  };

  return (
    <div className="space-y-6 pt-2">
      {/* 1. System Status & Header Banner */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400 font-bold text-lg">
              WA
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-semibold text-slate-100 text-base">
                  WhatsApp Business Cloud Platform
                </h3>
                <span
                  className={`text-[10px] px-2 py-0.5 rounded-full font-semibold uppercase tracking-wider ${
                    status?.mock_mode
                      ? 'bg-amber-500/10 text-amber-300 border border-amber-500/30'
                      : 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/30'
                  }`}
                >
                  {status?.mock_mode ? 'Mock Mode Active' : 'Meta Live Connected'}
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Multi-channel transcript ingestion, participant identity linking, and notification dispatch
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={fetchAllData}
              disabled={loading}
              className="px-3 py-1.5 text-xs bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-lg transition-colors font-medium flex items-center gap-1.5"
            >
              🔄 Refresh
            </button>
            <button
              onClick={() => setShowMetaGuide(!showMetaGuide)}
              className="px-3 py-1.5 text-xs bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 rounded-lg transition-colors font-medium"
            >
              {showMetaGuide ? 'Hide Meta Guide' : 'Meta Live Config Guide'}
            </button>
          </div>
        </div>

        {/* Status Metrics Strip */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4 text-xs">
          <div className="bg-slate-950/60 border border-slate-800/80 rounded-lg p-3">
            <div className="text-slate-400 font-medium">Provider Engine</div>
            <div className="text-slate-200 font-semibold mt-1 uppercase text-sm">
              {status?.provider || 'Mock'}
            </div>
          </div>
          <div className="bg-slate-950/60 border border-slate-800/80 rounded-lg p-3">
            <div className="text-slate-400 font-medium">Linked Phone Numbers</div>
            <div className="text-emerald-400 font-semibold mt-1 text-sm">
              {status?.linked_accounts_count ?? accounts.length}
            </div>
          </div>
          <div className="bg-slate-950/60 border border-slate-800/80 rounded-lg p-3">
            <div className="text-slate-400 font-medium">Total Messages Logged</div>
            <div className="text-blue-400 font-semibold mt-1 text-sm">
              {status?.total_messages_count ?? messages.length}
            </div>
          </div>
          <div className="bg-slate-950/60 border border-slate-800/80 rounded-lg p-3">
            <div className="text-slate-400 font-medium">Webhook Endpoint</div>
            <div className="text-slate-300 font-mono mt-1 text-[11px] truncate" title={status?.webhook_url}>
              {status?.webhook_url || '/api/v1/whatsapp/webhook'}
            </div>
          </div>
        </div>

        {/* Live Meta Guide Accordion */}
        {showMetaGuide && (
          <div className="mt-4 p-4 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-300 space-y-2">
            <div className="font-semibold text-emerald-400 text-sm flex items-center gap-1.5">
              <span>🚀</span> Meta WhatsApp Cloud API Setup Guide
            </div>
            <p className="text-slate-400">
              When Meta developer verification SMS OTP arrives and production access is activated, update{' '}
              <code className="text-emerald-300 bg-slate-900 px-1 py-0.5 rounded">backend/.env</code> with:
            </p>
            <pre className="bg-slate-900 p-3 rounded-lg border border-slate-800 text-[11px] text-slate-200 overflow-x-auto font-mono">
              {`WHATSAPP_PROVIDER=meta
WHATSAPP_MOCK_MODE=false
MOCK_WHATSAPP=false
WHATSAPP_PHONE_NUMBER_ID=<Your_Meta_Phone_Number_ID>
WHATSAPP_BUSINESS_ACCOUNT_ID=<Your_Meta_WABA_ID>
WHATSAPP_ACCESS_TOKEN=<Permanent_System_User_Token>
WHATSAPP_APP_SECRET=<Meta_App_Secret_For_HMAC_Verification>
WHATSAPP_VERIFY_TOKEN=<Custom_Webhook_Verify_Secret>`}
            </pre>
            <p className="text-[11px] text-slate-400">
              Note: The system strictly validates credentials in live mode and will never silently drop back to mock.
            </p>
          </div>
        )}
      </div>

      {/* Global Alerts */}
      {error && (
        <div className="p-3 bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs rounded-lg flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-rose-400 hover:text-rose-200 text-sm font-bold">
            ×
          </button>
        </div>
      )}
      {successMsg && (
        <div className="p-3 bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 text-xs rounded-lg flex items-center justify-between">
          <span>{successMsg}</span>
          <button onClick={() => setSuccessMsg(null)} className="text-emerald-400 hover:text-emerald-200 text-sm font-bold">
            ×
          </button>
        </div>
      )}

      {/* 2. Phone Linking & Connected Accounts Strip */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Linking Box */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm space-y-4">
          <h4 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
            <span>📱</span> Link WhatsApp Phone Number
          </h4>
          <p className="text-xs text-slate-400">
            Explicitly link your WhatsApp phone to your VERITAS identity with cryptographic token verification.
          </p>

          <form onSubmit={handleLinkPhone} className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">
                E.164 Phone Number
              </label>
              <input
                type="text"
                value={linkPhone}
                onChange={(e) => setLinkPhone(e.target.value)}
                placeholder="+14155550199"
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-100 focus:outline-none focus:border-emerald-500 font-mono"
                required
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">
                Display Label
              </label>
              <input
                type="text"
                value={linkDisplayName}
                onChange={(e) => setLinkDisplayName(e.target.value)}
                placeholder="Work Mobile / Personal"
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-100 focus:outline-none focus:border-emerald-500"
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="w-full py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-semibold transition-colors disabled:opacity-50"
            >
              Request Single-Use Verification Token
            </button>
          </form>

          {/* Verification Code Box (Visible when linking initiated) */}
          {(pendingVerificationToken || verifyPhoneTarget) && (
            <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-lg space-y-2 mt-3">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-amber-300">
                  Verification Code Generated (Simulated OTP)
                </span>
                <span className="font-mono text-emerald-400 font-bold bg-slate-900 px-2 py-0.5 rounded">
                  {pendingVerificationToken || 'Sent'}
                </span>
              </div>
              <form onSubmit={handleVerifyPhone} className="flex gap-2">
                <input
                  type="text"
                  value={verifyTokenInput}
                  onChange={(e) => setVerifyTokenInput(e.target.value)}
                  placeholder="Enter 6-digit code"
                  className="flex-1 bg-slate-950 border border-amber-600/40 rounded-lg px-3 py-1.5 text-xs text-slate-100 font-mono focus:outline-none"
                  required
                />
                <button
                  type="submit"
                  className="px-4 py-1.5 bg-amber-600 hover:bg-amber-500 text-slate-950 font-bold rounded-lg text-xs transition-colors"
                >
                  Verify
                </button>
              </form>
            </div>
          )}
        </div>

        {/* Connected Accounts List */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm space-y-4">
          <h4 className="text-sm font-semibold text-slate-200 flex items-center justify-between">
            <span className="flex items-center gap-2">
              <span>🔗</span> Linked WhatsApp Accounts ({accounts.length})
            </span>
          </h4>

          {accounts.length === 0 ? (
            <div className="py-8 text-center text-xs text-slate-500 border border-dashed border-slate-800 rounded-lg">
              No WhatsApp phone numbers linked yet. Link a number to route incoming chats to ACCORD.
            </div>
          ) : (
            <div className="space-y-2.5 max-h-[260px] overflow-y-auto pr-1">
              {accounts.map((acc) => (
                <div
                  key={acc.id}
                  className="p-3 bg-slate-950/70 border border-slate-800 rounded-lg flex items-center justify-between text-xs hover:border-slate-700 transition-colors"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-semibold text-slate-200">
                        {acc.phone_number}
                      </span>
                      <span
                        className={`text-[10px] px-2 py-0.5 rounded font-medium ${
                          acc.connection_status === 'CONNECTED'
                            ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                            : 'bg-amber-500/10 text-amber-300 border border-amber-500/30'
                        }`}
                      >
                        {acc.connection_status}
                      </span>
                      <span
                        className={`text-[10px] px-2 py-0.5 rounded font-medium ${
                          acc.consent_status === 'OPTED_IN'
                            ? 'bg-blue-500/10 text-blue-300 border border-blue-500/30'
                            : 'bg-slate-800 text-slate-400'
                        }`}
                      >
                        {acc.consent_status}
                      </span>
                    </div>
                    {acc.display_name && (
                      <div className="text-slate-400 text-[11px] mt-0.5">
                        {acc.display_name}
                      </div>
                    )}
                  </div>
                  <button
                    onClick={() => handleUnlink(acc.id)}
                    className="px-2.5 py-1 text-[11px] bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/30 rounded transition-colors"
                  >
                    Unlink
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 3. Interactive WhatsApp Simulator (Inbound & Outbound) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Inbound Simulator */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
              <span>📥</span> Simulate Inbound Message
            </h4>
            <span className="text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-2 py-0.5 rounded font-medium">
              Routes to ACCORD
            </span>
          </div>
          <p className="text-xs text-slate-400">
            Injects an incoming WhatsApp message payload matching the Meta Cloud API webhook schema.
          </p>

          <form onSubmit={handleSimulateInbound} className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">
                Sender Number (Linked Phone)
              </label>
              <input
                type="text"
                value={inboundFrom}
                onChange={(e) => setInboundFrom(e.target.value)}
                placeholder="+14155550199"
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-100 font-mono focus:outline-none focus:border-emerald-500"
                required
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">
                Message Transcript Content
              </label>
              <textarea
                rows={3}
                value={inboundContent}
                onChange={(e) => setInboundContent(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2.5 text-xs text-slate-100 focus:outline-none focus:border-emerald-500 font-sans"
                placeholder="Enter financial transaction claim or conversation details..."
                required
              />
            </div>
            <div className="flex items-center gap-2 text-xs text-slate-300">
              <input
                type="checkbox"
                id="triggerAnalysisCheck"
                checked={inboundTriggerAnalysis}
                onChange={(e) => setInboundTriggerAnalysis(e.target.checked)}
                className="rounded bg-slate-950 border-slate-700 text-emerald-500 focus:ring-emerald-500"
              />
              <label htmlFor="triggerAnalysisCheck" className="cursor-pointer">
                Automatically trigger Gemini Conversation Intelligence extraction
              </label>
            </div>
            <button
              type="submit"
              disabled={simulatingInbound}
              className="w-full py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-semibold transition-colors disabled:opacity-50"
            >
              {simulatingInbound ? 'Ingesting via ACCORD Pipeline...' : 'Simulate Inbound WhatsApp'}
            </button>
          </form>
        </div>

        {/* Outbound Dispatcher */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
              <span>📤</span> Dispatch Outbound Notification
            </h4>
            <span className="text-[10px] bg-blue-500/10 text-blue-300 border border-blue-500/20 px-2 py-0.5 rounded font-medium">
              Meta Templates
            </span>
          </div>
          <p className="text-xs text-slate-400">
            Dispatch business notifications or chat replies to participants via Meta Graph API or Mock.
          </p>

          <form onSubmit={handleSendOutbound} className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Recipient Number
                </label>
                <input
                  type="text"
                  value={outboundRecipient}
                  onChange={(e) => setOutboundRecipient(e.target.value)}
                  placeholder="+14155550199"
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-100 font-mono focus:outline-none focus:border-blue-500"
                  required
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Message Type
                </label>
                <select
                  value={outboundType}
                  onChange={(e) => setOutboundType(e.target.value as any)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-100 focus:outline-none focus:border-blue-500"
                >
                  <option value="TEXT">Freeform Text</option>
                  <option value="TEMPLATE">Business Template</option>
                </select>
              </div>
            </div>

            {outboundType === 'TEMPLATE' ? (
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Approved WhatsApp Template
                </label>
                <select
                  value={outboundTemplate}
                  onChange={(e) => setOutboundTemplate(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-100 font-mono focus:outline-none focus:border-blue-500"
                >
                  {(status?.registered_templates || [
                    'accord_agreement_review_v1',
                    'accord_consensus_confirmed_v1',
                    'accord_payment_request_v1',
                    'accord_payment_received_v1',
                    'accord_settlement_completed_v1',
                  ]).map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
              </div>
            ) : (
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Message Text
                </label>
                <textarea
                  rows={3}
                  value={outboundText}
                  onChange={(e) => setOutboundText(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2.5 text-xs text-slate-100 focus:outline-none focus:border-blue-500 font-sans"
                  placeholder="Enter message text..."
                  required
                />
              </div>
            )}

            <button
              type="submit"
              disabled={sendingOutbound}
              className="w-full py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-semibold transition-colors disabled:opacity-50"
            >
              {sendingOutbound ? 'Dispatching...' : 'Dispatch WhatsApp Message'}
            </button>
          </form>
        </div>
      </div>

      {/* 4. Message Log & Status Progression Audit */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
            <span>📋</span> WhatsApp Message History & Delivery Audit ({messages.length})
          </h4>
          <span className="text-[11px] text-slate-400">
            Real-time status tracking & WAMID tracing
          </span>
        </div>

        {messages.length === 0 ? (
          <div className="py-8 text-center text-xs text-slate-500 border border-dashed border-slate-800 rounded-lg">
            No WhatsApp messages recorded yet. Simulate an inbound message or send an outbound notification above.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-800 text-slate-400 font-medium">
                  <th className="py-2.5 px-3">Direction</th>
                  <th className="py-2.5 px-3">From / To</th>
                  <th className="py-2.5 px-3">Type</th>
                  <th className="py-2.5 px-3">Content</th>
                  <th className="py-2.5 px-3">Delivery Status</th>
                  <th className="py-2.5 px-3">Provider ID (WAMID)</th>
                  <th className="py-2.5 px-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {messages.map((m) => (
                  <tr key={m.id} className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-2.5 px-3">
                      <span
                        className={`text-[10px] px-2 py-0.5 rounded font-semibold ${
                          m.direction === 'INBOUND'
                            ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                            : 'bg-blue-500/10 text-blue-300 border border-blue-500/30'
                        }`}
                      >
                        {m.direction}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 font-mono text-slate-300 text-[11px]">
                      {m.direction === 'INBOUND' ? m.sender_number : m.recipient_number}
                    </td>
                    <td className="py-2.5 px-3 text-slate-400 text-[11px]">
                      {m.message_type}
                    </td>
                    <td className="py-2.5 px-3 text-slate-200 max-w-xs truncate" title={m.content}>
                      {m.content}
                    </td>
                    <td className="py-2.5 px-3">
                      <span
                        className={`text-[10px] px-2 py-0.5 rounded font-medium ${
                          m.delivery_status === 'READ'
                            ? 'bg-indigo-500/10 text-indigo-300 border border-indigo-500/30'
                            : m.delivery_status === 'DELIVERED'
                            ? 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/30'
                            : m.delivery_status === 'SENT'
                            ? 'bg-blue-500/10 text-blue-300 border border-blue-500/30'
                            : m.delivery_status === 'FAILED'
                            ? 'bg-rose-500/10 text-rose-300 border border-rose-500/30'
                            : 'bg-slate-800 text-slate-400'
                        }`}
                      >
                        {m.delivery_status}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 font-mono text-[10px] text-slate-400 truncate max-w-[120px]" title={m.provider_message_id}>
                      {m.provider_message_id}
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      {status?.mock_mode && m.direction === 'OUTBOUND' && (
                        <div className="flex items-center justify-end gap-1.5">
                          {m.delivery_status === 'SENT' && (
                            <button
                              onClick={() => handleSimulateStatus(m.provider_message_id, 'DELIVERED')}
                              className="px-2 py-0.5 text-[10px] bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 rounded transition-colors"
                            >
                              Deliver
                            </button>
                          )}
                          {m.delivery_status !== 'READ' && (
                            <button
                              onClick={() => handleSimulateStatus(m.provider_message_id, 'READ')}
                              className="px-2 py-0.5 text-[10px] bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 rounded transition-colors"
                            >
                              Read
                            </button>
                          )}
                        </div>
                      )}
                      {m.conversation_id && (
                        <button
                          onClick={() => onOpenConversation && onOpenConversation(m.conversation_id!)}
                          className="text-[10px] text-blue-400 hover:text-blue-300 underline ml-2"
                        >
                          View Chat
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

