path = r'X:\hackathon\Veritas\frontend\dist\assets\index-CJCEZJVU.js'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

target = 's.jsxs("div",{className:"bg-slate-800/40 border border-cyan-500/50 rounded-xl p-5 flex flex-col justify-between hover:border-cyan-400 transition shadow-lg shadow-cyan-950/20",'

replacement = 's.jsxs("div",{className:"bg-slate-800/40 border border-slate-700/60 rounded-xl p-5 flex flex-col justify-between hover:border-emerald-500/50 transition",'

assert target in text, "Target card container not found in bundle!"
new_text = text.replace(target, replacement)

with open(path, 'w', encoding='utf-8') as f:
    f.write(new_text)

print("ARGUS card border updated to match ACCORD border-slate-700/60 with hover:border-emerald-500/50!")
