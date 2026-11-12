import React, { useEffect, useState } from 'react';
import { checkHealth, checkReadiness, HealthStatus, ReadinessStatus, API_BASE_URL } from '../lib/api';
import { CheckCircle2, XCircle, RefreshCw, Server, Database, Layers } from 'lucide-react';

export const ConnectivityIndicator: React.FC = () => {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [readiness, setReadiness] = useState<ReadinessStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = async () => {
    try {
      const [h, r] = await Promise.all([
        checkHealth().catch((err) => {
          throw new Error(`API unreachable: ${err.message}`);
        }),
        checkReadiness().catch(() => null),
      ]);
      setHealth(h);
      setReadiness(r);
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to connect to backend server');
      // Only clear if we didn't already have a valid health check
      setHealth((prev) => prev);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 3000);
    return () => clearInterval(interval);
  }, []);

  const effectiveTarget = API_BASE_URL.startsWith('http')
    ? API_BASE_URL
    : (typeof window !== 'undefined' ? `${window.location.origin}${API_BASE_URL}` : API_BASE_URL);

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-5 shadow-lg max-w-xl w-full">
      <div className="flex items-center justify-between border-b border-slate-700 pb-3 mb-4">
        <div>
          <h2 className="text-lg font-semibold text-white">Backend Connectivity Status</h2>
          <p className="text-xs text-slate-400 font-mono mt-0.5 flex items-center gap-1.5">
            <span>Target: {effectiveTarget}</span>
            {!API_BASE_URL.startsWith('http') && (
              <span className="bg-slate-900 text-emerald-400 border border-emerald-800/60 px-1.5 py-0.2 rounded text-[10px]">
                Vite Proxy
              </span>
            )}
          </p>
        </div>
        <button
          onClick={fetchStatus}
          disabled={loading}
          className="flex items-center gap-1.5 text-xs bg-slate-700 hover:bg-slate-600 active:bg-slate-800 text-slate-200 px-3 py-1.5 rounded transition disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Check Now
        </button>
      </div>

      {error ? (
        <div className="bg-red-950/60 border border-red-800/80 rounded p-3 mb-4 text-sm text-red-200 flex items-start gap-2.5">
          <XCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold">Connection Error:</span> {error}
            <p className="text-xs text-red-300/80 mt-1">
              Ensure the FastAPI backend server is running on port 8000 (<code className="bg-red-900/60 px-1 py-0.5 rounded">uvicorn app.main:app --reload</code>).
            </p>
          </div>
        </div>
      ) : null}

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {/* Backend API Liveness */}
        <div className="bg-slate-900/80 border border-slate-800 rounded p-3 flex flex-col items-center justify-center text-center">
          <Server className="w-6 h-6 text-slate-400 mb-1.5" />
          <span className="text-xs text-slate-400 uppercase tracking-wide font-medium">FastAPI Server</span>
          <div className="mt-2 flex items-center gap-1.5 text-sm font-semibold">
            {loading && !health ? (
              <span className="text-slate-400 flex items-center gap-1">
                <RefreshCw className="w-3.5 h-3.5 animate-spin text-slate-500" /> Checking...
              </span>
            ) : health?.status === 'ok' ? (
              <span className="text-emerald-400 flex items-center gap-1">
                <CheckCircle2 className="w-4 h-4" /> Healthy
              </span>
            ) : (
              <span className="text-red-400 flex items-center gap-1">
                <XCircle className="w-4 h-4" /> Offline
              </span>
            )}
          </div>
        </div>

        {/* PostgreSQL Database Readiness */}
        <div className="bg-slate-900/80 border border-slate-800 rounded p-3 flex flex-col items-center justify-center text-center">
          <Database className="w-6 h-6 text-slate-400 mb-1.5" />
          <span className="text-xs text-slate-400 uppercase tracking-wide font-medium">PostgreSQL</span>
          <div className="mt-2 flex items-center gap-1.5 text-sm font-semibold">
            {loading && !readiness ? (
              <span className="text-slate-400 flex items-center gap-1">
                <RefreshCw className="w-3.5 h-3.5 animate-spin text-slate-500" /> Checking...
              </span>
            ) : readiness?.database ? (
              <span className="text-emerald-400 flex items-center gap-1">
                <CheckCircle2 className="w-4 h-4" /> Connected
              </span>
            ) : (
              <span className="text-amber-400 flex items-center gap-1">
                <XCircle className="w-4 h-4" /> Standby / Off
              </span>
            )}
          </div>
        </div>

        {/* Redis & ARQ Readiness */}
        <div className="bg-slate-900/80 border border-slate-800 rounded p-3 flex flex-col items-center justify-center text-center">
          <Layers className="w-6 h-6 text-slate-400 mb-1.5" />
          <span className="text-xs text-slate-400 uppercase tracking-wide font-medium">Redis / ARQ</span>
          <div className="mt-2 flex items-center gap-1.5 text-sm font-semibold">
            {loading && !readiness ? (
              <span className="text-slate-400 flex items-center gap-1">
                <RefreshCw className="w-3.5 h-3.5 animate-spin text-slate-500" /> Checking...
              </span>
            ) : readiness?.redis ? (
              <span className="text-emerald-400 flex items-center gap-1">
                <CheckCircle2 className="w-4 h-4" /> Connected
              </span>
            ) : (
              <span className="text-amber-400 flex items-center gap-1">
                <XCircle className="w-4 h-4" /> Standby / Off
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

