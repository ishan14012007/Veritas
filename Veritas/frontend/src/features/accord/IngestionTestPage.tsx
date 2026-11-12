import React, { useState, useEffect, useRef, useMemo } from 'react';
import { Link } from 'react-router-dom';
import {
  Upload,
  FileText,
  Send,
  Trash2,
  RefreshCw,
  MessageSquare,
  AlertCircle,
  CheckCircle2,
  Clock,
  ArrowLeft,
  LogIn,
  LogOut,
  Sparkles,
  Bot,
  Check,
  X,
  Edit2,
  DollarSign,
  HelpCircle,
  Scale,
  Shield,
  ChevronRight,
  UserCheck,
  Users,
  AlertTriangle,
  History,
  SendHorizontal,
  MessageCircle,
  Copy,
  Key,
  Link2,
  ShieldCheck,
  UserX,
  Mail,
  CreditCard,
  Receipt,
  RotateCcw,
} from 'lucide-react';
import {
  loginUser,
  registerUser,
  ingestPastedText,
  uploadWhatsAppFile,
  listConversations,
  getConversation,
  deleteConversation,
  analyzeConversation,
  getLatestAnalysis,
  getAgreement,
  resolveAmbiguity,
  updateAgreement,
  getFinancialSummary,
  submitAgreementForReview,
  getAgreementConsensus,
  respondAsParticipant,
  getAgreementHistory,
  bindParticipantUser,
  unbindParticipantUser,
  createParticipantInvitation,
  acceptInvitation,
  createPaymentRequest,
  cancelPaymentRequest,
  refundPayPalCapture,
  getAgreementSettlementSummary,
  getPaymentRequestHistory,
} from '../../lib/api';
import type {
  Agreement,
  AgreementConsensus,
  AgreementHistory,
  ConversationAnalysis,
  ConversationDetail,
  ConversationSummary,
  FinancialSummary,
  ParticipantInvitationResponse,
} from '../../types/accord';
import type {
  AgreementSettlementSummary,
  ObligationPaymentSummary,
  PaymentCapture,
  PaymentHistoryEntry,
  PaymentRequest,
} from '../../types/payments';
import { PayPalCheckoutModal } from './PayPalCheckoutModal';
import { WhatsAppTab } from './WhatsAppTab';

const SAMPLE_WHATSAPP_CHAT = `[12/03/24, 14:30:15] Messages and calls are end-to-end encrypted. No one outside of this chat can read them.
[12/03/24, 14:32:00] Alice Smith: Hey everyone! Let's settle the cabin rental expenses from this weekend.
[12/03/24, 14:33:10] Bob Miller: Sounds good. I paid $450 directly to the host for the 3 nights.
[12/03/24, 14:34:25] Alice Smith: Great. And I bought groceries and drinks totaling $180 at Safeway.
Here is the breakdown:
- Food: $130
- Drinks: $50
[12/03/24, 14:35:40] Charlie Davis: Thanks guys. I didn't pay for anything yet so I will cover my fair share!
[12/03/24, 14:36:15] Bob Miller: <Media omitted>
[12/03/24, 14:37:00] Bob Miller: That's the booking receipt above. So total is $630 split 3 ways, which is $210 each.`;

export const getCurrencySymbol = (currency?: string | null): string => {
  if (!currency) return '$';
  const c = currency.trim().toUpperCase();
  if (c === 'INR' || c === 'RS' || c === 'RUPEE' || c === 'RUPEES') return '₹';
  if (c === 'EUR') return '€';
  if (c === 'GBP') return '£';
  if (c === 'JPY') return '¥';
  return '$';
};

