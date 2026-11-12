path = r'X:\hackathon\static\index.html'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

target = '<body class="min-h-screen pb-16">\n\n  <!-- Navbar -->'

header_snippet = '''<body class="min-h-screen pb-16">

  <!-- VERITAS Unified Global Shell Header (Matches ACCORD and Core Platform) -->
  <header class="border-b border-slate-800 bg-slate-950/95 backdrop-blur px-6 py-3 flex items-center justify-between sticky top-0 z-50">
    <div class="flex items-center gap-6">
      <a href="/veritas" class="flex items-center gap-2.5 text-white font-bold text-base tracking-wide hover:opacity-90" title="Return to VERITAS Home">
        <div class="bg-emerald-600 p-1.5 rounded-lg text-white">
          <i data-lucide="shield" class="w-4 h-4"></i>
        </div>
        <span>VERITAS</span>
      </a>
      <nav class="flex items-center gap-4 text-xs font-medium">
        <a href="/veritas" class="text-slate-300 hover:text-white flex items-center gap-1.5 transition">
          <i data-lucide="home" class="w-3.5 h-3.5 text-slate-400"></i>
          VERITAS Home
        </a>
        <a href="/accord/ingest" class="text-slate-300 hover:text-emerald-400 flex items-center gap-1.5 transition">
          <i data-lucide="message-square" class="w-3.5 h-3.5 text-emerald-400"></i>
          ACCORD Ingestion
        </a>
        <a href="/argus" class="text-cyan-400 font-semibold flex items-center gap-1.5 transition">
          <i data-lucide="shield-check" class="w-3.5 h-3.5 text-cyan-400"></i>
          ARGUS Interceptor
        </a>
      </nav>
    </div>
    <div class="flex items-center gap-3">
      <a href="/veritas" class="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/30 text-xs font-semibold transition" title="Close Argus & Return to Veritas Platform">
        <i data-lucide="arrow-left" class="w-3.5 h-3.5"></i>
        <span>Close Argus & Return Home</span>
      </a>
    </div>
  </header>

  <!-- Navbar -->'''

# Normalize newlines
text_norm = text.replace('\r\n', '\n')
target_norm = target.replace('\r\n', '\n')
header_snippet_norm = header_snippet.replace('\r\n', '\n')

assert target_norm in text_norm, "Target not found in static/index.html!"
new_text = text_norm.replace(target_norm, header_snippet_norm)

# Also update the script cache-busting to ?v=3 in static/index.html
new_text = new_text.replace('/js/ag_grid_setup.js?v=2', '/js/ag_grid_setup.js?v=3')
new_text = new_text.replace('/js/app.js?v=2', '/js/app.js?v=3')

with open(path, 'w', encoding='utf-8') as f:
    f.write(new_text)

print("Successfully injected unified header and bumped cache-busting to v3!")
