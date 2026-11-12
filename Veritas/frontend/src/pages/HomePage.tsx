import React from 'react';
import { Link } from 'react-router-dom';
import { ConnectivityIndicator } from '../components/ConnectivityIndicator';
import { ShieldCheck, MessageSquareText, Lock, Terminal, ArrowRight } from 'lucide-react';

export const HomePage: React.FC = () => {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4 sm:px-6 lg:px-8 max-w-4xl mx-auto">
      <div className="text-center mb-8">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-950/80 text-emerald-400 border border-emerald-800/60 mb-4">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
          VERITAS Unified Platform: ACCORD &amp; ARGUS Active
        </div>
        <h1 className="text-4xl font-extrabold tracking-tight text-white sm:text-5xl">
          VERITAS Platform
        </h1>
        <p className="mt-3 text-base text-slate-400 max-w-2xl mx-auto">
          Unified conversational intelligence and merchant trust assessment platform.
        </p>
      </div>

      {/* Backend Live Connectivity Widget */}
      <ConnectivityIndicator />

      {/* Product Architecture Boundary Overview */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-8 w-full max-w-2xl">
        {/* ACCORD Card with CTA */}
        <div className="bg-slate-800/40 border border-slate-700/60 rounded-xl p-5 flex flex-col justify-between hover:border-emerald-500/50 transition">
          <div>
            <div className="flex items-center gap-2.5 text-emerald-400 font-semibold text-sm mb-1.5">
              <MessageSquareText className="w-5 h-5" />
              <span>ACCORD Subsystem</span>
            </div>
            <p className="text-xs text-slate-400 mb-4 leading-relaxed">
              Conversation ingestion, WhatsApp export parsing (iOS &amp; Android), participant extraction, and normalized message persistence.
            </p>
          </div>
          <Link
            to="/accord/ingest"
            className="inline-flex items-center justify-center gap-1.5 w-full bg-emerald-600 hover:bg-emerald-500 text-white font-medium py-2 px-3 rounded-lg text-xs transition"
          >
            <span>Open Ingestion Test Bench</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        {/* ARGUS Card - Active Subsystem */}
        <div className="bg-slate-800/40 border border-cyan-500/40 hover:border-cyan-400 hover:shadow-lg hover:shadow-cyan-950/40 rounded-xl p-5 flex flex-col justify-between transition">
          <div>
            <div className="flex items-center gap-2.5 text-cyan-400 font-semibold text-sm mb-1.5">
              <ShieldCheck className="w-5 h-5" />
              <span>ARGUS Fraud Interceptor</span>
            </div>
            <p className="text-xs text-slate-400 mb-4 leading-relaxed">
              Real-time merchant identity verification, domain forensics, 4-worker parallel AI matrix, and PayPal 2-phase pre-settlement authorization interceptor.
            </p>
          </div>
          <Link
            to="/argus"
            className="inline-flex items-center justify-center gap-2 w-full py-2 px-3 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-xs transition"
          >
            <span>Open ARGUS Interceptor</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      </div>

      <div className="mt-8 text-xs text-slate-500 flex items-center gap-4">
        <span className="flex items-center gap-1">
          <Lock className="w-3.5 h-3.5 text-slate-400" /> JWT + Argon2/Bcrypt Security
        </span>
        <span>•</span>
        <span className="flex items-center gap-1">
          <Terminal className="w-3.5 h-3.5 text-slate-400" /> FastAPI + React 18 + Tailwind
        </span>
      </div>
    </div>
  );
};
