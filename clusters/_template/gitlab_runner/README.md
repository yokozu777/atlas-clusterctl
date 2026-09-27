# `gitlab_runner` — GitLab CI runners template

Self-contained scaffold for GitLab runners (no k8s / no infra stacks).

Orchestration: [docs/stacks/gitlab-runner.md](../../../docs/stacks/gitlab-runner.md).

Product pair (copy/align with sibling `atlas-gitlab-runner`):

- `group_vars/all/atlas-gitlab-runner.yml`
- `group_vars/all/atlas-gitlab-runner.secrets.yml` (Vault-friendly)

## Init new cluster

```bash
./cluster init prod/gitlab --template gitlab_runner
./cluster init prod/gitlab --template gitlab_runner --dns-suffix prod.example.com
```

Then edit `hosts`, fill `atlas-gitlab-runner.secrets.yml` (`gitlab_runner_authentication_token`),
set `gitlab_url` / executor / CA paths in `atlas-gitlab-runner.yml`. Compute-provision
secrets live on ``<env>/default``.

Leaf DNS: `--dns-suffix` sets the shared suffix; `cluster_domain` keeps the
`gitlab-runner.` template prefix unless you edit `atlas-*.yml`.

## Phases

`provision` → `init` → `gitlab-runner`

## Reference

After init: `./cluster use <your-id>` (local org labs under `clusters/ci/` are optional / private inventory)  
Sibling product docs: `atlas-gitlab-runner` README (standalone `./run.sh`).

Regenerate this scaffold from a lab (maintainer; scrub hostnames/secrets after):

```bash
python3 -m clusterctl.tools.export_template --from <lab-id> --template gitlab_runner
```
