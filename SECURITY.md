# Security

## Pasteup is a local tool

Pasteup reads and writes files at whatever paths it is given — that is its job.
It has no accounts and no authentication, so run it only on your own machine,
bound to `127.0.0.1` (the default):

```bash
pasteup                  # fine: only this machine can reach it
pasteup --host 0.0.0.0   # don't: anyone on your network can read and write your files
```

Two guards back that up:

- **Host check.** Requests are only answered when addressed to `localhost` or
  `127.0.0.1`. That stops a web page that points its own domain at your machine
  (DNS rebinding) from driving the app through your browser. If you deliberately
  serve the app under another name, list it in `PASTEUP_ALLOWED_HOSTS`
  (comma-separated).
- **Bounded requests.** Output files stay inside the output folder you chose, and
  page size and video length are capped, so a single request cannot overwrite
  files elsewhere or exhaust memory.

## Reporting a vulnerability

Please report privately rather than in a public issue: use **Report a
vulnerability** on the repository's Security tab (GitHub private vulnerability
reporting). Include what an attacker needs, what they get, and a minimal
reproduction.
