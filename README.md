# Lenovo Stock Watch

Independent free monitor for Lenovo `21NS0012US` (ThinkPad X1 Carbon Gen 13 Aura Edition).

Runs on GitHub Actions — a **different IP and ASN** from the primary VPS poller,
so an IP-level block on one node does not blind the other.

- Polls Lenovo OpenAPI over plain HTTP JSON (no browser, no cookies, no JS).
- Stdlib only — no pip install.
- Alerts on Telegram **only on change**.
- State in `state.json`, committed back each run.

Secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
