# GitHub Action

For interactive reviews in Codex or Claude Code, use the
[coding-agent integration](coding-agents.md). This page covers PR automation
that runs independently of a local agent session.

The composite Action lives in `action/`. It installs only this public workspace.
Create `.github/workflows/genesis.yml` in your application's repository after
replacing `REVIEWED_FULL_COMMIT_SHA` with an actual reviewed client commit:

```yaml
name: Genesis review
on: [pull_request]
permissions:
  contents: read
  issues: read
  pull-requests: read
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262
        with:
          fetch-depth: 0
          persist-credentials: false
      - uses: GenesisAgentInfra/genesis/action@REVIEWED_FULL_COMMIT_SHA
        with:
          base: ${{ github.event.pull_request.base.sha }}
          service-url: ${{ vars.GENESIS_SERVICE_URL }}
          api-key: ${{ secrets.GENESIS_API_KEY }}
```

Set repository Variable `GENESIS_SERVICE_URL` to
`https://semantic-api-production.up.railway.app` and store a personal Genesis key
issued by the Genesis team in Secret `GENESIS_API_KEY`. This connects to the
Genesis team's hosted service; you do not need to deploy a server.
The Action writes the readable report to the Job Summary and uploads only
`summary.md`, `report.md`, and `report.json`. It does not post PR comments.
Missing keys, forks, `pull_request_target`, or unverified PR identity force
offline analysis; a usable partial report is not a failed transport step.
Do not change the trigger to `pull_request_target` to bypass these protections.

Business intent is optional. Same-repository PR metadata and closing issues can
provide context with read permissions. A supplied `task` path is optional.
The Action never runs the customer application or its tests.
