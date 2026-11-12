import os

def update_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()

    target = '''def _load_env_if_present():
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())'''

    replacement = '''def _load_env_if_present():
    cur = os.path.abspath(__file__)
    for _ in range(5):
        cur = os.path.dirname(cur)
        env_file = os.path.join(cur, ".env")
        if os.path.exists(env_file):
            try:
                with open(env_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            val = v.strip().strip("'\\\"")
                            if val and "mock" not in val.lower():
                                os.environ[k.strip()] = val
                            else:
                                os.environ.setdefault(k.strip(), val)
            except Exception:
                pass'''

    text_norm = text.replace('\r\n', '\n')
    target_norm = target.replace('\r\n', '\n')
    if target_norm in text_norm:
        text_norm = text_norm.replace(target_norm, replacement.replace('\r\n', '\n'))
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text_norm)
        print(f"Updated {path}")
    else:
        print(f"Target not found in {path}")

update_file(r'X:\hackathon\Veritas\backend\app\argus\paypal_gateway.py')
update_file(r'X:\hackathon\argus\paypal_gateway.py')
