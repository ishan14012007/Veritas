import React from 'react';
import { Link } from 'react-router-dom';
import { HelpCircle, ArrowLeft } from 'lucide-react';

export const NotFoundPage: React.FC = () => {
  return (
    <div className="flex flex-col items-center justify-center min-h-[70vh] px-4 text-center">
      <HelpCircle className="w-16 h-16 text-slate-500 mb-4" />
      <h1 className="text-3xl font-bold text-white mb-2">404 — Page Not Found</h1>
      <p className="text-sm text-slate-400 max-w-md mb-6">
        The route you requested does not exist on the VERITAS platform development foundation.
      </p>
      <Link
        to="/"
        className="inline-flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-semibold px-4 py-2 rounded-lg transition"
      >
        <ArrowLeft className="w-4 h-4" />
        Return to Home
      </Link>
    </div>
  );
};

