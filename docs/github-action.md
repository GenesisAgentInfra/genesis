# GitHub Action

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
      - uses: GenesisAgentInfra/genesis-cli/action@REVIEWED_FULL_COMMIT_SHA
        with:
          base: ${{ github.event.pull_request.base.sha }}
          service-url: ${{ vars.GENESIS_SERVICE_URL }}
          api-key: ${{ secrets.GENESIS_API_KEY }}
```

Set the service origin in repository Variables and the Genesis key in Secrets.
The Action writes the readable report to the Job Summary and uploads only
`summary.md`, `report.md`, and `report.json`. It does not post PR comments.
Missing keys, forks, `pull_request_target`, or unverified PR identity force
offline analysis; a usable partial report is not a failed transport step.
Do not change the trigger to `pull_request_target` to bypass these protections.

Business intent is optional. Same-repository PR metadata and closing issues can
provide context with read permissions. A supplied `task` path is optional.
The Action never runs the customer application or its tests.
