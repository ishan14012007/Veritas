path = r'X:\hackathon\static\js\app.js'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

target = 'script.src = `https://www.paypal.com/sdk/js?client-id=${paypalConfig.client_id}&intent=authorize&currency=USD&disable-funding=card,credit`;'
replacement = 'script.src = `https://www.paypal.com/sdk/js?client-id=${paypalConfig.client_id}&intent=authorize&currency=USD&components=buttons&enable-funding=card`;'

assert target in text, "Target not found in app.js!"
new_text = text.replace(target, replacement)

with open(path, 'w', encoding='utf-8') as f:
    f.write(new_text)

print("Updated app.js to enable live PayPal SDK and Debit/Credit Card options!")
