import React from 'react';
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';
import { HomePage } from './pages/HomePage';
import { NotFoundPage } from './pages/NotFoundPage';
import { IngestionTestPage } from './features/accord/IngestionTestPage';
import { ArgusPage } from './pages/ArgusPage';
import { Shield, MessageSquare } from 'lucide-react';

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <div className="min-h-screen flex flex-col bg-slate-900 text-slate-100">
        {/* Development Shell Header */}
        <header className="border-b border-slate-800 bg-slate-950/70 backdrop-blur px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <Link to="/" className="flex items-center gap-2.5 text-white font-bold text-lg tracking-wide hover:opacity-90">
              <div className="bg-emerald-600 p-1.5 rounded-lg text-white">
                <Shield className="w-5 h-5" />
              </div>
              <span>VERITAS</span>
            </Link>
            <nav className="flex items-center gap-4 text-xs font-medium">
              <Link
                to="/accord/ingest"
                className="text-slate-300 hover:text-emerald-400 flex items-center gap-1.5 transition"
              >
                <MessageSquare className="w-3.5 h-3.5 text-emerald-400" />
                ACCORD Ingestion
              </Link>
              <Link
                to="/argus"
                className="text-slate-300 hover:text-cyan-400 flex items-center gap-1.5 transition"
              >
                <Shield className="w-3.5 h-3.5 text-cyan-400" />
                ARGUS Interceptor
              </Link>
            </nav>
          </div>
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <span className="bg-emerald-950/80 text-emerald-400 px-2.5 py-1 rounded border border-emerald-800/60 font-mono flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
              Stage 2: ACCORD Ingestion
            </span>
            <span className="bg-emerald-950/80 text-emerald-400 px-2.5 py-1 rounded border border-emerald-800/60 font-mono flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
              ARGUS Interceptor Active
            </span>
          </div>
        </header>

        {/* Main Content Area */}
        <main className="flex-1">
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/accord/ingest" element={<IngestionTestPage />} />
            <Route path="/argus" element={<ArgusPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </main>

        {/* Minimal Footer */}
        <footer className="border-t border-slate-800 py-4 px-6 text-center text-xs text-slate-500">
          VERITAS Platform &copy; 2026 &bull; Core Infrastructure Foundation &amp; ACCORD Subsystem
        </footer>
      </div>
    </BrowserRouter>
  );
};

export default App;
