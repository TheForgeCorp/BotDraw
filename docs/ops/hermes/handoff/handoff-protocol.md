# Handoff protocol (Nav offline)

When Nav will be away, send Ink:

```text
HANDOFF
Away until: <ISO datetime>
Standing orders:
- Accept holds within capacity? yes/no
- Publish IG? yes/no
- Etsy fulfill digital? yes/no
- Ad boosts? yes/no / cap override
- Escalate P0 to: <backup human?>
Notes:
```

Ink acknowledges with checklist + what will wait for Nav return (date confirms, cash, calls still blocked unless backup assigned).