export const formatMoney = (amount: number | string | undefined | null, currency?: string | null): string => {
  const num = Number(amount || 0);
  const sym = getCurrencySymbol(currency);
  return `${sym}${num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
};

export const IngestionTestPage: React.FC = () => {
  // Auth state
  const [token, setToken] = useState<string>(() => localStorage.getItem('veritas_test_token') || '');
  const [userEmail, setUserEmail] = useState<string>(() => localStorage.getItem('veritas_test_email') || '');
  const [authEmail, setAuthEmail] = useState<string>('tester@veritas.local');
  const [authPassword, setAuthPassword] = useState<string>('TesterPass123!');
  const [authLoading, setAuthLoading] = useState<boolean>(false);
  const [authError, setAuthError] = useState<string | null>(null);

  // Ingestion form state
  const [activeTab, setActiveTab] = useState<'paste' | 'upload'>('paste');
  const [pastedText, setPastedText] = useState<string>('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [customTitle, setCustomTitle] = useState<string>('');
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState<string | null>(null);

  // Ingested & History state
  const [currentConversation, setCurrentConversation] = useState<ConversationDetail | null>(null);
  const [recentConversations, setRecentConversations] = useState<ConversationSummary[]>([]);
  const [loadingHistory, setLoadingHistory] = useState<boolean>(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Stage 3 Intelligence state
  const [activeSubTab, setActiveSubTab] = useState<
    'agreement' | 'settlement' | 'whatsapp' | 'financial' | 'facts' | 'ambiguities' | 'messages'
  >('agreement');
  const [analysis, setAnalysis] = useState<ConversationAnalysis | null>(null);
  const [selectedAgreement, setSelectedAgreement] = useState<Agreement | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState<boolean>(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [financialSummary, setFinancialSummary] = useState<FinancialSummary | null>(null);

  // Agreement edit state
  const [isEditingAgreement, setIsEditingAgreement] = useState<boolean>(false);
  const [editTitle, setEditTitle] = useState<string>('');
  const [editSummary, setEditSummary] = useState<string>('');
  const [editTerms, setEditTerms] = useState<string[]>([]);
  const [newTermInput, setNewTermInput] = useState<string>('');
  const [savingAgreement, setSavingAgreement] = useState<boolean>(false);

  // Ambiguity resolution state
  const [customResolution, setCustomResolution] = useState<{ [id: string]: string }>({});
  const [resolvingId, setResolvingId] = useState<string | null>(null);

  // Stage 3.1 Consensus state
  const [consensus, setConsensus] = useState<AgreementConsensus | null>(null);
  const [agreementHistoryList, setAgreementHistoryList] = useState<AgreementHistory[]>([]);
  const [submittingReview, setSubmittingReview] = useState<boolean>(false);
  const [activeRespondingParticipantId, setActiveRespondingParticipantId] = useState<string | null>(null);
  const [responseActionType, setResponseActionType] = useState<'ACCEPTED' | 'REJECTED' | 'REQUESTED_CHANGES'>('ACCEPTED');
  const [responseComment, setResponseComment] = useState<string>('');
  const [submittingResponse, setSubmittingResponse] = useState<boolean>(false);

  // Stage 3.2 Secure Identity Binding & Invitations state
  const [assigningPartId, setAssigningPartId] = useState<string | null>(null);
  const [assignEmail, setAssignEmail] = useState<string>('');
  const [bindingLoading, setBindingLoading] = useState<boolean>(false);
  const [generatedInvitations, setGeneratedInvitations] = useState<{ [participantId: string]: ParticipantInvitationResponse }>({});
  const [claimTokenInput, setClaimTokenInput] = useState<string>('');
  const [claimingInvitation, setClaimingInvitation] = useState<boolean>(false);
  const [showClaimModal, setShowClaimModal] = useState<boolean>(false);
  const [copiedTokenId, setCopiedTokenId] = useState<string | null>(null);

  // Stage 4 PayPal Payments & Settlement state
  const [settlementSummary, setSettlementSummary] = useState<AgreementSettlementSummary | null>(null);
  const [loadingSettlement, setLoadingSettlement] = useState<boolean>(false);
  const [settlementError, setSettlementError] = useState<string | null>(null);
  const [activePaymentRequestForCheckout, setActivePaymentRequestForCheckout] = useState<PaymentRequest | null>(null);
  const [isPaymentModalOpen, setIsPaymentModalOpen] = useState<boolean>(false);
  const [isReviewModalOpen, setIsReviewModalOpen] = useState<boolean>(false);
  const [selectedObligationForPayment, setSelectedObligationForPayment] = useState<ObligationPaymentSummary | null>(null);
  const [creatingPaymentReq, setCreatingPaymentReq] = useState<boolean>(false);
  const [paymentHistoryModalReq, setPaymentHistoryModalReq] = useState<PaymentRequest | null>(null);
  const [paymentHistoryList, setPaymentHistoryList] = useState<PaymentHistoryEntry[]>([]);
  const [loadingPaymentHistory, setLoadingPaymentHistory] = useState<boolean>(false);
  const [refundingCapture, setRefundingCapture] = useState<PaymentCapture | null>(null);
  const [refundReason, setRefundReason] = useState<string>('');
  const [refundingLoading, setRefundingLoading] = useState<boolean>(false);
  const [cancellingRequestId, setCancellingRequestId] = useState<string | null>(null);

  // Polling ref
  const pollingRef = useRef<any>(null);

  const stopPolling = () => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  };

  useEffect(() => {
    return () => {
      stopPolling();
    };
  }, []);

  // Load history when token is available
  useEffect(() => {
    if (token) {
      loadHistory();
    } else {
      setRecentConversations([]);
      setCurrentConversation(null);
      setSelectedAgreement(null);
      setAnalysis(null);
      setFinancialSummary(null);
      setConsensus(null);
      setAgreementHistoryList([]);
    }
  }, [token]);

  const saveAuth = (newToken: string, email: string) => {
    setToken(newToken);
    setUserEmail(email);
    localStorage.setItem('veritas_test_token', newToken);
    localStorage.setItem('veritas_test_email', email);
  };

  const clearAuth = () => {
    stopPolling();
    setToken('');
    setUserEmail('');
    localStorage.removeItem('veritas_test_token');
    localStorage.removeItem('veritas_test_email');
    setCurrentConversation(null);
    setSelectedAgreement(null);
    setRecentConversations([]);
    setAnalysis(null);
    setFinancialSummary(null);
    setConsensus(null);
    setAgreementHistoryList([]);
    setSettlementSummary(null);
    setActivePaymentRequestForCheckout(null);
    setIsPaymentModalOpen(false);
    setIsReviewModalOpen(false);
    setSelectedObligationForPayment(null);
    setPaymentHistoryModalReq(null);
    setPaymentHistoryList([]);
    setAnalysisError(null);
  };

  const handleDevLogin = async () => {
    setAuthLoading(true);
    setAuthError(null);
    try {
      try {
        const res = await loginUser(authEmail, authPassword);
        saveAuth(res.tokens.access_token, res.user.email);
        return;
      } catch (loginErr: any) {
        if (loginErr?.status === 401) {
          try {
            const regRes = await registerUser(authEmail, authPassword, 'Veritas QA Tester');
            saveAuth(regRes.tokens.access_token, regRes.user.email);
            return;
          } catch (regErr: any) {
            if (regErr?.status === 409) {
              throw new Error('Account exists, but password was incorrect. Please check your credentials.');
            }
            throw regErr;
          }
        }
        throw loginErr;
      }
    } catch (err: any) {
      setAuthError(err.message || 'Authentication failed');
    } finally {
      setAuthLoading(false);
    }
  };

  const handleSwitchPersona = async (email: string, fullName: string) => {
    setAuthLoading(true);
    setAuthError(null);
    try {
      let activeTok = '';
      try {
        const res = await loginUser(email, authPassword);
        activeTok = res.tokens.access_token;
        saveAuth(activeTok, res.user.email);
      } catch (loginErr: any) {
        if (loginErr?.status === 401) {
          const regRes = await registerUser(email, authPassword, fullName);
          activeTok = regRes.tokens.access_token;
          saveAuth(activeTok, regRes.user.email);
        } else {
          throw loginErr;
        }
      }
      setSubmitSuccess(`Switched active user to ${fullName} (${email}). Individual consent permissions reloaded.`);
      const activeAgrId = currentAgreement?.id || settlementSummary?.agreement_id;
      if (activeTok) {
        if (activeAgrId) {
          await refreshAgreementAndSettlement(activeAgrId, activeTok);
        } else if (currentConversation) {
          await loadIntelligenceForConversation(currentConversation.id, activeTok);
        }
      }
    } catch (err: any) {
      setAuthError(err.message || 'Persona switch failed');
    } finally {
      setAuthLoading(false);
    }
  };

  const loadConsensusForAgreement = async (agreementId: string, customToken?: string) => {
    const t = customToken || token;
    if (!t) return;
    try {
      const res = await getAgreementConsensus(t, agreementId);
      setConsensus(res);
      try {
        const hist = await getAgreementHistory(t, agreementId);
        setAgreementHistoryList(hist);
      } catch {}
      try {
        await loadSettlementSummary(agreementId, t);
      } catch {}
    } catch (err: any) {
      console.warn('Failed to load consensus:', err);
    }
  };

  const loadHistory = async () => {
    if (!token) return;
    setLoadingHistory(true);
    try {
      const res = await listConversations(token, 1, 20);
      setRecentConversations(res.items);
    } catch (err: any) {
      console.error('Failed to load conversations:', err);
    } finally {
      setLoadingHistory(false);
    }
  };

  const startPolling = (conversationId: string) => {
    stopPolling();
    setAnalysisLoading(true);
    let attempts = 0;
    const maxAttempts = 35; // 35 * 2s = 70s timeout

    pollingRef.current = setInterval(async () => {
      attempts++;
      try {
        const latest = await getLatestAnalysis(token, conversationId);
        setAnalysis(latest);

        if (latest.status === 'COMPLETED') {
          stopPolling();
          setAnalysisLoading(false);
          setAnalysisError(null);
          if (latest.agreements && latest.agreements.length > 0) {
            const agr = latest.agreements[0];
            setSelectedAgreement(agr);
            setEditTitle(agr.title);
            setEditSummary(agr.summary);
            setEditTerms([...agr.terms]);
            loadConsensusForAgreement(agr.id);
            loadSettlementSummary(agr.id);
          }
          try {
            const fin = await getFinancialSummary(token, conversationId);
            setFinancialSummary(fin);
          } catch {}
          setSubmitSuccess('Gemini analysis completed successfully with evidence-grounded facts and split calculations.');
        } else if (latest.status === 'FAILED') {
          stopPolling();
          setAnalysisLoading(false);
          setAnalysisError(latest.error_message || 'Analysis failed. Please click Retry Analysis.');
        } else if (attempts >= maxAttempts) {
          stopPolling();
          setAnalysisLoading(false);
          setAnalysisError('Analysis took longer than expected (>70s). Please click Retry Analysis.');
        }
      } catch (err: any) {
        if (attempts >= maxAttempts) {
          stopPolling();
          setAnalysisLoading(false);
          setAnalysisError(err.message || 'Status polling failed');
        }
      }
    }, 2000);
  };

  const loadIntelligenceForConversation = async (conversationId: string, customToken?: string) => {
    const t = customToken || token;
    if (!t) return;
    stopPolling();
    setAnalysisError(null);
    try {
      const latest = await getLatestAnalysis(t, conversationId);
      setAnalysis(latest);

      if (latest.status === 'COMPLETED') {
        setAnalysisLoading(false);
        if (latest.agreements && latest.agreements.length > 0) {
          const agr = latest.agreements[0];
          setSelectedAgreement(agr);
          setEditTitle(agr.title);
          setEditSummary(agr.summary);
          setEditTerms([...agr.terms]);
          loadConsensusForAgreement(agr.id, t);
          loadSettlementSummary(agr.id, t);
        }
      } else if (latest.status === 'FAILED') {
        setAnalysisLoading(false);
        setAnalysisError(latest.error_message || 'Analysis previously failed.');
      } else if (latest.status === 'QUEUED' || latest.status === 'PROCESSING') {
        startPolling(conversationId);
      }
    } catch (err: any) {
      console.warn('Failed to load analysis for conversation:', err);
      setAnalysisLoading(false);
    }

    try {
      const fin = await getFinancialSummary(t, conversationId);
      setFinancialSummary(fin);
    } catch (err: any) {
      console.warn('Failed to load financial summary:', err);
    }
  };

  const handleIngest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) {
      setSubmitError('Please sign in first before ingesting conversations.');
      return;
    }

    setSubmitting(true);
    setSubmitError(null);
    setSubmitSuccess(null);

    try {
      let result: ConversationDetail;
      if (activeTab === 'paste') {
        if (!pastedText.trim()) {
          throw new Error('Please enter conversation text to ingest.');
        }
        result = await ingestPastedText(token, pastedText, customTitle);
      } else {
        if (!selectedFile) {
          throw new Error('Please select a .txt WhatsApp export file to upload.');
        }
        result = await uploadWhatsAppFile(token, selectedFile, customTitle);
      }

      setCurrentConversation(result);
      setSubmitSuccess(
        `Ingested conversation successfully with ${result.total_messages} messages and ${result.total_participants} participants.`
      );
      if (activeTab === 'paste') setPastedText('');
      setSelectedFile(null);
      setCustomTitle('');
      loadHistory();
      // Load intelligence
      setSelectedAgreement(null);
      loadIntelligenceForConversation(result.id);
    } catch (err: any) {
      setSubmitError(err.message || 'Ingestion failed');
    } finally {
      setSubmitting(false);
    }
  };

  const handleViewConversation = async (id: string) => {
    if (!token) return;
    try {
      setSelectedAgreement(null);
      setAnalysis(null);
      setFinancialSummary(null);
      setConsensus(null);
      setSettlementSummary(null);
      setAgreementHistoryList([]);
      const detail = await getConversation(token, id);
      setCurrentConversation(detail);
      setSubmitSuccess(null);
      setSubmitError(null);
      setIsEditingAgreement(false);
      loadIntelligenceForConversation(id);
    } catch (err: any) {
      setSubmitError(err.message || 'Failed to fetch conversation details');
    }
  };

  const handleDeleteConversation = async (id: string) => {
    if (!token) return;
    if (!confirm('Are you sure you want to delete this conversation and all associated messages?')) {
      return;
    }

    setDeletingId(id);
    try {
      await deleteConversation(token, id);
      if (currentConversation?.id === id) {
        setCurrentConversation(null);
        setSelectedAgreement(null);
        setAnalysis(null);
        setFinancialSummary(null);
      }
      setRecentConversations((prev) => prev.filter((item) => item.id !== id));
      setSubmitSuccess('Conversation deleted successfully.');
    } catch (err: any) {
      setSubmitError(err.message || 'Failed to delete conversation');
    } finally {
      setDeletingId(null);
    }
  };

  // Stage 3: Analyze with Gemini
  const handleAnalyze = async (forceRetry: boolean = false) => {
    if (!token || !currentConversation) return;
    stopPolling();
    setAnalysisLoading(true);
    setAnalysisError(null);
    try {
      const result = await analyzeConversation(token, currentConversation.id, forceRetry);
      setAnalysis(result);

      if (result.status === 'COMPLETED') {
        setAnalysisLoading(false);
        if (result.agreements.length > 0) {
          const agr = result.agreements[0];
          setEditTitle(agr.title);
          setEditSummary(agr.summary);
          setEditTerms([...agr.terms]);
          loadConsensusForAgreement(agr.id);
        }
        const fin = await getFinancialSummary(token, currentConversation.id);
        setFinancialSummary(fin);
        setActiveSubTab('agreement');
        setSubmitSuccess('Gemini analysis completed successfully with evidence-grounded facts and split calculations.');
      } else if (result.status === 'FAILED') {
        setAnalysisLoading(false);
        setAnalysisError(result.error_message || 'Analysis failed. Please click Retry Analysis.');
      } else {
        // QUEUED or PROCESSING: poll until terminal status
        startPolling(currentConversation.id);
      }
    } catch (err: any) {
      setAnalysisLoading(false);
      setAnalysisError(err.message || 'Analysis failed');
    }
  };

  // Stage 3: Edit Agreement (Increments version & resets acceptances for re-review)
  const handleSaveAgreement = async () => {
    if (!token || !analysis || analysis.agreements.length === 0) return;
    const agr = analysis.agreements[0];
    setSavingAgreement(true);
    try {
      const updated = await updateAgreement(token, agr.id, {
        title: editTitle.trim(),
        summary: editSummary.trim(),
        terms: editTerms,
      });
      setAnalysis({
        ...analysis,
        agreements: [updated, ...analysis.agreements.slice(1)],
      });
      setIsEditingAgreement(false);
      await loadConsensusForAgreement(updated.id);
      setSubmitSuccess(`Agreement updated to v${updated.version}. Prior acceptances have been invalidated and reset for review.`);
    } catch (err: any) {
      alert(`Failed to save agreement: ${err.message}`);
    } finally {
      setSavingAgreement(false);
    }
  };

  // Stage 3.1: Submit Agreement for Multi-Participant Review
  const handleSubmitForReview = async () => {
    if (!token || !currentAgreement) return;
    setSubmittingReview(true);
    try {
      const res = await submitAgreementForReview(token, currentAgreement.id);
      setConsensus(res);
      if (analysis) {
        setAnalysis({
          ...analysis,
          agreements: analysis.agreements.map((a) =>
            a.id === currentAgreement.id ? { ...a, status: res.status, version: res.version } : a
          ),
        });
      }
      const hist = await getAgreementHistory(token, currentAgreement.id);
      setAgreementHistoryList(hist);
      setSubmitSuccess(`Agreement v${res.version} submitted for review. All participants can now review terms and submit individual consent.`);
    } catch (err: any) {
      alert(`Failed to submit for review: ${err.message}`);
    } finally {
      setSubmittingReview(false);
    }
  };

  // Stage 3.1: Record Individual Participant Response
  const handleParticipantRespond = async (
    participantId: string,
    action: 'ACCEPTED' | 'REJECTED' | 'REQUESTED_CHANGES',
    comment?: string
  ) => {
    if (!token || !currentAgreement) return;
    setSubmittingResponse(true);
    try {
      const res = await respondAsParticipant(token, currentAgreement.id, participantId, action, comment);
      setConsensus(res);
      if (analysis) {
        setAnalysis({
          ...analysis,
          agreements: analysis.agreements.map((a) =>
            a.id === currentAgreement.id
              ? { ...a, status: res.status, version: res.version, is_confirmed: res.is_confirmed }
              : a
          ),
        });
      }
      const hist = await getAgreementHistory(token, currentAgreement.id);
      setAgreementHistoryList(hist);
      setActiveRespondingParticipantId(null);
      setResponseComment('');
      setSubmitSuccess(
        action === 'ACCEPTED'
          ? `Individual consent recorded: ACCEPTED for v${res.version}.`
          : action === 'REQUESTED_CHANGES'
          ? `Changes requested for v${res.version}. Agreement marked CHANGES_REQUESTED.`
          : `Agreement rejected for v${res.version}.`
      );
    } catch (err: any) {
      alert(`Failed to submit participant response: ${err.message}`);
    } finally {
      setSubmittingResponse(false);
    }
  };

  // Stage 3.2: Direct User Assignment
  const handleAssignUser = async (participantId: string, email: string) => {
    if (!token || !currentAgreement || !email.trim()) return;
    setBindingLoading(true);
    try {
      await bindParticipantUser(token, currentAgreement.id, participantId, { email: email.trim() });
      await loadConsensusForAgreement(currentAgreement.id);
      setAssigningPartId(null);
      setAssignEmail('');
      setSubmitSuccess(`User account ${email.trim()} explicitly bound to participant.`);
    } catch (err: any) {
      alert(`Failed to assign user: ${err.message}`);
    } finally {
      setBindingLoading(false);
    }
  };

  // Stage 3.2: Unbind User
  const handleUnbindUser = async (participantId: string) => {
    if (!token || !currentAgreement) return;
    if (!confirm('Are you sure you want to unbind this participant?')) return;
    setBindingLoading(true);
    try {
      await unbindParticipantUser(token, currentAgreement.id, participantId);
      await loadConsensusForAgreement(currentAgreement.id);
      setSubmitSuccess('Participant account binding revoked.');
    } catch (err: any) {
      alert(`Failed to unbind participant: ${err.message}`);
    } finally {
      setBindingLoading(false);
    }
  };

  // Stage 3.2: Generate Invitation Token
  const handleGenerateInvitation = async (participantId: string) => {
    if (!token || !currentAgreement) return;
    setBindingLoading(true);
    try {
      const inv = await createParticipantInvitation(token, currentAgreement.id, participantId, 48);
      setGeneratedInvitations((prev) => ({ ...prev, [participantId]: inv }));
      await loadConsensusForAgreement(currentAgreement.id);
      setSubmitSuccess(`Single-use invitation token generated for ${inv.participant_name}. Link is active for 48 hours.`);
    } catch (err: any) {
      alert(`Failed to generate invitation: ${err.message}`);
    } finally {
      setBindingLoading(false);
    }
  };

  // Stage 3.2: Claim / Accept Invitation Token
  const handleClaimInvitation = async (tokenStr: string) => {
    if (!token) {
      alert('Please sign in first before accepting an invitation.');
      return;
    }
    if (!tokenStr.trim()) {
      alert('Please enter an invitation token.');
      return;
    }
    setClaimingInvitation(true);
    try {
      const res = await acceptInvitation(token, tokenStr.trim());
      setConsensus(res);
      if (currentAgreement) {
        await loadConsensusForAgreement(currentAgreement.id);
      }
      setShowClaimModal(false);
      setClaimTokenInput('');
      setSubmitSuccess('Invitation successfully claimed! Your authenticated account is now securely bound to the participant role.');
    } catch (err: any) {
      alert(`Failed to claim invitation: ${err.message}`);
    } finally {
      setClaimingInvitation(false);
    }
  };

  // Stage 3: Resolve Ambiguity
  const handleResolveAmbiguity = async (ambiguityId: string, resolutionText: string) => {
    if (!token || !analysis) return;
    setResolvingId(ambiguityId);
    try {
      const resolved = await resolveAmbiguity(token, ambiguityId, resolutionText);
      setAnalysis({
        ...analysis,
        ambiguities: analysis.ambiguities.map((a) => (a.id === ambiguityId ? resolved : a)),
      });
      setSubmitSuccess('Ambiguity resolved and recorded in agreement audit history.');
    } catch (err: any) {
      alert(`Failed to resolve ambiguity: ${err.message}`);
    } finally {
      setResolvingId(null);
    }
  };

  const getStatusBadgeClass = (status: string) => {
    switch (status?.toUpperCase()) {
      case 'CONFIRMED':
        return 'bg-emerald-950/80 text-emerald-400 border border-emerald-700/80';
      case 'PARTIALLY_ACCEPTED':
        return 'bg-sky-950/80 text-sky-300 border border-sky-700/80';
      case 'UNDER_REVIEW':
        return 'bg-amber-950/80 text-amber-300 border border-amber-700/80';
      case 'CHANGES_REQUESTED':
        return 'bg-purple-950/80 text-purple-300 border border-purple-700/80';
      case 'REJECTED':
        return 'bg-rose-950/80 text-rose-300 border border-rose-700/80';
      case 'DRAFT':
      default:
        return 'bg-slate-800 text-slate-300 border border-slate-700';
    }
  };

  const getConsentBadgeClass = (status: string) => {
    switch (status?.toUpperCase()) {
      case 'ACCEPTED':
        return 'bg-emerald-950/80 text-emerald-400 border border-emerald-700/80';
      case 'REQUESTED_CHANGES':
        return 'bg-purple-950/80 text-purple-300 border border-purple-700/80';
      case 'REJECTED':
        return 'bg-rose-950/80 text-rose-300 border border-rose-700/80';
      case 'PENDING':
      default:
        return 'bg-slate-800/80 text-slate-400 border border-slate-700';
    }
  };

  const getFactClassificationClass = (cls: string) => {
    switch (cls.toUpperCase()) {
      case 'PAID':
        return 'bg-emerald-950/80 text-emerald-400 border-emerald-800';
      case 'PROMISED':
        return 'bg-sky-950/80 text-sky-400 border-sky-800';
      case 'REQUESTED':
        return 'bg-amber-950/80 text-amber-300 border-amber-800';
      case 'PROPOSED':
        return 'bg-purple-950/80 text-purple-300 border-purple-800';
      case 'MENTIONED':
        return 'bg-slate-800 text-slate-300 border-slate-700';
      case 'UNCLEAR':
      default:
        return 'bg-rose-950/80 text-rose-300 border-rose-800';
    }
  };

  const getSettlementBadgeClass = (status?: string) => {
    switch (status?.toUpperCase()) {
      case 'FULLY_SETTLED':
        return 'bg-emerald-950/80 text-emerald-400 border border-emerald-700/80';
      case 'PARTIALLY_SETTLED':
        return 'bg-amber-950/80 text-amber-300 border border-amber-700/80';
      case 'UNSETTLED':
      default:
        return 'bg-slate-800 text-slate-300 border border-slate-700';
    }
  };

  const getPaymentRequestStatusBadgeClass = (status?: string) => {
    switch (status?.toUpperCase()) {
      case 'COMPLETED':
        return 'bg-emerald-950/80 text-emerald-400 border border-emerald-700/80';
      case 'PENDING':
        return 'bg-amber-950/80 text-amber-300 border border-amber-700/80';
      case 'CANCELLED':
        return 'bg-slate-800 text-slate-400 border border-slate-700';
      case 'FAILED':
      case 'REFUNDED':
        return 'bg-rose-950/80 text-rose-300 border border-rose-700/80';
      default:
        return 'bg-slate-800 text-slate-300 border border-slate-700';
    }
  };

  // Stage 4: PayPal Settlement Summary Loader
  const loadSettlementSummary = async (agreementId: string, customToken?: string) => {
    const t = customToken || token;
    if (!t) return;
    setLoadingSettlement(true);
    setSettlementError(null);
    try {
      const summary = await getAgreementSettlementSummary(t, agreementId);
      setSettlementSummary(summary);
    } catch (err: any) {
      console.warn('Failed to load settlement summary:', err);
      setSettlementError(err?.message || 'Failed to load settlement summary');
    } finally {
      setLoadingSettlement(false);
    }
  };

  // Stage 4: Open Pre-Payment Review Modal
  const handleOpenPaymentReview = (obligation: ObligationPaymentSummary) => {
    setSelectedObligationForPayment(obligation);
    setIsReviewModalOpen(true);
  };

  // Stage 4: Confirm and Launch PayPal Checkout
  const handleConfirmAndProceedToCheckout = async () => {
    const activeAgrId = currentAgreement?.id || settlementSummary?.agreement_id;
    if (!token || !activeAgrId || !selectedObligationForPayment) return;
    setCreatingPaymentReq(true);
    try {
      let req = selectedObligationForPayment.payment_request;
      // If no payment request exists or it's cancelled, create one
      if (!req || req.status === 'CANCELLED') {
        req = await createPaymentRequest(token, activeAgrId, selectedObligationForPayment.obligation_id);
      }
      setIsReviewModalOpen(false);
      setActivePaymentRequestForCheckout(req);
      setIsPaymentModalOpen(true);
      await loadSettlementSummary(activeAgrId);
    } catch (err: any) {
      alert(`Could not initiate payment request: ${err.message}`);
    } finally {
      setCreatingPaymentReq(false);
    }
  };

  // Stage 4: Open Checkout Modal for an existing pending PaymentRequest
  const handlePayExistingRequest = (req: PaymentRequest) => {
    setActivePaymentRequestForCheckout(req);
    setIsPaymentModalOpen(true);
  };

  // Stage 4.3: Robust unified refresh for agreement, settlement, and consensus state
  const refreshAgreementAndSettlement = async (agreementId: string, customToken?: string) => {
    const t = customToken || token;
    if (!t) return;
    try {
      try {
        const updatedAgr = await getAgreement(t, agreementId);
        setSelectedAgreement(updatedAgr);
      } catch (err: any) {
        console.warn('Could not refresh agreement by id:', err);
      }
      await loadSettlementSummary(agreementId, t);
      await loadConsensusForAgreement(agreementId, t);
      if (currentConversation) {
        await loadIntelligenceForConversation(currentConversation.id, t);
      }
    } catch (err: any) {
      console.warn('refreshAgreementAndSettlement failed:', err);
    }
  };

  // Stage 4: Handle successful capture
  const handlePaymentSuccess = async (capture: PaymentCapture) => {
    setSubmitSuccess(
      `Payment of $${Number(capture.amount).toFixed(2)} ${capture.currency} successfully captured via PayPal! (Capture ID: ${capture.paypal_capture_id})`
    );
    const agrId = currentAgreement?.id || settlementSummary?.agreement_id;
    if (agrId) {
      await refreshAgreementAndSettlement(agrId);
    }
  };

  // Stage 4: Cancel uncaptured payment request
  const handleCancelRequest = async (requestId: string) => {
    const agrId = currentAgreement?.id || settlementSummary?.agreement_id;
    if (!token || !agrId) return;
    if (!confirm('Are you sure you want to cancel this payment request?')) return;
    setCancellingRequestId(requestId);
    try {
      await cancelPaymentRequest(token, requestId, 'Cancelled by user');
      setSubmitSuccess('Payment request cancelled successfully.');
      await refreshAgreementAndSettlement(agrId);
    } catch (err: any) {
      alert(`Failed to cancel payment request: ${err.message}`);
    } finally {
      setCancellingRequestId(null);
    }
  };

  // Stage 4: View Payment Request Audit History
  const handleViewPaymentHistory = async (req: PaymentRequest) => {
    if (!token) return;
    setPaymentHistoryModalReq(req);
    setLoadingPaymentHistory(true);
    try {
      const history = await getPaymentRequestHistory(token, req.id);
      setPaymentHistoryList(history);
    } catch (err: any) {
      alert(`Failed to load payment history: ${err.message}`);
    } finally {
      setLoadingPaymentHistory(false);
    }
  };

  // Stage 4: Refund Payment Capture
  const handleRefundCapture = async () => {
    const agrId = currentAgreement?.id || settlementSummary?.agreement_id;
    if (!token || !refundingCapture || !agrId) return;
    setRefundingLoading(true);
    try {
      await refundPayPalCapture(token, refundingCapture.id, refundReason || 'Refund requested by agreement owner');
      setSubmitSuccess(`Payment refunded successfully via PayPal (Capture ID: ${refundingCapture.paypal_capture_id}).`);
      setRefundingCapture(null);
      setRefundReason('');
      await refreshAgreementAndSettlement(agrId);
    } catch (err: any) {
      alert(`Failed to process refund: ${err.message}`);
    } finally {
      setRefundingLoading(false);
    }
  };

  const currentAgreement: Agreement | null =
    selectedAgreement || (analysis && analysis.agreements && analysis.agreements.length > 0 ? analysis.agreements[0] : null);

  const activeCurrency: string = useMemo(() => {
    if (currentAgreement?.currency) return currentAgreement.currency;
    if (selectedAgreement?.currency) return selectedAgreement.currency;
    if (settlementSummary?.currency) return settlementSummary.currency;
    if (financialSummary?.currency) return financialSummary.currency;
    if (analysis?.financial_facts?.[0]?.currency) return analysis.financial_facts[0].currency;
    if (currentConversation?.messages?.some((m) => m.message_body.includes('₹') || m.message_body.includes('INR'))) return 'INR';
    return 'USD';
  }, [currentAgreement, selectedAgreement, settlementSummary, financialSummary, analysis, currentConversation]);

  const activeTestPersonas = useMemo(() => {
    const rawParts: { id: string; name: string; role?: string }[] = [];
    if (consensus?.participants && consensus.participants.length > 0) {
      consensus.participants.forEach((p) => rawParts.push({ id: p.id, name: p.name, role: (p as any).stated_role }));
    } else if (currentAgreement?.participants && currentAgreement.participants.length > 0) {
      currentAgreement.participants.forEach((p) => rawParts.push({ id: p.id, name: p.name, role: p.stated_role }));
    } else if (currentConversation?.participants && currentConversation.participants.length > 0) {
      currentConversation.participants.forEach((p) => rawParts.push({ id: p.id, name: p.display_name, role: 'Participant' }));
    }

    const seen = new Set<string>();
    const uniqueParts: { id: string; name: string; role?: string }[] = [];
    for (const p of rawParts) {
      const k = p.name.trim().toLowerCase();
      if (!seen.has(k) && k !== 'none' && k !== 'system') {
        seen.add(k);
        uniqueParts.push({ id: p.id, name: p.name.trim(), role: p.role });
      }
    }

    if (uniqueParts.length === 0) {
      return [
        { name: 'Veritas QA Tester', email: 'tester@veritas.local', role: 'QA Owner' }
      ];
    }

    const shareMap = new Map<string, { paid: number; fair: number; net: number }>();
    if (financialSummary?.participant_shares) {
      for (const sh of financialSummary.participant_shares) {
        shareMap.set(sh.participant_name.toLowerCase().trim(), {
          paid: Number(sh.paid_amount),
          fair: Number(sh.fair_share),
          net: Number(sh.net_balance),
        });
      }
    }

    const cur = activeCurrency;
    const list = uniqueParts.map((p) => {
      const cleanName = p.name.trim();
      const firstName = cleanName.split(' ')[0].toLowerCase().replace(/[^a-z0-9]/g, '');
      const email = `${firstName}@veritas.local`;

      const stats = shareMap.get(cleanName.toLowerCase());
      let roleText = p.role || 'Participant';
      if (stats) {
        if (stats.paid > 0) {
          roleText = `Paid ${formatMoney(stats.paid, cur)}`;
        } else if (stats.net < 0) {
          roleText = `Owes ${formatMoney(Math.abs(stats.net), cur)}`;
        } else {
          roleText = `Share ${formatMoney(stats.fair, cur)}`;
        }
      }
      return {
        name: cleanName,
        email: email,
        role: roleText,
      };
    });

    list.push({ name: 'Veritas QA Tester', email: 'tester@veritas.local', role: 'QA Owner' });
    return list;
  }, [consensus, currentAgreement, analysis, currentConversation, financialSummary, activeCurrency]);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      {/* Navigation header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <Link
              to="/"
              className="text-slate-400 hover:text-slate-200 transition-colors p-1.5 -ml-1.5 rounded-lg hover:bg-slate-800 inline-flex items-center gap-1 text-xs"
            >
              <ArrowLeft className="w-4 h-4" /> Back to Home
            </Link>
          </div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2.5 mt-1">
            <Bot className="w-6 h-6 text-emerald-400" />
            ACCORD Conversation Intelligence Test Bench
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Stage 3, 4 & 5: Gemini Intelligence, PayPal Settlement & WhatsApp Business Cloud Platform
          </p>
        </div>

        {/* Authentication bar */}
        <div className="bg-slate-800/80 border border-slate-700/80 rounded-xl p-3 flex flex-wrap items-center gap-3">
          {token ? (
            <div className="flex items-center gap-3 text-xs">
              <span className="flex items-center gap-1.5 text-emerald-400 font-medium">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                {userEmail}
              </span>
              <button
                onClick={clearAuth}
                className="bg-slate-700 hover:bg-slate-600 text-slate-300 hover:text-white px-2.5 py-1 rounded text-xs inline-flex items-center gap-1 transition"
              >
                <LogOut className="w-3.5 h-3.5" /> Sign Out
              </button>
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <input
                type="email"
                value={authEmail}
                onChange={(e) => setAuthEmail(e.target.value)}
                placeholder="Email"
                className="bg-slate-900 border border-slate-700 text-slate-200 text-xs px-2.5 py-1 rounded w-36 focus:outline-none focus:border-emerald-500"
              />
              <input
                type="password"
                value={authPassword}
                onChange={(e) => setAuthPassword(e.target.value)}
                placeholder="Password"
                className="bg-slate-900 border border-slate-700 text-slate-200 text-xs px-2.5 py-1 rounded w-28 focus:outline-none focus:border-emerald-500"
              />
              <button
                onClick={handleDevLogin}
                disabled={authLoading}
                className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-medium text-xs px-3 py-1 rounded inline-flex items-center gap-1.5 transition"
              >
                {authLoading ? (
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <LogIn className="w-3.5 h-3.5" />
                )}
                Quick Dev Auth
              </button>
            </div>
          )}
        </div>
      </div>

      {authError && (
        <div className="bg-rose-950/40 border border-rose-800 text-rose-300 text-xs p-3 rounded-lg flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
          <span>{authError}</span>
        </div>
      )}

      {submitError && (
        <div className="bg-rose-950/40 border border-rose-800 text-rose-300 text-xs p-3 rounded-lg flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
          <span>{submitError}</span>
        </div>
      )}

      {submitSuccess && (
        <div className="bg-emerald-950/40 border border-emerald-800 text-emerald-300 text-xs p-3 rounded-lg flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-400" />
          <span>{submitSuccess}</span>
        </div>
      )}

      {/* Main Grid: Left Ingestion Panel (4 cols), Right Results & Intelligence (8 cols) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Input Form & History (4 cols) */}
        <div className="lg:col-span-4 space-y-6">
          <div className="bg-slate-800/40 border border-slate-700/60 rounded-xl p-5 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-700/60 pb-3">
              <h2 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
                <FileText className="w-4 h-4 text-emerald-400" /> Ingest Transcript
              </h2>
              {/* Tab toggles */}
              <div className="inline-flex rounded-lg bg-slate-900/80 p-0.5 border border-slate-700/80 text-xs">
                <button
                  type="button"
                  onClick={() => setActiveTab('paste')}
                  className={`px-2.5 py-1 rounded font-medium transition text-xs ${
                    activeTab === 'paste'
                      ? 'bg-emerald-600 text-white shadow'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  Pasted
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab('upload')}
                  className={`px-2.5 py-1 rounded font-medium transition text-xs ${
                    activeTab === 'upload'
                      ? 'bg-emerald-600 text-white shadow'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  Upload
                </button>
              </div>
            </div>

            <form onSubmit={handleIngest} className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Title <span className="text-slate-500">(optional)</span>
                </label>
                <input
                  type="text"
                  value={customTitle}
                  onChange={(e) => setCustomTitle(e.target.value)}
                  placeholder="e.g. Tahoe Cabin Trip"
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500"
                />
              </div>

              {activeTab === 'paste' ? (
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="block text-xs font-medium text-slate-300">Transcript</label>
                    <button
                      type="button"
                      onClick={() => setPastedText(SAMPLE_WHATSAPP_CHAT)}
                      className="text-xs text-emerald-400 hover:text-emerald-300 inline-flex items-center gap-1"
                    >
                      <Sparkles className="w-3 h-3" /> Load Sample
                    </button>
                  </div>
                  <textarea
                    rows={8}
                    value={pastedText}
                    onChange={(e) => setPastedText(e.target.value)}
                    placeholder="Paste chat lines..."
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-xs font-mono text-slate-200 placeholder-slate-600 focus:outline-none focus:border-emerald-500"
                  />
                </div>
              ) : (
                <div>
                  <div className="border border-dashed border-slate-700 rounded-lg p-4 text-center hover:border-emerald-500/60 transition bg-slate-900/50">
                    <Upload className="w-6 h-6 mx-auto text-slate-500 mb-1" />
                    <input
                      type="file"
                      accept=".txt"
                      onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                      className="text-xs text-slate-400 file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:text-xs file:bg-emerald-600 file:text-white"
                    />
                    {selectedFile && (
                      <div className="text-[11px] text-emerald-400 mt-1 font-mono">
                        {selectedFile.name}
                      </div>
                    )}
                  </div>
                </div>
              )}

              <button
                type="submit"
                disabled={submitting || !token}
                className="w-full bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-medium py-2 px-3 rounded-lg text-xs inline-flex items-center justify-center gap-1.5 shadow-sm transition"
              >
                {submitting ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" /> Ingesting...
                  </>
                ) : (
                  <>
                    <Send className="w-3.5 h-3.5" /> Ingest Transcript
                  </>
                )}
              </button>
            </form>
          </div>

          {/* History list */}
          <div className="bg-slate-800/40 border border-slate-700/60 rounded-xl p-4 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-semibold text-slate-200 flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5 text-slate-400" /> History
              </h3>
              <button
                onClick={loadHistory}
                disabled={loadingHistory || !token}
                className="text-slate-400 hover:text-slate-200 text-xs p-1 rounded hover:bg-slate-700/50"
                title="Refresh list"
              >
                <RefreshCw className={`w-3 h-3 ${loadingHistory ? 'animate-spin' : ''}`} />
              </button>
            </div>

            {!token ? (
              <p className="text-xs text-slate-500 py-2 text-center">Sign in to view conversations.</p>
            ) : recentConversations.length === 0 ? (
              <p className="text-xs text-slate-500 py-2 text-center">No conversations ingested.</p>
            ) : (
              <div className="divide-y divide-slate-700/60 max-h-56 overflow-y-auto pr-1">
                {recentConversations.map((conv) => (
                  <div
                    key={conv.id}
                    className={`py-2 flex items-center justify-between gap-2 text-xs rounded px-1.5 transition ${
                      currentConversation?.id === conv.id ? 'bg-slate-800' : 'hover:bg-slate-800/50'
                    }`}
                  >
                    <div
                      onClick={() => handleViewConversation(conv.id)}
                      className="cursor-pointer flex-1 min-w-0"
                    >
                      <div className="font-medium text-slate-200 truncate">{conv.title}</div>
                      <div className="text-[10px] text-slate-500 flex items-center gap-1.5 mt-0.5">
                        <span>{conv.message_count} msgs</span>
                        <span>•</span>
                        <span>{conv.participant_count} parts</span>
                      </div>
                    </div>
                    <button
                      onClick={() => handleDeleteConversation(conv.id)}
                      disabled={deletingId === conv.id}
                      className="text-slate-500 hover:text-rose-400 p-1 rounded transition"
                    >
                      {deletingId === conv.id ? (
                        <RefreshCw className="w-3 h-3 animate-spin" />
                      ) : (
                        <Trash2 className="w-3 h-3" />
                      )}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Ingested Details & Stage 3 Intelligence (8 cols) */}
        <div className="lg:col-span-8">
          {activeSubTab === 'whatsapp' ? (
            <div className="bg-slate-800/40 border border-slate-700/60 rounded-xl p-5 space-y-5">
              <div className="flex items-center justify-between border-b border-slate-700/60 pb-3">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-400"></span>
                  <h3 className="font-bold text-white text-base">WhatsApp Cloud API & Test Bench Hub</h3>
                </div>
                {currentConversation && (
                  <button
                    onClick={() => setActiveSubTab('agreement')}
                    className="text-xs text-slate-400 hover:text-slate-200 underline"
                  >
                    ← Return to Agreement ({currentConversation.title})
                  </button>
                )}
              </div>
              <WhatsAppTab
                token={token}
                onOpenConversation={(convId) => {
                  handleViewConversation(convId);
                  setActiveSubTab('agreement');
                }}
              />
            </div>
          ) : currentConversation ? (
            <div className="bg-slate-800/40 border border-slate-700/60 rounded-xl p-5 space-y-5">
              {/* Header with Title and "Analyze with Gemini" Action */}
              <div className="border-b border-slate-700/60 pb-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="text-lg font-bold text-white flex items-center gap-2">
                      {currentConversation.title}
                    </h2>
                    <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400 mt-1 font-mono">
                      <span>ID: {currentConversation.id.substring(0, 8)}...</span>
                      <span>•</span>
                      <span>{currentConversation.messages.length} messages</span>
                      <span>•</span>
                      <span>{currentConversation.participants.length} participants</span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleAnalyze(analysis?.status === 'FAILED')}
                      disabled={analysisLoading}
                      className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-medium text-xs px-3.5 py-2 rounded-lg inline-flex items-center gap-2 shadow-lg shadow-emerald-900/30 transition"
                    >
                      {analysisLoading ? (
                        <>
                          <RefreshCw className="w-4 h-4 animate-spin" />
                          <span>
                            Extracting with Gemini
                            {analysis?.status === 'QUEUED'
                              ? ' (queued)...'
                              : analysis?.status === 'PROCESSING'
                              ? ' (processing)...'
                              : '...'}
                          </span>
                        </>
                      ) : analysis?.status === 'FAILED' ? (
                        <>
                          <RefreshCw className="w-4 h-4 text-amber-300" />
                          <span>Retry Analysis</span>
                        </>
                      ) : (
                        <>
                          <Bot className="w-4 h-4" />
                          <span>{analysis ? 'Re-Analyze with Gemini' : 'Analyze with Gemini'}</span>
                        </>
                      )}
                    </button>
                  </div>
                </div>

                {analysisError && (
                  <div className="mt-3 bg-rose-950/50 border border-rose-800 text-rose-300 text-xs p-3 rounded-lg flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2 min-w-0">
                      <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
                      <span className="truncate">Analysis Error: {analysisError}</span>
                    </div>
                    <button
                      onClick={() => handleAnalyze(true)}
                      disabled={analysisLoading}
                      className="bg-rose-700 hover:bg-rose-600 text-white font-semibold text-xs px-2.5 py-1 rounded inline-flex items-center gap-1 shrink-0 transition"
                    >
                      <RefreshCw className="w-3.5 h-3.5" />
                      <span>Retry Analysis</span>
                    </button>
                  </div>
                )}

                {/* Sub-Tabs Navigation */}
                <div className="flex items-center gap-1.5 mt-5 border-b border-slate-800 overflow-x-auto text-xs pb-1">
                  <button
                    onClick={() => setActiveSubTab('agreement')}
                    className={`px-3 py-1.5 font-medium rounded-t-lg transition flex items-center gap-1.5 ${
                      activeSubTab === 'agreement'
                        ? 'bg-slate-800 text-white border-t border-x border-slate-700'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    <Scale className="w-3.5 h-3.5 text-emerald-400" />
                    <span>Agreement & Consensus</span>
                    {currentAgreement && (
                      <span className={`text-[10px] px-1.5 py-0.2 rounded font-mono ${getStatusBadgeClass(currentAgreement.status)}`}>
                        {currentAgreement.status}
                      </span>
                    )}
                  </button>

                  <button
                    onClick={() => setActiveSubTab('settlement')}
                    className={`px-3 py-1.5 font-medium rounded-t-lg transition flex items-center gap-1.5 ${
                      activeSubTab === 'settlement'
                        ? 'bg-slate-800 text-white border-t border-x border-slate-700'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    <CreditCard className="w-3.5 h-3.5 text-amber-400" />
                    <span>PayPal Settlement</span>
                    {settlementSummary && (
                      <span className={`text-[10px] px-1.5 py-0.2 rounded font-mono ${getSettlementBadgeClass(settlementSummary.settlement_status)}`}>
                        {settlementSummary.settlement_status}
                      </span>
                    )}
                  </button>

                  <button
                    onClick={() => setActiveSubTab('whatsapp')}
                    className={`px-3 py-1.5 font-medium rounded-t-lg transition flex items-center gap-1.5 ${
                      (activeSubTab as string) === 'whatsapp'
                        ? 'bg-slate-800 text-white border-t border-x border-slate-700'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
                    <span>WhatsApp Hub</span>
                  </button>

                  <button
                    onClick={() => setActiveSubTab('financial')}
                    className={`px-3 py-1.5 font-medium rounded-t-lg transition flex items-center gap-1.5 ${
                      activeSubTab === 'financial'
                        ? 'bg-slate-800 text-white border-t border-x border-slate-700'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    <DollarSign className="w-3.5 h-3.5 text-emerald-400" />
                    <span>Expense Shares</span>
                    {financialSummary && (
                      <span className="bg-slate-700 text-slate-300 text-[10px] px-1.5 py-0.2 rounded font-mono">
                        {formatMoney(financialSummary.total_expenses, financialSummary.currency || activeCurrency)}
                      </span>
                    )}
                  </button>

                  <button
                    onClick={() => setActiveSubTab('facts')}
                    className={`px-3 py-1.5 font-medium rounded-t-lg transition flex items-center gap-1.5 ${
                      activeSubTab === 'facts'
                        ? 'bg-slate-800 text-white border-t border-x border-slate-700'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                    <span>Evidence Facts</span>
                    {analysis && (
                      <span className="bg-slate-700 text-slate-300 text-[10px] px-1.5 py-0.2 rounded">
                        {analysis.financial_facts.length}
                      </span>
                    )}
                  </button>

                  <button
                    onClick={() => setActiveSubTab('ambiguities')}
                    className={`px-3 py-1.5 font-medium rounded-t-lg transition flex items-center gap-1.5 ${
                      activeSubTab === 'ambiguities'
                        ? 'bg-slate-800 text-white border-t border-x border-slate-700'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    <HelpCircle className="w-3.5 h-3.5 text-amber-400" />
                    <span>Ambiguities</span>
                    {analysis && analysis.ambiguities.length > 0 && (
                      <span className="bg-amber-950/80 text-amber-300 border border-amber-800 text-[10px] px-1.5 py-0.2 rounded font-medium">
                        {analysis.ambiguities.filter((a) => a.status === 'UNRESOLVED').length}
                      </span>
                    )}
                  </button>

                  <button
                    onClick={() => setActiveSubTab('messages')}
                    className={`px-3 py-1.5 font-medium rounded-t-lg transition flex items-center gap-1.5 ${
                      activeSubTab === 'messages'
                        ? 'bg-slate-800 text-white border-t border-x border-slate-700'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    <MessageSquare className="w-3.5 h-3.5 text-slate-400" />
                    <span>Raw Messages ({currentConversation.messages.length})</span>
                  </button>
                </div>
              </div>

              {/* Sub-Tab 1: Agreement & Consensus Review */}
              {activeSubTab === 'agreement' && (
                <div className="space-y-5">
                  {!analysis ? (
                    <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-8 text-center space-y-3">
                      <Bot className="w-10 h-10 text-emerald-400 mx-auto" />
                      <h4 className="text-sm font-semibold text-white">No Analysis Generated Yet</h4>
                      <p className="text-xs text-slate-400 max-w-md mx-auto">
                        Click "Analyze with Gemini" above to automatically extract financial facts, identify obligations, detect ambiguities, and propose a consensus agreement.
                      </p>
                    </div>
                  ) : analysis.status === 'QUEUED' || analysis.status === 'PROCESSING' ? (
                    <div className="bg-slate-900/80 border border-slate-700/80 rounded-xl p-8 text-center space-y-4">
                      <div className="relative inline-flex items-center justify-center">
                        <div className="w-12 h-12 rounded-full border-2 border-emerald-500/20 border-t-emerald-400 animate-spin" />
                        <Bot className="w-6 h-6 text-emerald-400 absolute" />
                      </div>
                      <div>
                        <h4 className="text-sm font-bold text-white">
                          Gemini 3.8 Flash Analysis in Progress
                        </h4>
                        <p className="text-xs text-slate-400 mt-1 max-w-md mx-auto">
                          Extracting financial facts, verifying evidence anchors, and calculating deterministic settlement splits. This typically takes 5–15 seconds.
                        </p>
                      </div>
                      <div className="inline-flex items-center gap-2 px-3 py-1 bg-slate-800 text-xs text-slate-300 rounded-full font-mono">
                        <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
                        <span>Status: {analysis.status}</span>
                      </div>
                    </div>
                  ) : analysis.status === 'FAILED' ? (
                    <div className="bg-rose-950/30 border border-rose-800/80 rounded-xl p-6 text-center space-y-3">
                      <div className="w-10 h-10 rounded-full bg-rose-900/50 border border-rose-700 text-rose-400 flex items-center justify-center mx-auto">
                        <AlertCircle className="w-5 h-5" />
                      </div>
                      <div>
                        <h4 className="text-sm font-bold text-rose-300">Analysis Failed</h4>
                        <p className="text-xs text-rose-200/80 mt-1 max-w-lg mx-auto font-mono">
                          {analysis.error_message || 'The Gemini analysis job encountered an error.'}
                        </p>
                      </div>
                      <div className="pt-2 flex justify-center gap-3">
                        <button
                          onClick={() => handleAnalyze(true)}
                          disabled={analysisLoading}
                          className="bg-rose-700 hover:bg-rose-600 disabled:opacity-50 text-white font-medium text-xs px-4 py-2 rounded-lg inline-flex items-center gap-2 shadow-lg transition"
                        >
                          <RefreshCw className="w-3.5 h-3.5" />
                          <span>Retry Analysis</span>
                        </button>
                      </div>
                    </div>
                  ) : currentAgreement ? (
                    <div className="space-y-5">
                      {(() => {
                        const displayStatus = consensus?.status || currentAgreement.status;
                        const displayVersion = consensus?.version || currentAgreement.version || 1;
                        const participantsList = consensus?.participants && consensus.participants.length > 0
                          ? consensus.participants
                          : currentAgreement.participants;
                        const totalCount = consensus?.total_participants ?? participantsList.length;
                        const acceptedCount = consensus?.accepted_count ?? (displayStatus === 'CONFIRMED' ? totalCount : 0);
                        const progressPct = totalCount > 0 ? Math.round((acceptedCount / totalCount) * 100) : 0;

                        return (
                          <>
                            {/* Agreement Header Card */}
                            <div className="bg-slate-900/90 border border-slate-700/80 rounded-xl p-5 space-y-4">
                              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3">
                                <div className="flex flex-wrap items-center gap-2.5">
                                  <h3 className="text-base font-bold text-white">
                                    {currentAgreement.title}
                                  </h3>
                                  <span className="text-xs bg-slate-800 border border-slate-700 text-slate-300 px-2 py-0.5 rounded font-mono font-medium">
                                    v{displayVersion}
                                  </span>
                                  <span className={`text-xs px-2.5 py-0.5 rounded-full font-semibold ${getStatusBadgeClass(displayStatus)}`}>
                                    {displayStatus}
                                  </span>
                                </div>

                                <div className="flex items-center gap-2">
                                  {displayStatus === 'DRAFT' && (
                                    <button
                                      onClick={handleSubmitForReview}
                                      disabled={submittingReview}
                                      className="bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white text-xs font-medium px-3 py-1.5 rounded-lg inline-flex items-center gap-1.5 shadow transition"
                                    >
                                      {submittingReview ? (
                                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                                      ) : (
                                        <SendHorizontal className="w-3.5 h-3.5" />
                                      )}
                                      Submit for Review
                                    </button>
                                  )}

                                  {displayStatus !== 'CONFIRMED' && (
                                    <button
                                      onClick={() => setIsEditingAgreement(!isEditingAgreement)}
                                      className="bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs px-2.5 py-1.5 rounded-lg inline-flex items-center gap-1 transition border border-slate-700"
                                    >
                                      <Edit2 className="w-3 h-3" />
                                      {isEditingAgreement ? 'Cancel Edit' : 'Edit Agreement'}
                                    </button>
                                  )}
                                </div>
                              </div>

                              {/* Edit Agreement Form (Increments version & resets acceptances) */}
                              {isEditingAgreement ? (
                                <div className="space-y-3 bg-slate-800/40 border border-slate-700 p-4 rounded-lg">
                                  <div className="bg-amber-950/40 border border-amber-800/60 p-2.5 rounded text-xs text-amber-300 flex items-start gap-2">
                                    <AlertTriangle className="w-4 h-4 shrink-0 text-amber-400 mt-0.5" />
                                    <span>
                                      <strong>Note:</strong> Modifying terms increments the agreement version (to v{displayVersion + 1}) and invalidates all previous participant acceptances. Each participant must review and accept the new terms.
                                    </span>
                                  </div>
                                  <div>
                                    <label className="block text-xs font-medium text-slate-300 mb-1">Agreement Title</label>
                                    <input
                                      type="text"
                                      value={editTitle}
                                      onChange={(e) => setEditTitle(e.target.value)}
                                      className="w-full bg-slate-900 border border-slate-700 text-xs text-slate-200 px-3 py-1.5 rounded focus:outline-none focus:border-emerald-500"
                                    />
                                  </div>
                                  <div>
                                    <label className="block text-xs font-medium text-slate-300 mb-1">Agreement Summary</label>
                                    <textarea
                                      rows={3}
                                      value={editSummary}
                                      onChange={(e) => setEditSummary(e.target.value)}
                                      className="w-full bg-slate-900 border border-slate-700 text-xs text-slate-200 p-2.5 rounded focus:outline-none focus:border-emerald-500"
                                    />
                                  </div>
                                  <div>
                                    <label className="block text-xs font-medium text-slate-300 mb-1">Key Terms</label>
                                    <div className="space-y-1.5 mb-2">
                                      {editTerms.map((term, idx) => (
                                        <div key={idx} className="flex items-center gap-2">
                                          <input
                                            type="text"
                                            value={term}
                                            onChange={(e) => {
                                              const next = [...editTerms];
                                              next[idx] = e.target.value;
                                              setEditTerms(next);
                                            }}
                                            className="flex-1 bg-slate-900 border border-slate-700 text-xs text-slate-200 px-2.5 py-1 rounded"
                                          />
                                          <button
                                            type="button"
                                            onClick={() => setEditTerms(editTerms.filter((_, i) => i !== idx))}
                                            className="text-slate-500 hover:text-rose-400 p-1"
                                          >
                                            <X className="w-3.5 h-3.5" />
                                          </button>
                                        </div>
                                      ))}
                                    </div>
                                    <div className="flex items-center gap-2">
                                      <input
                                        type="text"
                                        value={newTermInput}
                                        onChange={(e) => setNewTermInput(e.target.value)}
                                        placeholder="Add another term..."
                                        className="flex-1 bg-slate-900 border border-slate-700 text-xs text-slate-200 px-2.5 py-1 rounded"
                                      />
                                      <button
                                        type="button"
                                        onClick={() => {
                                          if (newTermInput.trim()) {
                                            setEditTerms([...editTerms, newTermInput.trim()]);
                                            setNewTermInput('');
                                          }
                                        }}
                                        className="bg-slate-700 hover:bg-slate-600 text-white text-xs px-2.5 py-1 rounded"
                                      >
                                        Add Term
                                      </button>
                                    </div>
                                  </div>
                                  <div className="flex justify-end gap-2 pt-2">
                                    <button
                                      onClick={() => setIsEditingAgreement(false)}
                                      className="text-slate-400 hover:text-slate-200 text-xs px-3 py-1.5"
                                    >
                                      Cancel
                                    </button>
                                    <button
                                      onClick={handleSaveAgreement}
                                      disabled={savingAgreement}
                                      className="bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium px-4 py-1.5 rounded inline-flex items-center gap-1.5 shadow"
                                    >
                                      {savingAgreement ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
                                      Save New Version & Reset Acceptances
                                    </button>
                                  </div>
                                </div>
                              ) : (
                                <>
                                  <p className="text-xs text-slate-300 leading-relaxed">
                                    {currentAgreement.summary}
                                  </p>

                                  {/* Terms List */}
                                  {currentAgreement.terms.length > 0 && (
                                    <div className="space-y-1.5">
                                      <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Key Terms & Breakdown</h4>
                                      <ul className="space-y-1 text-xs text-slate-300">
                                        {currentAgreement.terms.map((term, idx) => (
                                          <li key={idx} className="flex items-start gap-2">
                                            <span className="text-emerald-400 mt-0.5">•</span>
                                            <span>{term}</span>
                                          </li>
                                        ))}
                                      </ul>
                                    </div>
                                  )}
                                </>
                              )}
                            </div>

                            {/* Consensus Overview & Progress Bar */}
                            <div className="bg-slate-900/90 border border-slate-700/80 rounded-xl p-5 space-y-4">
                              <div className="flex flex-wrap items-center justify-between gap-3">
                                <div>
                                  <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                                    <Users className="w-3.5 h-3.5 text-emerald-400" /> Multi-Participant Consensus Progress
                                  </h4>
                                  <p className="text-xs text-slate-300 mt-1">
                                    {consensus?.status_message ||
                                      (displayStatus === 'DRAFT'
                                        ? 'Agreement is in draft. Submit for review so participants can cast individual consent.'
                                        : displayStatus === 'CONFIRMED'
                                        ? 'Full mutual consensus achieved! All participants have independently accepted terms.'
                                        : 'Awaiting participant individual review.')}
                                  </p>
                                </div>
                                <div className="text-xs font-mono font-semibold text-slate-200">
                                  {acceptedCount} / {totalCount} Accepted ({progressPct}%)
                                </div>
                              </div>

                              {/* Progress Track */}
                              <div className="w-full bg-slate-800 rounded-full h-2.5 overflow-hidden border border-slate-700/60">
                                <div
                                  className={`h-2.5 transition-all duration-500 ${
                                    displayStatus === 'CONFIRMED'
                                      ? 'bg-emerald-500'
                                      : displayStatus === 'REJECTED'
                                      ? 'bg-rose-500'
                                      : displayStatus === 'CHANGES_REQUESTED'
                                      ? 'bg-purple-500'
                                      : 'bg-sky-500'
                                  }`}
                                  style={{ width: `${progressPct}%` }}
                                />
                              </div>

                              {/* Counter breakdown pills */}
                              <div className="flex flex-wrap items-center gap-2 pt-1 text-[11px]">
                                <span className="bg-emerald-950/80 border border-emerald-800 text-emerald-400 px-2.5 py-0.5 rounded-full">
                                  Accepted: {consensus?.accepted_count || (displayStatus === 'CONFIRMED' ? totalCount : 0)}
                                </span>
                                <span className="bg-slate-800 border border-slate-700 text-slate-400 px-2.5 py-0.5 rounded-full">
                                  Pending: {consensus?.pending_count ?? (displayStatus === 'DRAFT' ? totalCount : 0)}
                                </span>
                                <span className="bg-purple-950/80 border border-purple-800 text-purple-300 px-2.5 py-0.5 rounded-full">
                                  Changes Requested: {consensus?.changes_requested_count || 0}
                                </span>
                                <span className="bg-rose-950/80 border border-rose-800 text-rose-300 px-2.5 py-0.5 rounded-full">
                                  Rejected: {consensus?.rejected_count || 0}
                                </span>
                              </div>
                            </div>

                            {/* Testing Persona Switcher Bar (DEV / TEST ENVIRONMENT ONLY) */}
                            {import.meta.env.DEV && (
                              <div className="bg-slate-850 border border-slate-700/80 rounded-xl p-4 space-y-2.5 bg-slate-900/60">
                                <div className="flex flex-wrap items-center justify-between gap-2">
                                  <div className="flex items-center gap-2">
                                    <span className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                                      <UserCheck className="w-3.5 h-3.5 text-emerald-400" />
                                      Participant Persona Testing Switcher
                                    </span>
                                    <span className="text-[10px] bg-amber-950/80 border border-amber-800 text-amber-300 px-2 py-0.2 rounded font-mono">
                                      DEV TEST ONLY
                                    </span>
                                  </div>
                                  <div className="flex items-center gap-2">
                                    <span className="text-[11px] text-slate-400">
                                      Active Identity: <strong className="text-emerald-400">{userEmail || 'Not signed in'}</strong>
                                    </span>
                                    <button
                                      onClick={() => setShowClaimModal(true)}
                                      className="text-xs bg-slate-800 hover:bg-slate-700 border border-slate-700 text-sky-300 px-2.5 py-1 rounded-lg inline-flex items-center gap-1 transition"
                                    >
                                      <Key className="w-3 h-3 text-sky-400" />
                                      Claim Invitation
                                    </button>
                                  </div>
                                </div>
                                <p className="text-[11px] text-slate-400">
                                  Identity binding is strictly authenticated. First-name and email-prefix matching are disabled. Switch personas to test bound authorization or claim single-use invitation tokens:
                                </p>
                                <div className="flex flex-wrap gap-2 pt-1">
                                  {activeTestPersonas.map((persona) => {
                                    const isActive = userEmail?.toLowerCase() === persona.email.toLowerCase();
                                    return (
                                      <button
                                        key={persona.email}
                                        onClick={() => handleSwitchPersona(persona.email, persona.name)}
                                        disabled={authLoading}
                                        className={`text-xs px-3 py-1.5 rounded-lg border font-medium transition inline-flex items-center gap-1.5 ${
                                          isActive
                                            ? 'bg-emerald-600 text-white border-emerald-500 shadow-md shadow-emerald-950'
                                            : 'bg-slate-800 hover:bg-slate-700 text-slate-300 border-slate-700'
                                        }`}
                                      >
                                        {isActive && <Check className="w-3 h-3 text-white" />}
                                        <span>{persona.name}</span>
                                        <span className="text-[10px] opacity-75">({persona.role})</span>
                                      </button>
                                    );
                                  })}
                                </div>
                              </div>
                            )}

                            {/* Claim Invitation Modal */}
                            {showClaimModal && (
                              <div className="bg-slate-900 border border-sky-700/80 rounded-xl p-4 space-y-3 shadow-xl">
                                <div className="flex items-center justify-between">
                                  <h4 className="text-xs font-semibold text-sky-300 flex items-center gap-1.5">
                                    <Key className="w-4 h-4 text-sky-400" /> Claim Single-Use Participant Invitation
                                  </h4>
                                  <button
                                    onClick={() => setShowClaimModal(false)}
                                    className="text-slate-400 hover:text-white"
                                  >
                                    <X className="w-3.5 h-3.5" />
                                  </button>
                                </div>
                                <p className="text-xs text-slate-300">
                                  Enter the cryptographically random invitation token provided by the agreement owner. Claiming binds your active account (<strong>{userEmail}</strong>) exclusively to that participant role.
                                </p>
                                <div className="flex items-center gap-2">
                                  <input
                                    type="text"
                                    value={claimTokenInput}
                                    onChange={(e) => setClaimTokenInput(e.target.value)}
                                    placeholder="Paste invitation token (e.g. gD73...)"
                                    className="flex-1 bg-slate-950 border border-slate-700 text-xs text-slate-200 px-3 py-1.5 rounded font-mono focus:outline-none focus:border-sky-500"
                                  />
                                  <button
                                    onClick={() => handleClaimInvitation(claimTokenInput)}
                                    disabled={claimingInvitation || !claimTokenInput.trim()}
                                    className="bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white text-xs font-medium px-4 py-1.5 rounded inline-flex items-center gap-1.5 transition"
                                  >
                                    {claimingInvitation ? <RefreshCw className="w-3 h-3 animate-spin" /> : <ShieldCheck className="w-3 h-3" />}
                                    Accept & Bind Account
                                  </button>
                                </div>
                              </div>
                            )}

                            {/* Individual Participant Consent Cards with Secure Identity Binding */}
                            <div className="bg-slate-900/90 border border-slate-700/80 rounded-xl p-5 space-y-4">
                              <div className="flex items-center justify-between">
                                <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                                  <Shield className="w-3.5 h-3.5 text-emerald-400" /> Required Participant Consents ({participantsList.length})
                                </h4>
                                <span className="text-[11px] text-slate-400">
                                  Target: <strong>v{displayVersion}</strong>
                                </span>
                              </div>

                              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                                {participantsList.map((participant) => {
                                  const canRespond = !!participant.can_respond;
                                  const isBound = !!participant.user_id;
                                  const isDrawerOpen = activeRespondingParticipantId === participant.id;
                                  const isAssigning = assigningPartId === participant.id;
                                  const activeInvitation = generatedInvitations[participant.id];
                                  const hasPendingInvitation = participant.has_pending_invitation || !!activeInvitation;
                                  const matchedPersona = activeTestPersonas.find((tp) =>
                                    tp.name.toLowerCase().includes(participant.name.toLowerCase().split(' ')[0])
                                  );

                                  return (
                                    <div
                                      key={participant.id}
                                      className={`rounded-xl p-4 border transition flex flex-col justify-between space-y-3 ${
                                        canRespond
                                          ? 'bg-slate-800/90 border-emerald-500/70 shadow-lg shadow-emerald-950/20'
                                          : isBound
                                          ? 'bg-slate-800/50 border-slate-700/80'
                                          : 'bg-slate-800/30 border-dashed border-slate-700/60'
                                      }`}
                                    >
                                      <div className="space-y-2.5">
                                        {/* Name & Consent Badge */}
                                        <div className="flex items-start justify-between gap-2">
                                          <div>
                                            <h5 className="text-xs font-bold text-white flex items-center gap-1.5">
                                              {participant.name}
                                            </h5>
                                            <div className="text-[11px] text-slate-400 mt-0.5">
                                              {participant.stated_role || 'Participant'}
                                            </div>
                                          </div>
                                          <span className={`text-[10px] px-2 py-0.5 rounded font-semibold ${getConsentBadgeClass(participant.consent_status)}`}>
                                            {participant.consent_status}
                                          </span>
                                        </div>

                                        {/* Secure Identity Binding Status Banner */}
                                        <div className="text-[11px] space-y-1">
                                          {isBound ? (
                                            <div className="bg-emerald-950/40 border border-emerald-800/60 rounded-lg p-2 space-y-1">
                                              <div className="flex items-center justify-between text-emerald-400 font-medium">
                                                <span className="flex items-center gap-1">
                                                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                                                  Verified Account Bound
                                                </span>
                                                {displayStatus !== 'CONFIRMED' && participant.consent_status === 'PENDING' && (
                                                  <button
                                                    onClick={() => handleUnbindUser(participant.id)}
                                                    disabled={bindingLoading}
                                                    className="text-[10px] text-slate-500 hover:text-rose-400 transition"
                                                    title="Unbind account"
                                                  >
                                                    Unbind
                                                  </button>
                                                )}
                                              </div>
                                              <div className="text-slate-200 font-mono text-[10px] truncate">
                                                {participant.bound_user_email || participant.bound_user_name || String(participant.user_id).slice(0, 8)}
                                              </div>
                                              <div className="text-[9px] text-slate-400">
                                                via {participant.bound_method === 'INVITATION' ? 'Single-Use Token' : 'Direct Assignment'}
                                                {participant.bound_at && ` • ${new Date(participant.bound_at).toLocaleDateString()}`}
                                              </div>
                                            </div>
                                          ) : hasPendingInvitation ? (
                                            <div className="bg-amber-950/40 border border-amber-800/60 rounded-lg p-2 space-y-1">
                                              <div className="flex items-center justify-between text-amber-300 font-medium">
                                                <span className="flex items-center gap-1">
                                                  <Mail className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                                                  Invitation Token Pending
                                                </span>
                                              </div>
                                              <div className="text-[10px] text-slate-400">
                                                Single-use cryptographic token active (hash stored securely).
                                              </div>
                                            </div>
                                          ) : (
                                            <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-2 space-y-1">
                                              <div className="text-slate-400 font-medium flex items-center gap-1">
                                                <UserX className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                                                Unbound Participant
                                              </div>
                                              <div className="text-[10px] text-slate-500">
                                                No account bound. Owner must assign account or generate invite.
                                              </div>
                                            </div>
                                          )}
                                        </div>

                                        {/* Status & Version Notes */}
                                        <div className="text-[11px] text-slate-400">
                                          {participant.consent_status === 'PENDING' ? (
                                            <span className="text-amber-400/90 flex items-center gap-1">
                                              <Clock className="w-3 h-3" /> Awaiting response for v{displayVersion}
                                            </span>
                                          ) : (
                                            <div>
                                              <span className="font-mono text-slate-300">
                                                Responded to v{participant.responded_version || displayVersion}
                                              </span>
                                              {participant.responded_at && (
                                                <span className="text-slate-500 ml-1">
                                                  ({new Date(participant.responded_at).toLocaleDateString()})
                                                </span>
                                              )}
                                            </div>
                                          )}
                                        </div>

                                        {/* Comment note if exists */}
                                        {participant.comment && (
                                          <div className="bg-slate-900/80 border border-slate-700/80 rounded p-2 text-[11px] text-slate-300 italic flex items-start gap-1.5">
                                            <MessageCircle className="w-3 h-3 text-slate-500 shrink-0 mt-0.5" />
                                            <span>"{participant.comment}"</span>
                                          </div>
                                        )}

                                        {/* Active Invitation Link Box */}
                                        {activeInvitation && !isBound && (
                                          <div className="bg-sky-950/40 border border-sky-800/80 rounded-lg p-2 space-y-1 text-[11px]">
                                            <div className="flex items-center justify-between text-sky-300 font-semibold text-[10px]">
                                              <span>Single-Use Token:</span>
                                              <button
                                                onClick={() => {
                                                  navigator.clipboard?.writeText(activeInvitation.invitation_token);
                                                  setCopiedTokenId(participant.id);
                                                  setTimeout(() => setCopiedTokenId(null), 2000);
                                                }}
                                                className="hover:underline flex items-center gap-1 text-[10px]"
                                              >
                                                <Copy className="w-3 h-3" />
                                                {copiedTokenId === participant.id ? 'Copied!' : 'Copy Token'}
                                              </button>
                                            </div>
                                            <div className="font-mono text-[10px] text-sky-200 bg-slate-950 px-1.5 py-0.5 rounded truncate">
                                              {activeInvitation.invitation_token}
                                            </div>
                                            {matchedPersona && userEmail?.toLowerCase() === matchedPersona.email.toLowerCase() ? (
                                              <button
                                                onClick={() => handleClaimInvitation(activeInvitation.invitation_token)}
                                                disabled={claimingInvitation}
                                                className="w-full mt-1 bg-sky-700 hover:bg-sky-600 text-white text-[10px] py-1 rounded font-medium transition flex items-center justify-center gap-1"
                                              >
                                                <ShieldCheck className="w-3 h-3" />
                                                Claim as {userEmail}
                                              </button>
                                            ) : matchedPersona ? (
                                              <button
                                                onClick={async () => {
                                                  await handleSwitchPersona(matchedPersona.email, matchedPersona.name);
                                                  await handleClaimInvitation(activeInvitation.invitation_token);
                                                }}
                                                disabled={claimingInvitation || authLoading}
                                                className="w-full mt-1 bg-sky-700 hover:bg-sky-600 text-white text-[10px] py-1 rounded font-medium transition flex items-center justify-center gap-1"
                                              >
                                                <UserCheck className="w-3 h-3" />
                                                Switch to {matchedPersona.name.split(' ')[0]} &amp; Claim
                                              </button>
                                            ) : userEmail ? (
                                              <button
                                                onClick={() => handleClaimInvitation(activeInvitation.invitation_token)}
                                                disabled={claimingInvitation}
                                                className="w-full mt-1 bg-sky-700 hover:bg-sky-600 text-white text-[10px] py-1 rounded font-medium transition"
                                              >
                                                Claim as {userEmail}
                                              </button>
                                            ) : null}
                                          </div>
                                        )}
                                      </div>

                                      {/* Controls & Response Section */}
                                      <div className="pt-2 border-t border-slate-700/60 space-y-2">
                                        {/* Owner Binding Controls if Unbound */}
                                        {!isBound && (
                                          <div className="space-y-1.5">
                                            {matchedPersona && (
                                              <button
                                                onClick={() => handleAssignUser(participant.id, matchedPersona.email)}
                                                disabled={bindingLoading}
                                                className="w-full bg-emerald-600/90 hover:bg-emerald-500 text-white text-[10px] py-1 px-2 rounded font-semibold transition flex items-center justify-center gap-1.5 shadow-sm"
                                              >
                                                <UserCheck className="w-3 h-3" />
                                                <span>Quick Bind to {matchedPersona.email}</span>
                                              </button>
                                            )}
                                            {!isAssigning ? (
                                              <div className="grid grid-cols-2 gap-1.5">
                                                <button
                                                  onClick={() => {
                                                    setAssigningPartId(participant.id);
                                                    setAssignEmail(matchedPersona ? matchedPersona.email : '');
                                                  }}
                                                  disabled={bindingLoading}
                                                  className="bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 text-[10px] py-1 px-1.5 rounded transition text-center"
                                                >
                                                  Assign User
                                                </button>
                                                <button
                                                  onClick={() => handleGenerateInvitation(participant.id)}
                                                  disabled={bindingLoading}
                                                  className="bg-slate-800 hover:bg-slate-700 border border-slate-700 text-sky-300 text-[10px] py-1 px-1.5 rounded transition text-center inline-flex items-center justify-center gap-1"
                                                >
                                                  <Link2 className="w-2.5 h-2.5" />
                                                  Invite Link
                                                </button>
                                              </div>
                                            ) : (
                                              <div className="space-y-1.5 bg-slate-900 border border-slate-700 p-2 rounded">
                                                <div className="flex items-center justify-between text-[10px] text-slate-300 font-medium">
                                                  <span>Assign by Email:</span>
                                                  <button
                                                    onClick={() => setAssigningPartId(null)}
                                                    className="text-slate-500 hover:text-white"
                                                  >
                                                    <X className="w-2.5 h-2.5" />
                                                  </button>
                                                </div>
                                                <input
                                                  type="email"
                                                  value={assignEmail}
                                                  onChange={(e) => setAssignEmail(e.target.value)}
                                                  placeholder="user@veritas.local"
                                                  className="w-full bg-slate-950 border border-slate-700 text-[11px] text-slate-200 px-2 py-1 rounded"
                                                />
                                                {/* Pre-fill buttons for development personas */}
                                                <div className="flex flex-wrap gap-1">
                                                  {activeTestPersonas.filter((tp) => tp.email !== 'tester@veritas.local').map((tp) => (
                                                    <button
                                                      key={tp.email}
                                                      type="button"
                                                      onClick={() => setAssignEmail(tp.email)}
                                                      className="text-[9px] bg-slate-800 hover:bg-slate-700 text-slate-300 px-1.5 py-0.5 rounded"
                                                    >
                                                      {tp.name.split(' ')[0]}
                                                    </button>
                                                  ))}
                                                </div>
                                                <div className="flex justify-end gap-1 pt-1">
                                                  <button
                                                    onClick={() => setAssigningPartId(null)}
                                                    className="text-[10px] text-slate-400 px-1.5"
                                                  >
                                                    Cancel
                                                  </button>
                                                  <button
                                                    onClick={() => handleAssignUser(participant.id, assignEmail)}
                                                    disabled={bindingLoading || !assignEmail.trim()}
                                                    className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-[10px] font-medium px-2.5 py-0.5 rounded"
                                                  >
                                                    Confirm Assign
                                                  </button>
                                                </div>
                                              </div>
                                            )}
                                          </div>
                                        )}

                                        {/* Authenticated Consent Response Controls */}
                                        {canRespond ? (
                                          <div className="space-y-2">
                                            <div className="text-[10px] font-medium text-emerald-400 flex items-center gap-1">
                                              <CheckCircle2 className="w-3 h-3" /> You are authorized to respond as {participant.name}
                                            </div>

                                            {!isDrawerOpen ? (
                                              <div className="grid grid-cols-3 gap-1.5">
                                                <button
                                                  onClick={() => {
                                                    setActiveRespondingParticipantId(participant.id);
                                                    setResponseActionType('ACCEPTED');
                                                    setResponseComment('');
                                                  }}
                                                  className="bg-emerald-600 hover:bg-emerald-500 text-white text-[11px] font-medium py-1 px-1.5 rounded transition text-center"
                                                >
                                                  Accept
                                                </button>
                                                <button
                                                  onClick={() => {
                                                    setActiveRespondingParticipantId(participant.id);
                                                    setResponseActionType('REQUESTED_CHANGES');
                                                    setResponseComment('');
                                                  }}
                                                  className="bg-purple-700 hover:bg-purple-600 text-white text-[11px] font-medium py-1 px-1.5 rounded transition text-center"
                                                >
                                                  Changes
                                                </button>
                                                <button
                                                  onClick={() => {
                                                    setActiveRespondingParticipantId(participant.id);
                                                    setResponseActionType('REJECTED');
                                                    setResponseComment('');
                                                  }}
                                                  className="bg-rose-700 hover:bg-rose-600 text-white text-[11px] font-medium py-1 px-1.5 rounded transition text-center"
                                                >
                                                  Reject
                                                </button>
                                              </div>
                                            ) : (
                                              <div className="space-y-2 bg-slate-900/90 border border-slate-700 p-2.5 rounded-lg">
                                                <div className="flex items-center justify-between text-[11px]">
                                                  <span className="font-semibold text-slate-200">
                                                    Action: <strong className="text-emerald-400">{responseActionType}</strong>
                                                  </span>
                                                  <button
                                                    onClick={() => setActiveRespondingParticipantId(null)}
                                                    className="text-slate-400 hover:text-white"
                                                  >
                                                    <X className="w-3 h-3" />
                                                  </button>
                                                </div>
                                                <textarea
                                                  rows={2}
                                                  value={responseComment}
                                                  onChange={(e) => setResponseComment(e.target.value)}
                                                  placeholder={
                                                    responseActionType === 'ACCEPTED'
                                                      ? 'Optional comment (e.g. Looks good to me)...'
                                                      : responseActionType === 'REQUESTED_CHANGES'
                                                      ? 'Describe what needs to change (required)...'
                                                      : 'State reason for rejection (required)...'
                                                  }
                                                  className="w-full bg-slate-950 border border-slate-700 text-xs text-slate-200 p-1.5 rounded focus:outline-none focus:border-emerald-500"
                                                />
                                                <div className="flex justify-end gap-1.5">
                                                  <button
                                                    onClick={() => setActiveRespondingParticipantId(null)}
                                                    className="text-[11px] text-slate-400 hover:text-slate-200 px-2 py-0.5"
                                                  >
                                                    Cancel
                                                  </button>
                                                  <button
                                                    onClick={() =>
                                                      handleParticipantRespond(participant.id, responseActionType, responseComment)
                                                    }
                                                    disabled={
                                                      submittingResponse ||
                                                      (responseActionType !== 'ACCEPTED' && !responseComment.trim())
                                                    }
                                                    className={`text-[11px] font-medium px-3 py-1 rounded inline-flex items-center gap-1 ${
                                                      responseActionType === 'ACCEPTED'
                                                        ? 'bg-emerald-600 hover:bg-emerald-500 text-white'
                                                        : responseActionType === 'REQUESTED_CHANGES'
                                                        ? 'bg-purple-600 hover:bg-purple-500 text-white'
                                                        : 'bg-rose-600 hover:bg-rose-500 text-white'
                                                    } disabled:opacity-50`}
                                                  >
                                                    {submittingResponse ? (
                                                      <RefreshCw className="w-3 h-3 animate-spin" />
                                                    ) : (
                                                      <Check className="w-3 h-3" />
                                                    )}
                                                    Confirm {responseActionType}
                                                  </button>
                                                </div>
                                              </div>
                                            )}
                                          </div>
                                        ) : (
                                          <div className="text-[10px] text-slate-500 py-1">
                                            {isBound ? (
                                              <span>Signed in as {userEmail || 'Guest'}. Only the bound account can submit consent.</span>
                                            ) : (
                                              <span>Unbound: claim invitation or assign account to cast consent.</span>
                                            )}
                                          </div>
                                        )}
                                      </div>
                                    </div>
                                  );
                                })}
                              </div>
                            </div>

                            {/* Finalized Status or Explicit Action Info */}
                            <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4 flex flex-wrap items-center justify-between gap-3 text-xs">
                              <div className="flex items-center gap-2 text-slate-400">
                                <Shield className="w-4 h-4 text-emerald-400 shrink-0" />
                                <span>
                                  {displayStatus === 'CONFIRMED'
                                    ? `Agreement successfully confirmed on ${currentAgreement.confirmed_at ? new Date(currentAgreement.confirmed_at).toLocaleDateString() : 'recently'}. Payment authorization is an independent step.`
                                    : 'All required participants must accept current version before status transitions to CONFIRMED. PayPal payment capture requires explicit consent.'}
                                </span>
                              </div>

                              <div className="flex items-center gap-2">
                                {displayStatus === 'CONFIRMED' ? (
                                  <div className="flex items-center gap-2">
                                    <span className="bg-emerald-950/80 border border-emerald-800 text-emerald-400 text-xs px-3 py-1.5 rounded-lg inline-flex items-center gap-1.5 font-medium">
                                      <Check className="w-4 h-4" /> Mutual Consensus Confirmed
                                    </span>
                                    <button
                                      onClick={() => setActiveSubTab('settlement')}
                                      className="bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs px-3.5 py-1.5 rounded-lg inline-flex items-center gap-1.5 transition shadow"
                                    >
                                      <CreditCard className="w-3.5 h-3.5 text-slate-950" />
                                      Settle with PayPal →
                                    </button>
                                  </div>
                                ) : displayStatus === 'REJECTED' ? (
                                  <span className="text-xs text-rose-300 bg-rose-950/60 border border-rose-800 px-3 py-1.5 rounded-lg">
                                    Rejected: {currentAgreement.rejection_reason || 'By participant'}
                                  </span>
                                ) : null}
                              </div>
                            </div>

                            {/* Version History (if agreement has multiple versions) */}
                            {currentAgreement.versions && currentAgreement.versions.length > 0 && (
                              <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4 space-y-3">
                                <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                                  <History className="w-3.5 h-3.5 text-emerald-400" /> Version History ({currentAgreement.versions.length})
                                </h4>
                                <div className="space-y-2">
                                  {currentAgreement.versions.map((v) => (
                                    <div
                                      key={v.id}
                                      className="text-xs bg-slate-800/60 border border-slate-700/60 rounded p-2.5 flex items-center justify-between"
                                    >
                                      <div>
                                        <span className="font-bold text-white mr-2">Version {v.version}</span>
                                        <span className="text-slate-300">{v.title}</span>
                                        <span className="text-slate-500 text-[11px] ml-2">
                                          ({v.terms?.length || 0} terms • {formatMoney(v.total_value, v.currency || activeCurrency)} {v.currency})
                                        </span>
                                      </div>
                                      <span className="text-[10px] text-slate-500 font-mono">
                                        {new Date(v.created_at).toLocaleString()}
                                      </span>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}

                            {/* Audit History Trail */}
                            {(agreementHistoryList.length > 0 || currentAgreement.history.length > 0) && (
                              <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4 space-y-3">
                                <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                                  <Clock className="w-3.5 h-3.5 text-emerald-400" /> Consensus & Agreement Audit Trail
                                </h4>
                                <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
                                  {(agreementHistoryList.length > 0 ? agreementHistoryList : currentAgreement.history).map((entry) => (
                                    <div
                                      key={entry.id}
                                      className="text-xs bg-slate-800/60 border border-slate-700/60 rounded p-2.5 flex items-center justify-between"
                                    >
                                      <div>
                                        <span className="font-semibold text-emerald-400 mr-2">[{entry.action}]</span>
                                        <span className="text-slate-300">{entry.notes || 'Consensus updated'}</span>
                                      </div>
                                      <span className="text-[10px] text-slate-500 font-mono">
                                        {new Date(entry.created_at).toLocaleString()}
                                      </span>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}
                          </>
                        );
                      })()}
                    </div>
                  ) : (
                    <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-8 text-center space-y-2">
                      <Bot className="w-8 h-8 text-slate-500 mx-auto" />
                      <h4 className="text-sm font-semibold text-white">No Agreement Identified</h4>
                      <p className="text-xs text-slate-400 max-w-md mx-auto">
                        Analysis completed, but no formal financial consensus or obligations were found in the conversation.
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* Sub-Tab: PayPal Obligation Settlement & History */}
              {activeSubTab === 'settlement' && (
                <div className="space-y-6">
                  {!currentAgreement && !settlementSummary ? (
                    <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-8 text-center space-y-2">
                      <CreditCard className="w-8 h-8 text-slate-500 mx-auto" />
                      <h4 className="text-sm font-semibold text-white">No Agreement Available</h4>
                      <p className="text-xs text-slate-400 max-w-md mx-auto">
                        An agreement must first be extracted and agreed upon before obligations can be settled.
                      </p>
                    </div>
                  ) : (
                    <>
                      {/* Consensus Guard Banner */}
                      {!settlementSummary?.consensus_achieved &&
                      consensus?.status !== 'CONFIRMED' &&
                      !['CONFIRMED', 'PARTIALLY_SETTLED', 'FULLY_SETTLED'].includes(currentAgreement?.status || '') ? (
                        <div className="bg-amber-950/40 border border-amber-800/80 rounded-xl p-5 space-y-3">
                          <div className="flex items-start gap-3">
                            <AlertCircle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
                            <div className="space-y-1">
                              <h4 className="text-sm font-bold text-amber-300">
                                PayPal Settlement Locked — Mutual Consensus Required
                              </h4>
                              <p className="text-xs text-amber-200/80 leading-relaxed">
                                Obligations cannot be paid or settled until <strong>all participants</strong> have independently accepted Agreement v{consensus?.version || currentAgreement?.version || settlementSummary?.agreement_version || 1}.
                                Current status: <strong className="font-mono text-white">{consensus?.status || currentAgreement?.status || 'PENDING'}</strong> ({consensus?.accepted_count || 0}/{consensus?.total_participants || currentAgreement?.participants?.length || 0} accepted).
                              </p>
                              <div className="pt-2">
                                <button
                                  onClick={() => setActiveSubTab('agreement')}
                                  className="text-xs bg-amber-600 hover:bg-amber-500 text-white font-medium px-3 py-1.5 rounded-lg inline-flex items-center gap-1.5 transition"
                                >
                                  <Scale className="w-3.5 h-3.5" />
                                  Go to Agreement & Participant Consents
                                </button>
                              </div>
                            </div>
                          </div>
                        </div>
                      ) : (
                        <div className="bg-emerald-950/40 border border-emerald-800/80 rounded-xl p-4 flex flex-wrap items-center justify-between gap-3 text-xs">
                          <div className="flex items-center gap-2.5 text-emerald-300">
                            <ShieldCheck className="w-5 h-5 text-emerald-400 shrink-0" />
                            <div>
                              <span className="font-bold">Mutual Consensus Verified (v{consensus?.version || currentAgreement?.version || settlementSummary?.agreement_version || 1})</span>
                              <p className="text-[11px] text-emerald-400/80">
                                All {consensus?.total_participants || currentAgreement?.participants?.length || 3} participants have accepted the agreement. Payment requests are unlocked for PayPal Sandbox processing.
                              </p>
                            </div>
                          </div>
                          <span className="bg-emerald-900/60 border border-emerald-700 text-emerald-300 text-[11px] px-2.5 py-1 rounded font-mono font-semibold">
                            Sandbox Merchant: merchant_sandbox@veritas.local
                          </span>
                        </div>
                      )}

                      {/* Settlement Error Notice */}
                      {settlementError && (
                        <div className="bg-rose-950/60 border border-rose-800 text-rose-300 text-xs p-3 rounded-lg flex items-center gap-2">
                          <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
                          <span>{settlementError}</span>
                        </div>
                      )}

                      {/* Settlement Overview KPI Metrics */}
                      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                        <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl space-y-1">
                          <div className="text-[11px] uppercase tracking-wider text-slate-500 flex items-center justify-between">
                            <span>Total Obligations</span>
                            <Scale className="w-3.5 h-3.5 text-slate-400" />
                          </div>
                          <div className="text-xl font-bold text-white">
                            {formatMoney(settlementSummary?.total_obligations_amount, settlementSummary?.currency || activeCurrency)}
                            <span className="text-xs text-slate-400 ml-1 font-normal">{settlementSummary?.currency || activeCurrency}</span>
                          </div>
                        </div>

                        <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl space-y-1">
                          <div className="text-[11px] uppercase tracking-wider text-slate-500 flex items-center justify-between">
                            <span>Settled (Captured)</span>
                            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                          </div>
                          <div className="text-xl font-bold text-emerald-400">
                            {formatMoney(settlementSummary?.total_completed_amount, settlementSummary?.currency || activeCurrency)}
                            <span className="text-xs text-slate-400 ml-1 font-normal">{settlementSummary?.currency || activeCurrency}</span>
                          </div>
                        </div>

                        <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl space-y-1">
                          <div className="text-[11px] uppercase tracking-wider text-slate-500 flex items-center justify-between">
                            <span>Pending In-Flight</span>
                            <Clock className="w-3.5 h-3.5 text-amber-400" />
                          </div>
                          <div className="text-xl font-bold text-amber-300">
                            {formatMoney(settlementSummary?.total_pending_amount, settlementSummary?.currency || activeCurrency)}
                            <span className="text-xs text-slate-400 ml-1 font-normal">{settlementSummary?.currency || activeCurrency}</span>
                          </div>
                        </div>

                        <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl space-y-1">
                          <div className="text-[11px] uppercase tracking-wider text-slate-500 flex items-center justify-between">
                            <span>Outstanding Balance</span>
                            <DollarSign className="w-3.5 h-3.5 text-rose-400" />
                          </div>
                          <div className="text-xl font-bold text-rose-300">
                            {formatMoney(settlementSummary?.outstanding_balance, settlementSummary?.currency || activeCurrency)}
                            <span className="text-xs text-slate-400 ml-1 font-normal">{settlementSummary?.currency || activeCurrency}</span>
                          </div>
                        </div>
                      </div>

                      {/* Settlement Progress Bar */}
                      {settlementSummary && Number(settlementSummary.total_obligations_amount) > 0 && (
                        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 space-y-2">
                          <div className="flex justify-between items-center text-xs">
                            <span className="font-semibold text-slate-300 flex items-center gap-2">
                              <span>Settlement Completion Progress</span>
                              <span className={`text-[10px] px-2 py-0.5 rounded font-mono ${getSettlementBadgeClass(settlementSummary.settlement_status)}`}>
                                {settlementSummary.settlement_status}
                              </span>
                            </span>
                            <span className="font-mono text-slate-400 text-xs">
                              {Math.min(100, Math.round((Number(settlementSummary.total_completed_amount) / Number(settlementSummary.total_obligations_amount)) * 100))}%
                            </span>
                          </div>
                          <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden border border-slate-700/60">
                            <div
                              className="h-2 bg-emerald-500 transition-all duration-500"
                              style={{
                                width: `${Math.min(100, Math.round((Number(settlementSummary.total_completed_amount) / Number(settlementSummary.total_obligations_amount)) * 100))}%`,
                              }}
                            />
                          </div>
                        </div>
                      )}

                      {/* Recipient Routing Notice Banner */}
                      <div className="bg-slate-900/90 border border-amber-500/30 rounded-xl p-3.5 flex items-start gap-3 text-xs text-slate-300">
                        <ShieldCheck className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                        <div>
                          <strong className="text-amber-300">Sandbox Merchant Receiver Disclosure:</strong> All settlement payments are credited to the platform Sandbox merchant account (<code className="text-amber-200">merchant_sandbox@veritas.local</code>). Funds are not automatically disbursed to individual creditor bank accounts or held in escrow.
                        </div>
                      </div>

                      {/* Verified Obligations List */}
                      <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 space-y-4">
                        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-3">
                          <div>
                            <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                              <Receipt className="w-3.5 h-3.5 text-amber-400" />
                              Agreement Obligations & Settlement Actions
                            </h4>
                            <p className="text-[11px] text-slate-400 mt-0.5">
                              Server-enforced amounts and participants extracted from verified conversation intelligence.
                            </p>
                          </div>
                          {settlementSummary && (
                            <button
                              onClick={() => {
                                const agrId = currentAgreement?.id || settlementSummary?.agreement_id;
                                if (agrId) loadSettlementSummary(agrId);
                              }}
                              disabled={loadingSettlement}
                              className="text-xs text-slate-400 hover:text-white inline-flex items-center gap-1 transition"
                            >
                              <RefreshCw className={`w-3 h-3 ${loadingSettlement ? 'animate-spin' : ''}`} />
                              <span>Refresh Status</span>
                            </button>
                          )}
                        </div>

                        {settlementSummary?.obligations && settlementSummary.obligations.length > 0 ? (
                          <div className="space-y-3">
                            {settlementSummary.obligations.map((ob) => {
                              const req = ob.payment_request;
                              const isSettled = ob.is_settled;
                              const settledAmount = Number(ob.settled_amount || 0);
                              const outstandingAmount = Number(ob.outstanding_amount ?? ob.amount);
                              const hasActiveReq = req && req.status === 'PENDING';
                              const canInitiate = ob.is_eligible_for_payment && !isSettled;

                              return (
                                <div
                                  key={ob.obligation_id}
                                  className={`p-4 rounded-xl border transition ${
                                    isSettled
                                      ? 'bg-slate-800/40 border-emerald-800/60'
                                      : settledAmount > 0
                                      ? 'bg-slate-800/60 border-blue-800/60'
                                      : hasActiveReq
                                      ? 'bg-slate-800/60 border-amber-700/60'
                                      : 'bg-slate-800/80 border-slate-700/80'
                                  }`}
                                >
                                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                                    <div className="space-y-1.5 flex-1 min-w-0">
                                      <div className="flex flex-wrap items-center gap-2">
                                        <h5 className="text-sm font-bold text-white truncate">{ob.title}</h5>
                                        {isSettled ? (
                                          <span className="text-[10px] bg-emerald-950 text-emerald-400 border border-emerald-800 px-2 py-0.5 rounded font-medium flex items-center gap-1">
                                            <CheckCircle2 className="w-3 h-3" /> SETTLED
                                          </span>
                                        ) : settledAmount > 0 ? (
                                          <span className="text-[10px] bg-blue-950 text-blue-300 border border-blue-800 px-2 py-0.5 rounded font-medium flex items-center gap-1">
                                            <Clock className="w-3 h-3" /> PARTIALLY SETTLED ({formatMoney(settledAmount, ob.currency || activeCurrency)} paid, {formatMoney(outstandingAmount, ob.currency || activeCurrency)} rem.)
                                          </span>
                                        ) : hasActiveReq ? (
                                          <span className="text-[10px] bg-amber-950 text-amber-300 border border-amber-800 px-2 py-0.5 rounded font-medium flex items-center gap-1">
                                            <Clock className="w-3 h-3" /> PAYMENT REQUEST PENDING
                                          </span>
                                        ) : (
                                          <span className="text-[10px] bg-slate-700 text-slate-300 px-2 py-0.5 rounded font-mono">
                                            UNPAID
                                          </span>
                                        )}
                                      </div>

                                      <p className="text-xs text-slate-300">{ob.description}</p>

                                      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-400 pt-1">
                                        <div>
                                          Payer (Debtor): <strong className="text-rose-300">{ob.debtor_name || 'Unassigned'}</strong>
                                        </div>
                                        <div>→</div>
                                        <div>
                                          Payee (Creditor): <strong className="text-emerald-400">{ob.creditor_name || 'Unassigned'}</strong>
                                        </div>
                                        {req?.latest_capture && (
                                          <div className="font-mono text-[11px] text-slate-400">
                                            Capture ID: <span className="text-emerald-300">{req.latest_capture.paypal_capture_id}</span>
                                          </div>
                                        )}
                                      </div>

                                      {!ob.is_eligible_for_payment && !isSettled && (
                                        <div className="text-[11px] text-amber-400/90 flex items-center gap-1 pt-1">
                                          <AlertCircle className="w-3 h-3 shrink-0" />
                                          <span>Ineligibility: {ob.ineligibility_reason}</span>
                                        </div>
                                      )}
                                    </div>

                                    {/* Amount and Action Buttons */}
                                    <div className="flex flex-col sm:flex-row md:flex-col items-end justify-between gap-2.5 shrink-0">
                                      <div className="text-right">
                                        <div className="text-lg font-bold font-mono text-white">
                                          {formatMoney(ob.amount, ob.currency || activeCurrency)}{' '}
                                          <span className="text-xs font-normal text-slate-400">{ob.currency}</span>
                                        </div>
                                        {settledAmount > 0 && !isSettled && (
                                          <div className="text-[11px] font-mono text-emerald-400">
                                            {formatMoney(settledAmount, ob.currency || activeCurrency)} settled / {formatMoney(outstandingAmount, ob.currency || activeCurrency)} due
                                          </div>
                                        )}
                                      </div>

                                      <div className="flex items-center gap-2">
                                        {isSettled ? (
                                          <div className="flex items-center gap-2">
                                            {req && (
                                              <button
                                                onClick={() => handleViewPaymentHistory(req)}
                                                className="text-xs text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 border border-slate-700 px-2.5 py-1.5 rounded-lg transition inline-flex items-center gap-1"
                                              >
                                                <History className="w-3 h-3 text-emerald-400" />
                                                <span>Audit</span>
                                              </button>
                                            )}
                                            {req?.can_refund && req.latest_capture && (
                                              <button
                                                onClick={() => {
                                                  setRefundingCapture(req.latest_capture!);
                                                  setRefundReason('');
                                                }}
                                                className="text-xs text-rose-300 hover:text-rose-200 bg-rose-950/60 hover:bg-rose-900/60 border border-rose-800 px-2.5 py-1.5 rounded-lg transition inline-flex items-center gap-1"
                                              >
                                                <RotateCcw className="w-3 h-3" />
                                                <span>Refund</span>
                                              </button>
                                            )}
                                          </div>
                                        ) : hasActiveReq ? (
                                          <div className="flex items-center gap-2">
                                            {req.can_cancel && (
                                              <button
                                                onClick={() => handleCancelRequest(req.id)}
                                                disabled={cancellingRequestId === req.id}
                                                className="text-xs text-slate-400 hover:text-rose-300 px-2 py-1 transition"
                                                title="Cancel Request"
                                              >
                                                {cancellingRequestId === req.id ? (
                                                  <RefreshCw className="w-3 h-3 animate-spin" />
                                                ) : (
                                                  'Cancel'
                                                )}
                                              </button>
                                            )}
                                            <button
                                              onClick={() => handlePayExistingRequest(req)}
                                              className="bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs px-3.5 py-1.5 rounded-lg inline-flex items-center gap-1.5 transition shadow"
                                            >
                                              <CreditCard className="w-3.5 h-3.5" />
                                              <span>Pay with PayPal</span>
                                            </button>
                                          </div>
                                        ) : (
                                          <button
                                            onClick={() => handleOpenPaymentReview(ob)}
                                            disabled={!canInitiate}
                                            className="bg-amber-500 hover:bg-amber-400 disabled:opacity-40 disabled:hover:bg-amber-500 text-slate-950 font-bold text-xs px-3.5 py-1.5 rounded-lg inline-flex items-center gap-1.5 transition shadow"
                                          >
                                            <CreditCard className="w-3.5 h-3.5" />
                                            <span>Review & Settle</span>
                                          </button>
                                        )}
                                      </div>
                                    </div>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        ) : (
                          <p className="text-xs text-slate-400 italic">No structured obligations found for this agreement.</p>
                        )}
                      </div>

                      {/* Payment History Timeline & Audit Log */}
                      {settlementSummary?.payment_requests && settlementSummary.payment_requests.length > 0 && (
                        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 space-y-4">
                          <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                            <History className="w-3.5 h-3.5 text-emerald-400" />
                            PayPal Payment Records & Audit History ({settlementSummary.payment_requests.length})
                          </h4>

                          <div className="overflow-x-auto">
                            <table className="w-full text-left text-xs">
                              <thead>
                                <tr className="border-b border-slate-800 text-slate-400 font-medium">
                                  <th className="py-2 pr-3">Created</th>
                                  <th className="py-2 px-3">Obligation</th>
                                  <th className="py-2 px-3">Participants</th>
                                  <th className="py-2 px-3">Amount</th>
                                  <th className="py-2 px-3">PayPal IDs</th>
                                  <th className="py-2 px-3">Status</th>
                                  <th className="py-2 pl-3 text-right">Action</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-slate-800/60">
                                {settlementSummary.payment_requests.map((pr) => (
                                  <tr key={pr.id} className="text-slate-300 hover:bg-slate-800/40 transition">
                                    <td className="py-2.5 pr-3 text-slate-400 font-mono text-[11px]">
                                      {new Date(pr.created_at).toLocaleDateString()}
                                    </td>
                                    <td className="py-2.5 px-3 max-w-[160px] truncate text-white">
                                      {pr.debtor_name} share
                                    </td>
                                    <td className="py-2.5 px-3 text-[11px]">
                                      <span className="text-rose-300">{pr.debtor_name}</span> →{' '}
                                      <span className="text-emerald-400">{pr.creditor_name}</span>
                                    </td>
                                    <td className="py-2.5 px-3 font-mono font-semibold text-white">
                                      {formatMoney(pr.amount, pr.currency || activeCurrency)} {pr.currency}
                                    </td>
                                    <td className="py-2.5 px-3 font-mono text-[10px] text-slate-400">
                                      {pr.latest_capture ? (
                                        <div className="text-emerald-400">
                                          Cap: {pr.latest_capture.paypal_capture_id.slice(0, 12)}...
                                        </div>
                                      ) : pr.active_order ? (
                                        <div>Ord: {pr.active_order.paypal_order_id.slice(0, 12)}...</div>
                                      ) : (
                                        '—'
                                      )}
                                    </td>
                                    <td className="py-2.5 px-3">
                                      <span className={`text-[10px] px-2 py-0.5 rounded font-semibold ${getPaymentRequestStatusBadgeClass(pr.status)}`}>
                                        {pr.status}
                                      </span>
                                    </td>
                                    <td className="py-2.5 pl-3 text-right">
                                      <button
                                        onClick={() => handleViewPaymentHistory(pr)}
                                        className="text-[11px] text-sky-400 hover:underline"
                                      >
                                        Timeline
                                      </button>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}

              {/* Sub-Tab 2: Financial Settlement & Net Balances */}
              {activeSubTab === 'financial' && (
                <div className="space-y-5">
                  {!financialSummary ? (
                    <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-8 text-center space-y-2">
                      <DollarSign className="w-8 h-8 text-slate-500 mx-auto" />
                      <p className="text-xs text-slate-400">Run Gemini analysis to compute deterministic settlement shares.</p>
                    </div>
                  ) : (
                    <div className="space-y-5">
                      {/* Top Metric Cards */}
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl">
                          <div className="text-[11px] uppercase tracking-wider text-slate-500">Total Group Expenses</div>
                          <div className="text-2xl font-bold text-white mt-1">
                            {formatMoney(financialSummary.total_expenses, financialSummary.currency || activeCurrency)}
                            <span className="text-xs text-slate-400 ml-1 font-normal">{financialSummary.currency}</span>
                          </div>
                        </div>

                        <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl">
                          <div className="text-[11px] uppercase tracking-wider text-slate-500">Split Method</div>
                          <div className="text-lg font-bold text-emerald-400 mt-1 uppercase">
                            {financialSummary.split_method} SPLIT
                          </div>
                        </div>

                        <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl">
                          <div className="text-[11px] uppercase tracking-wider text-slate-500">Discrepancy Check</div>
                          <div className="text-lg font-bold text-white mt-1">
                            {formatMoney(financialSummary.discrepancy_cents, financialSummary.currency || activeCurrency)}
                            <span className="text-xs text-emerald-400 ml-1.5 font-normal">Penny Safe ✓</span>
                          </div>
                        </div>
                      </div>

                      {/* Participant Shares & Net Balances */}
                      <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 space-y-3">
                        <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
                          Participant Fair Share Breakdown
                        </h4>
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                          {financialSummary.participant_shares.map((share, idx) => (
                            <div
                              key={idx}
                              className="bg-slate-800/70 border border-slate-700/80 p-3.5 rounded-lg space-y-2 text-xs"
                            >
                              <div className="flex items-center justify-between font-semibold text-white">
                                <span>{share.participant_name}</span>
                                <span
                                  className={`text-[10px] px-2 py-0.5 rounded font-mono ${
                                    share.net_balance > 0
                                      ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                                      : share.net_balance < 0
                                      ? 'bg-rose-950 text-rose-300 border border-rose-800'
                                      : 'bg-slate-700 text-slate-300'
                                  }`}
                                >
                                  {share.net_balance > 0 ? 'OVERPAID' : share.net_balance < 0 ? 'UNDERPAID' : 'EVEN'}
                                </span>
                              </div>
                              <div className="space-y-1 text-slate-400 text-[11px]">
                                <div className="flex justify-between">
                                  <span>Paid:</span>
                                  <span className="font-mono text-slate-200">{formatMoney(share.paid_amount, financialSummary.currency || activeCurrency)}</span>
                                </div>
                                <div className="flex justify-between">
                                  <span>Fair Share:</span>
                                  <span className="font-mono text-slate-200">{formatMoney(share.fair_share, financialSummary.currency || activeCurrency)}</span>
                                </div>
                                <div className="flex justify-between border-t border-slate-700 pt-1 font-semibold">
                                  <span className="text-slate-300">Net Balance:</span>
                                  <span
                                    className={`font-mono ${
                                      share.net_balance > 0
                                        ? 'text-emerald-400'
                                        : share.net_balance < 0
                                        ? 'text-rose-400'
                                        : 'text-slate-300'
                                    }`}
                                  >
                                    {share.net_balance > 0 ? '+' : ''}{formatMoney(share.net_balance, financialSummary.currency || activeCurrency)}
                                  </span>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Minimal Settlement Transfers */}
                      <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 space-y-3">
                        <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                          <DollarSign className="w-3.5 h-3.5 text-emerald-400" /> Minimal Settlement Transfers
                        </h4>
                        {financialSummary.settlement_transfers.length === 0 ? (
                          <p className="text-xs text-slate-500 italic">No transfers required. All accounts are settled.</p>
                        ) : (
                          <div className="space-y-2">
                            {financialSummary.settlement_transfers.map((t, idx) => (
                              <div
                                key={idx}
                                className="bg-slate-800/80 border border-slate-700 p-3 rounded-lg flex items-center justify-between text-xs"
                              >
                                <div className="flex items-center gap-2">
                                  <span className="font-semibold text-rose-300">{t.from_participant}</span>
                                  <ChevronRight className="w-3.5 h-3.5 text-slate-500" />
                                  <span className="text-slate-400">pays</span>
                                  <ChevronRight className="w-3.5 h-3.5 text-slate-500" />
                                  <span className="font-semibold text-emerald-400">{t.to_participant}</span>
                                </div>
                                <div className="font-mono font-bold text-white bg-slate-900 px-3 py-1 rounded border border-slate-700">
                                  {formatMoney(t.amount, t.currency || activeCurrency)} {t.currency}
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>

                      {/* Disclaimer Box */}
                      <div className="bg-slate-900/40 border border-slate-800 rounded-lg p-3 text-[11px] text-slate-400 italic">
                        {financialSummary.disclaimer}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Sub-Tab 3: Evidence Grounded Financial Facts */}
              {activeSubTab === 'facts' && (
                <div className="space-y-4">
                  {!analysis || analysis.financial_facts.length === 0 ? (
                    <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-8 text-center text-xs text-slate-400">
                      No financial facts extracted yet. Run Gemini analysis first.
                    </div>
                  ) : (
                    <div className="space-y-3">
                      <div className="flex items-center justify-between text-xs text-slate-400">
                        <span>Extracted Facts ({analysis.financial_facts.length})</span>
                        <span>Verbatim Evidence Grounded</span>
                      </div>

                      {analysis.financial_facts.map((fact) => (
                        <div
                          key={fact.id}
                          className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 space-y-2.5 text-xs"
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="flex items-center gap-2">
                              <span
                                className={`text-[10px] font-bold px-2 py-0.5 rounded border ${getFactClassificationClass(
                                  fact.classification
                                )}`}
                              >
                                {fact.classification}
                              </span>
                              <span className="font-bold text-white font-mono text-sm">
                                {formatMoney(fact.amount, fact.currency || activeCurrency)} {fact.currency}
                              </span>
                            </div>

                            <div className="text-[11px] text-slate-400 font-mono">
                              Confidence: {(fact.confidence * 100).toFixed(0)}%
                            </div>
                          </div>

                          <div className="text-slate-300 font-medium">
                            {fact.description}
                          </div>

                          <div className="flex items-center gap-3 text-slate-400 text-[11px]">
                            {fact.payer_name && (
                              <span>
                                Payer: <strong className="text-slate-200">{fact.payer_name}</strong>
                              </span>
                            )}
                            {fact.recipient_name && (
                              <span>
                                Recipient: <strong className="text-slate-200">{fact.recipient_name}</strong>
                              </span>
                            )}
                          </div>

                          {/* Verbatim quote */}
                          <div className="bg-slate-950/60 border-l-2 border-emerald-500 p-2.5 rounded text-slate-300 text-[11px] italic font-sans flex items-start justify-between gap-2">
                            <span>"{fact.evidence_quote}"</span>
                            <span className="text-[10px] font-mono text-slate-500 shrink-0">
                              Messages: [{fact.message_indices.map((i) => `#${i}`).join(', ')}]
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Sub-Tab 4: Ambiguities & Clarifications */}
              {activeSubTab === 'ambiguities' && (
                <div className="space-y-4">
                  {!analysis || analysis.ambiguities.length === 0 ? (
                    <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-8 text-center text-xs text-slate-400">
                      No ambiguities detected by Gemini.
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {analysis.ambiguities.map((amb) => (
                        <div
                          key={amb.id}
                          className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 space-y-3 text-xs"
                        >
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              <span
                                className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                                  amb.severity === 'HIGH'
                                    ? 'bg-rose-950 text-rose-300 border border-rose-800'
                                    : amb.severity === 'MEDIUM'
                                    ? 'bg-amber-950 text-amber-300 border border-amber-800'
                                    : 'bg-slate-800 text-slate-300 border border-slate-700'
                                }`}
                              >
                                {amb.severity} SEVERITY
                              </span>
                              <span className="font-semibold text-slate-200">{amb.ambiguity_type}</span>
                            </div>

                            <span
                              className={`text-[10px] px-2 py-0.5 rounded font-mono ${
                                amb.status === 'RESOLVED'
                                  ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                                  : 'bg-amber-950 text-amber-300 border border-amber-800'
                              }`}
                            >
                              {amb.status}
                            </span>
                          </div>

                          <p className="text-slate-300">{amb.description}</p>

                          {/* Clarification Question Prompt */}
                          <div className="bg-amber-950/20 border border-amber-800/40 p-3 rounded-lg space-y-1.5">
                            <div className="text-[11px] font-semibold text-amber-400 flex items-center gap-1">
                              <HelpCircle className="w-3.5 h-3.5" /> Clarification Question:
                            </div>
                            <div className="text-xs text-white font-medium">{amb.clarification_question}</div>
                          </div>

                          {/* Verbatim quote */}
                          <div className="text-slate-400 text-[11px] italic">
                            Evidence: "{amb.evidence_quote}" (msgs: [{amb.message_indices.map((i) => `#${i}`).join(', ')}])
                          </div>

                          {/* Resolution view or action buttons */}
                          {amb.status === 'RESOLVED' ? (
                            <div className="bg-emerald-950/40 border border-emerald-800 p-2.5 rounded text-xs text-emerald-300 flex items-center justify-between">
                              <span>
                                <strong>Resolved:</strong> {amb.resolution_text}
                              </span>
                              <span className="text-[10px] text-slate-500 font-mono">
                                {amb.resolved_at ? new Date(amb.resolved_at).toLocaleTimeString() : ''}
                              </span>
                            </div>
                          ) : (
                            <div className="space-y-2 pt-1 border-t border-slate-800">
                              <div className="text-[11px] text-slate-400 font-medium">Suggested Options:</div>
                              <div className="flex flex-wrap gap-1.5">
                                {amb.suggested_options.map((opt, oIdx) => (
                                  <button
                                    key={oIdx}
                                    onClick={() => handleResolveAmbiguity(amb.id, opt)}
                                    disabled={resolvingId === amb.id}
                                    className="bg-slate-800 hover:bg-emerald-950 hover:text-emerald-300 hover:border-emerald-700 border border-slate-700 text-slate-300 text-xs px-2.5 py-1.5 rounded transition text-left"
                                  >
                                    {opt}
                                  </button>
                                ))}
                              </div>

                              <div className="flex items-center gap-2 pt-1">
                                <input
                                  type="text"
                                  value={customResolution[amb.id] || ''}
                                  onChange={(e) =>
                                    setCustomResolution({
                                      ...customResolution,
                                      [amb.id]: e.target.value,
                                    })
                                  }
                                  placeholder="Or enter custom clarification text..."
                                  className="flex-1 bg-slate-900 border border-slate-700 text-xs text-slate-200 px-2.5 py-1.5 rounded"
                                />
                                <button
                                  onClick={() =>
                                    handleResolveAmbiguity(amb.id, customResolution[amb.id] || '')
                                  }
                                  disabled={resolvingId === amb.id || !customResolution[amb.id]?.trim()}
                                  className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs px-3 py-1.5 rounded font-medium inline-flex items-center gap-1"
                                >
                                  {resolvingId === amb.id ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
                                  Resolve
                                </button>
                              </div>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Sub-Tab 5: Raw Normalized Messages Stream */}
              {activeSubTab === 'messages' && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                      Normalized Message Stream
                    </h3>
                    <span className="text-[11px] text-slate-500">Order preserved & timestamps UTC converted</span>
                  </div>

                  <div className="space-y-2.5 max-h-[500px] overflow-y-auto pr-1">
                    {currentConversation.messages.map((msg) => {
                      if (msg.is_system_message) {
                        return (
                          <div
                            key={msg.id}
                            className="bg-slate-900/40 border border-dashed border-slate-700/60 rounded-lg p-2.5 text-xs text-slate-400 italic text-center"
                          >
                            <div className="text-[10px] uppercase font-semibold text-slate-500 mb-0.5">
                              System Notification [#{msg.order_index}]
                            </div>
                            {msg.message_body}
                          </div>
                        );
                      }

                      return (
                        <div
                          key={msg.id}
                          className="bg-slate-900/80 border border-slate-800 rounded-lg p-3 space-y-1.5"
                        >
                          <div className="flex items-center justify-between text-xs">
                            <span className="font-semibold text-emerald-400 flex items-center gap-1.5">
                              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                              {msg.sender_name || 'Unknown Participant'}
                            </span>
                            <span className="text-slate-500 font-mono text-[11px]">
                              {msg.original_timestamp
                                ? new Date(msg.original_timestamp).toLocaleString()
                                : 'No Timestamp'}{' '}
                              (#{msg.order_index})
                            </span>
                          </div>
                          <div className="text-xs text-slate-200 whitespace-pre-wrap font-sans">
                            {msg.message_body}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="bg-slate-800/30 border border-slate-700/40 rounded-xl p-12 text-center flex flex-col items-center justify-center space-y-3 h-full min-h-[400px]">
              <div className="p-3 bg-slate-800 rounded-full text-slate-500">
                <MessageSquare className="w-8 h-8" />
              </div>
              <h3 className="text-sm font-semibold text-slate-300">No Conversation Selected</h3>
              <p className="text-xs text-slate-500 max-w-sm">
                Paste a conversation transcript or upload a .txt WhatsApp export on the left to test ingestion and view normalized output.
              </p>
              <button
                onClick={() => setActiveSubTab('whatsapp')}
                className="mt-2 px-3.5 py-1.5 bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/30 rounded-lg text-xs font-semibold transition flex items-center gap-2"
              >
                <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
                Open WhatsApp Live & Mock Hub
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Stage 4 Pre-Payment Review Modal */}
      {isReviewModalOpen && selectedObligationForPayment && currentAgreement && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 animate-fade-in">
          <div className="bg-slate-900 border border-slate-700/90 rounded-2xl max-w-lg w-full p-6 shadow-2xl relative text-slate-100">
            <button
              onClick={() => setIsReviewModalOpen(false)}
              className="absolute top-4 right-4 text-slate-400 hover:text-white transition-colors"
            >
              <X className="w-5 h-5" />
            </button>

            <div className="flex items-center gap-3 mb-5">
              <div className="w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400">
                <Receipt className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-base font-bold text-white">Review Payment Settlement</h3>
                <p className="text-xs text-slate-400">Cryptographically bound ACCORD obligation</p>
              </div>
            </div>

            <div className="bg-slate-800/80 border border-slate-700 rounded-xl p-4 space-y-2.5 text-xs mb-5">
              <div className="flex justify-between items-center border-b border-slate-700/60 pb-2">
                <span className="text-slate-400">Agreement:</span>
                <span className="font-semibold text-white">
                  {currentAgreement.title} (v{consensus?.version || currentAgreement.version})
                </span>
              </div>
              <div className="flex justify-between items-center border-b border-slate-700/60 pb-2">
                <span className="text-slate-400">Obligation:</span>
                <span className="font-semibold text-white">{selectedObligationForPayment.title}</span>
              </div>
              <div className="flex justify-between items-center border-b border-slate-700/60 pb-2">
                <span className="text-slate-400">Payer (Debtor):</span>
                <span className="font-semibold text-rose-300">{selectedObligationForPayment.debtor_name}</span>
              </div>
              <div className="flex justify-between items-center border-b border-slate-700/60 pb-2">
                <span className="text-slate-400">Intended Recipient (Creditor):</span>
                <span className="font-semibold text-emerald-300">{selectedObligationForPayment.creditor_name}</span>
              </div>
              <div className="flex justify-between items-center border-b border-slate-700/60 pb-2">
                <span className="text-slate-400">Receiver Merchant Account:</span>
                <span className="font-mono text-[11px] text-amber-300 truncate max-w-[200px]">
                  {selectedObligationForPayment.payment_request?.receiver_merchant_account || 'merchant_sandbox@veritas.local'}
                </span>
              </div>
              <div className="flex justify-between items-center pt-1 text-sm">
                <span className="font-semibold text-slate-200">Amount to Settle:</span>
                <span className="font-mono font-bold text-emerald-400 text-base">
                  {formatMoney(selectedObligationForPayment.amount, selectedObligationForPayment.currency || activeCurrency)} {selectedObligationForPayment.currency}
                </span>
              </div>
            </div>

            {/* ARGUS Autonomous Subsystem Intent Interception Notice */}
            <div className="flex items-start gap-2.5 p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-[11px] text-emerald-200 mb-3 leading-relaxed">
              <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
              <div>
                <strong className="text-emerald-300">ARGUS Subsystem Automated Interception:</strong> Clicking checkout automatically routes this transaction intent through the ARGUS 4-worker AI forensic engine (Domain Forensics, Catalog Inspector, Price Anomaly AI) for risk scoring, logs to the ARGUS Audit Ledger, and dispatches a verified WhatsApp settlement notice.
              </div>
            </div>

            {/* Mandatory Disclaimer */}
            <div className="flex items-start gap-2.5 p-3 rounded-lg bg-blue-500/10 border border-blue-500/20 text-[11px] text-blue-200 mb-5 leading-relaxed">
              <ShieldCheck className="w-4 h-4 text-blue-400 shrink-0 mt-0.5" />
              <span>
                This payment settles an obligation verified under ACCORD Agreement v{consensus?.version || currentAgreement.version}.
                Payments are processed through the VERITAS Sandbox Merchant Account. The exact amount and currency are server-enforced and cannot be altered.
              </span>
            </div>

            <div className="flex justify-end gap-2.5">
              <button
                onClick={() => setIsReviewModalOpen(false)}
                className="px-4 py-2 text-xs text-slate-400 hover:text-white transition"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmAndProceedToCheckout}
                disabled={creatingPaymentReq}
                className="bg-amber-500 hover:bg-amber-400 disabled:opacity-50 text-slate-950 font-bold text-xs px-4 py-2 rounded-xl inline-flex items-center gap-1.5 transition shadow"
              >
                {creatingPaymentReq ? (
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <CreditCard className="w-3.5 h-3.5 text-slate-950" />
                )}
                <span>Proceed to PayPal Checkout</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* PayPal Checkout Modal */}
      {activePaymentRequestForCheckout && (
        <PayPalCheckoutModal
          isOpen={isPaymentModalOpen}
          onClose={() => {
            setIsPaymentModalOpen(false);
            setActivePaymentRequestForCheckout(null);
          }}
          token={token}
          paymentRequest={activePaymentRequestForCheckout}
          onPaymentSuccess={handlePaymentSuccess}
        />
      )}

      {/* Refund Confirmation Modal */}
      {refundingCapture && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 animate-fade-in">
          <div className="bg-slate-900 border border-slate-700/90 rounded-2xl max-w-md w-full p-6 shadow-2xl relative text-slate-100 space-y-4">
            <button
              onClick={() => setRefundingCapture(null)}
              className="absolute top-4 right-4 text-slate-400 hover:text-white"
            >
              <X className="w-5 h-5" />
            </button>

            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-rose-500/10 border border-rose-500/30 flex items-center justify-center text-rose-400">
                <RotateCcw className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-base font-bold text-white">Confirm PayPal Refund</h3>
                <p className="text-xs text-slate-400">Reverts settled obligation status</p>
              </div>
            </div>

            <div className="bg-slate-800/80 border border-slate-700 p-3 rounded-lg text-xs space-y-1.5 font-mono">
              <div className="flex justify-between">
                <span className="text-slate-400">Capture ID:</span>
                <span className="text-emerald-400">{refundingCapture.paypal_capture_id}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Amount:</span>
                <span className="text-white">{formatMoney(refundingCapture.amount, refundingCapture.currency || activeCurrency)} {refundingCapture.currency}</span>
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">Refund Reason (optional)</label>
              <input
                type="text"
                value={refundReason}
                onChange={(e) => setRefundReason(e.target.value)}
                placeholder="e.g. Agreement modification / mutual cancellation"
                className="w-full bg-slate-950 border border-slate-700 text-xs text-slate-200 px-3 py-2 rounded-lg"
              />
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setRefundingCapture(null)}
                className="px-3 py-1.5 text-xs text-slate-400 hover:text-white"
              >
                Cancel
              </button>
              <button
                onClick={handleRefundCapture}
                disabled={refundingLoading}
                className="bg-rose-600 hover:bg-rose-500 disabled:opacity-50 text-white font-medium text-xs px-4 py-2 rounded-xl inline-flex items-center gap-1.5 shadow"
              >
                {refundingLoading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <RotateCcw className="w-3.5 h-3.5" />}
                Confirm Refund
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Payment History Audit Timeline Modal */}
      {paymentHistoryModalReq && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 animate-fade-in">
          <div className="bg-slate-900 border border-slate-700/90 rounded-2xl max-w-lg w-full p-6 shadow-2xl relative text-slate-100 space-y-4">
            <button
              onClick={() => setPaymentHistoryModalReq(null)}
              className="absolute top-4 right-4 text-slate-400 hover:text-white"
            >
              <X className="w-5 h-5" />
            </button>

            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
                <History className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-base font-bold text-white">Payment Transition Timeline</h3>
                <p className="text-xs text-slate-400">Audit trail of state transitions & captures</p>
              </div>
            </div>

            <div className="bg-slate-800/80 border border-slate-700 p-3 rounded-lg text-xs space-y-1">
              <div className="flex justify-between">
                <span className="text-slate-400">Payment Request ID:</span>
                <span className="font-mono text-slate-200">{paymentHistoryModalReq.id.slice(0, 16)}...</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Payer → Payee:</span>
                <span className="text-white">{paymentHistoryModalReq.debtor_name} → {paymentHistoryModalReq.creditor_name}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Amount:</span>
                <span className="font-mono font-bold text-emerald-400">
                  {formatMoney(paymentHistoryModalReq.amount, paymentHistoryModalReq.currency || activeCurrency)} {paymentHistoryModalReq.currency}
                </span>
              </div>
            </div>

            <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
              {loadingPaymentHistory ? (
                <div className="text-center py-6 text-slate-400 text-xs flex items-center justify-center gap-2">
                  <RefreshCw className="w-4 h-4 animate-spin text-emerald-400" />
                  <span>Loading audit transitions...</span>
                </div>
              ) : paymentHistoryList.length === 0 ? (
                <p className="text-center py-4 text-xs text-slate-500 italic">No transition history logged yet.</p>
              ) : (
                paymentHistoryList.map((entry, idx) => (
                  <div
                    key={entry.id || idx}
                    className="p-3 bg-slate-800/60 border border-slate-700/70 rounded-lg text-xs space-y-1"
                  >
                    <div className="flex items-center justify-between font-semibold">
                      <span className="text-emerald-400 font-mono">[{entry.action}]</span>
                      <span className="text-[10px] text-slate-400 font-mono">
                        {new Date(entry.created_at).toLocaleString()}
                      </span>
                    </div>
                    <div className="text-slate-300">
                      Transition: <span className="font-mono text-amber-300">{entry.from_status || 'NONE'}</span> →{' '}
                      <span className="font-mono text-emerald-300">{entry.to_status}</span>
                    </div>
                    {entry.details && Object.keys(entry.details).length > 0 && (
                      <div className="bg-slate-950 p-1.5 rounded font-mono text-[10px] text-slate-400 overflow-x-auto">
                        {JSON.stringify(entry.details)}
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>

            <div className="flex justify-end pt-2">
              <button
                onClick={() => setPaymentHistoryModalReq(null)}
                className="px-4 py-1.5 bg-slate-800 hover:bg-slate-700 text-white text-xs rounded-lg transition"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
