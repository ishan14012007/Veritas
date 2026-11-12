with open('X:/hackathon/Veritas/frontend/dist/assets/index-CJCEZJVU.js', 'r', encoding='utf-8') as f:
    text = f.read()

target = 'children:s.jsxs(Ix,{children:[s.jsx(al,{path:"/",element:s.jsx(Zg,{})}),s.jsx(al,{path:"/accord/ingest",element:s.jsx(Cy,{})}),s.jsx(al,{path:"*",element:s.jsx(ey,{})})]})'

assert target in text, f"Target route string not found!"

# Add /veritas and /accord routes pointing to HomePage (Zg)
replacement = 'children:s.jsxs(Ix,{children:[s.jsx(al,{path:"/",element:s.jsx(Zg,{})}),s.jsx(al,{path:"/veritas",element:s.jsx(Zg,{})}),s.jsx(al,{path:"/accord",element:s.jsx(Zg,{})}),s.jsx(al,{path:"/accord/ingest",element:s.jsx(Cy,{})}),s.jsx(al,{path:"*",element:s.jsx(ey,{})})]})'

new_text = text.replace(target, replacement)

# In the header nav, let's also make sure both ACCORD and ARGUS are linked!
# Find the header nav
# Original: s.jsx("nav",{className:"flex items-center gap-4 text-xs font-medium",children:s.jsxs(cs,{to:"/accord/ingest",className:"text-slate-300 hover:text-emerald-400 flex items-center gap-1.5 transition",children:[s.jsx($i,{className:"w-3.5 h-3.5 text-emerald-400"}),"ACCORD Ingestion"]})})
nav_old = 'children:s.jsxs(cs,{to:"/accord/ingest",className:"text-slate-300 hover:text-emerald-400 flex items-center gap-1.5 transition",children:[s.jsx($i,{className:"w-3.5 h-3.5 text-emerald-400"}),"ACCORD Ingestion"]})'

# We can make nav include both ACCORD and ARGUS!
nav_new = 'children:[s.jsxs(cs,{to:"/accord/ingest",className:"text-slate-300 hover:text-emerald-400 flex items-center gap-1.5 transition",children:[s.jsx($i,{className:"w-3.5 h-3.5 text-emerald-400"}),"ACCORD Ingestion"]}),s.jsxs("a",{href:"/argus",className:"text-slate-300 hover:text-cyan-400 flex items-center gap-1.5 transition ml-3",children:[s.jsx($i,{className:"w-3.5 h-3.5 text-cyan-400"}),"ARGUS Interceptor"]})]'

if nav_old in new_text:
    new_text = new_text.replace(nav_old, nav_new)
    print("Header nav enhanced with ARGUS link!")
else:
    print("Note: nav_old not matched, skipping nav update.")

with open('X:/hackathon/Veritas/frontend/dist/assets/index-CJCEZJVU.js', 'w', encoding='utf-8') as f:
    f.write(new_text)

print("Routes successfully patched!")
