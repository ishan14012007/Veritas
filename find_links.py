import re

with open('X:/hackathon/static/index.html', 'r', encoding='utf-8') as f:
    text = f.read()

print('SRC:')
for s in re.findall(r'src=["\']([^"\']+)["\']', text):
    print(' ', s)

print('HREF:')
for h in re.findall(r'href=["\']([^"\']+)["\']', text):
    print(' ', h)
