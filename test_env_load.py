import os

cur = os.path.abspath(r'X:\hackathon\Veritas\backend\app\argus\paypal_gateway.py')
for _ in range(5):
    cur = os.path.dirname(cur)
    env_file = os.path.join(cur, '.env')
    if os.path.exists(env_file):
        print('Found:', env_file)
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    val = v.strip().strip('\'"')
                    if val and 'mock' not in val.lower():
                        os.environ[k.strip()] = val

print('Loaded client ID len:', len(os.getenv('PAYPAL_CLIENT_ID', '')))
print('Loaded secret len:', len(os.getenv('PAYPAL_CLIENT_SECRET', '')))
