import re

with open('X:/hackathon/static/js/app.js', 'r', encoding='utf-8') as f:
    text1 = f.read()
with open('X:/hackathon/static/js/ag_grid_setup.js', 'r', encoding='utf-8') as f:
    text2 = f.read()

print('Endpoints in app.js:')
for m in sorted(set(re.findall(r'["\'`/]api/v1/[a-zA-Z0-9_\-/]+', text1))):
    print(' ', m)

print('Endpoints in ag_grid_setup.js:')
for m in sorted(set(re.findall(r'["\'`/]api/v1/[a-zA-Z0-9_\-/]+', text2))):
    print(' ', m)
