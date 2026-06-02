# Razorpay Production Integration — ReplyOS
**Last Updated**: 2026-05-29T19:27:25+05:30

---

## ⚠️ CURRENT STATUS: TEST MODE ACTIVE

```
PAYMENT_MODE=test
RAZORPAY_KEY_ID=rzp_test_Suof5OJrcLYP9M
```
Real money NOT being charged. Must migrate to `rzp_live_*` for production.

---

## Environment Variables

| Variable | Description | Current Value |
|---|---|---|
| `RAZORPAY_KEY_ID` | Public client key | `rzp_test_Suof5OJrcLYP9M` |
| `RAZORPAY_KEY_SECRET` | Private HMAC key (backend only) | Set in `.env` |
| `RAZORPAY_WEBHOOK_SECRET` | Webhook verification key | Set in `.env` |
| `NEXT_PUBLIC_RAZORPAY_KEY` | Public key for frontend checkout | Dynamic from API response |
| `PAYMENT_MODE` | `test` or `production` | `test` |

---

## SDK Integration

```python
import razorpay
client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

# Order creation
order = client.order.create({
    "amount": 99900,   # paise
    "currency": "INR",
    "receipt": f"order_{tenant_id}_{plan_tier}",
    "payment_capture": 1
})

# Signature verification
client.utility.verify_payment_signature({
    'razorpay_order_id': order_id,
    'razorpay_payment_id': payment_id,
    'razorpay_signature': signature
})

# Webhook verification
client.utility.verify_webhook_signature(
    raw_body.decode("utf-8"),
    signature,
    settings.RAZORPAY_WEBHOOK_SECRET
)
```

---

## Verified Order

**Test order created and verified**:
```json
{
  "razorpay_order_id": "order_SupuBpnujM1TuS",
  "amount": 99900,
  "currency": "INR",
  "razorpay_key_id": "rzp_test_Suof5OJrcLYP9M"
}
```

Database record:
```
id: 00d01b75-cdec-4635-9410-5049fe95c93e
tenant_id: eee18224-de89-41c3-9fb3-e4fdebb532eb
order_id: order_SupuBpnujM1TuS
amount: 99900
status: created
plan_tier: starter
created_at: 2026-05-28 15:37:43
```

---

## Bug History

### Bug: `razorpay==1.4.3` (non-existent package)
- **Date**: 2026-05-28
- **Fix**: Changed to `razorpay==2.0.1`

### Bug: Mock key `rzp_test_mockKeyId12345` in .env
- **Date**: 2026-05-28
- **Fix**: Replaced with real test credentials from Razorpay dashboard

### Bug: `httpx` custom POST instead of SDK client
- **Date**: 2026-05-28
- **Fix**: Refactored to official `razorpay.Client` with structured error handling

---

## Production Migration Checklist

To switch to live production mode:
- [ ] Obtain `rzp_live_*` API key ID and secret from Razorpay dashboard
- [ ] Set `PAYMENT_MODE=production` in `.env`
- [ ] Set `RAZORPAY_KEY_ID=rzp_live_xxxx`
- [ ] Set `RAZORPAY_KEY_SECRET=<live_secret>`
- [ ] Configure webhook URL in Razorpay dashboard: `http://144.24.126.153:8080/api/v1/payments/webhook`
- [ ] Set `RAZORPAY_WEBHOOK_SECRET` to match dashboard webhook secret
- [ ] Rebuild containers: `docker compose build --no-cache backend worker && docker compose up -d`
- [ ] Test one ₹1 transaction with real card
- [ ] Verify `payment_transactions` table shows `status: captured`
- [ ] Verify tenant subscription `period_end` extended by 30 days
