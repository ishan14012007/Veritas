path = r'X:\hackathon\Veritas\frontend\dist\assets\index-CJCEZJVU.js'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Update the top right badges
target_badge = 'children:s.jsx("span",{className:"bg-emerald-950/80 text-emerald-400 px-2.5 py-1 rounded border border-emerald-800/60 font-mono",children:"Stage 2: ACCORD Ingestion"})'

# Replace with both ACCORD and ARGUS badges
replacement_badge = 'children:[s.jsx("span",{className:"bg-emerald-950/80 text-emerald-400 px-2.5 py-1 rounded border border-emerald-800/60 font-mono flex items-center gap-1",children:"Stage 2: ACCORD Ingestion"}),s.jsxs("span",{className:"bg-emerald-950/80 text-emerald-400 px-2.5 py-1 rounded border border-emerald-800/60 font-mono flex items-center gap-1.5",children:[s.jsx("span",{className:"w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"}),"ARGUS Interceptor Active"]})]'

assert target_badge in text, "Target badge not found!"
text = text.replace(target_badge, replacement_badge)
print("Badge updated successfully!")

# 2. Update the ARGUS Interceptor button color to match the ACCORD button (green: bg-emerald-600 hover:bg-emerald-500)
target_btn = 'bg-cyan-600 hover:bg-cyan-500 text-white font-medium py-2 px-3 rounded-lg text-xs transition cursor-pointer font-semibold'
replacement_btn = 'bg-emerald-600 hover:bg-emerald-500 text-white font-medium py-2 px-3 rounded-lg text-xs transition cursor-pointer font-semibold'

assert target_btn in text, "Target button not found!"
text = text.replace(target_btn, replacement_btn)
print("Button color updated to emerald green!")

with open(path, 'w', encoding='utf-8') as f:
    f.write(text)

print("Patch applied successfully!")
