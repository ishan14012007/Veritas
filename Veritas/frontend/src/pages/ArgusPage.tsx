import React from 'react';
import { ExternalLink, ShieldCheck } from 'lucide-react';

export const ArgusPage: React.FC = () => {
  return (
    <div className="flex flex-col w-full h-[calc(100vh-65px)] bg-[#080c14]">
      <div className="bg-slate-950/90 border-b border-slate-800/80 px-4 py-2 flex items-center justify-between text-xs text-slate-400">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-cyan-400" />
          <span className="font-semibold text-slate-200">ARGUS Trust Gateway &amp; Pre-Settlement Interceptor</span>
          <span className="bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 px-2 py-0.5 rounded text-[10px]">
            Live SOC &amp; Fraud Matrix
          </span>
        </div>
        <a
          href="/argus"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 text-cyan-400 hover:text-cyan-300 font-medium transition"
        >
          <span>Open Fullscreen Tab</span>
          <ExternalLink className="w-3 h-3" />
        </a>
      </div>
      <iframe
        src="/argus"
        title="ARGUS Merchant Trust Dashboard"
        className="w-full flex-1 border-0"
      />
    </div>
  );
};

