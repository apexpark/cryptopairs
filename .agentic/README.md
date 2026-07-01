# CryptoPairs Agentic Adapter

This directory contains the project-local adapter for bounded agentic loops.

Local policy has highest priority. This adapter cannot grant permissions beyond
`AGENTS.md`, `docs/AGENT_STATE.md`, `docs/playbooks/remote-agent-bootstrap.md`,
and the current operator instruction.

Use these files as the local harness:

- `.agentic/project.yaml` - adapter metadata and default-deny authorities.
- `.agentic/policies/project-loop-policy.md` - local loop policy.
- `.agentic/templates/loop-spec.json` - machine-checkable loop spec template.
- `.agentic/templates/loop-state.json` - durable state template for each run.
- `.agentic/playbooks/repository-development-loop.md` - manual loop procedure.
- `.agentic/registers/loop-runs.md` - accepted-change and failure register.

This adapter does not authorize schedulers, deployment, merge, secrets, external
connectors, host access, production jobs, live trading, or background loops.
