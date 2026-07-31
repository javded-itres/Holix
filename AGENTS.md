# Agent notes (Helix workspace)

## Deploy policy for Holix Studio / related products

- **Never deploy to production without explicit user confirmation** in the current turn/conversation.
- «На прод» / production Actions / `201.24.113.209` / `holix-studio.ru` — only after the user clearly asks **and** you should still confirm if the request is ambiguous.
- Test environments (e.g. `172.17.3.130`) may be deployed when the user requests test.
- Prior approval is not reusable for later production deploys.
