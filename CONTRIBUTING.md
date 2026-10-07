# Contributing

Work on a dedicated branch and open a draft PR with the concrete problem, change and observed validation. Keep generated previews private and retain existing evaluation labels and the budget ledger.

Use the exact environment setup and test commands in [README.md](README.md). Local fast checks after installation:

```sh
ruff check services evals
pytest
npm run lint --prefix apps/web
npm run typecheck --prefix apps/web
npm run test:renderer --prefix apps/web
```

Browser and Docker integration checks are distinct from contract tests; record which actually ran, their sample sizes, and unavailable services. CI runs fixture-provider checks without live provider credentials. Never substitute fixture responses for a live job, report unknown costs as zero, or make paid requests without an explicitly available validation budget.

Preserve tenant isolation, URL/network protections and verification gates. Include regression evidence when changing them. Do not add real credentials or client data to fixtures. Follow [security guidance](docs/SECURITY.md) for suspected vulnerabilities.
