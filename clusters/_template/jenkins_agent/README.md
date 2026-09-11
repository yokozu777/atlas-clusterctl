# `jenkins_agent` — Jenkins CI agents template

Self-contained scaffold for Jenkins build agents (no k8s / no infra stacks).

Orchestration: [docs/stacks/jenkins-agent.md](../../../docs/stacks/jenkins-agent.md).

Product pair (copy/align with sibling `atlas-jenkins-agent`):

- `group_vars/all/atlas-jenkins-agent.yml`
- `group_vars/all/atlas-jenkins-agent.secrets.yml` (Vault-friendly)

## Init new cluster

```bash
./cluster init prod/jenkins --template jenkins_agent
./cluster init prod/jenkins --template jenkins_agent --dns-suffix prod.example.com
```

Then edit `hosts`, fill `atlas-jenkins-agent.secrets.yml` (`jenkins_admin_password`), set
`jenkins_url` / CA paths in `atlas-jenkins-agent.yml`, and provision secrets in
`atlas-compute-provision.secrets.yml`.

Leaf DNS: `--dns-suffix` sets the shared suffix; `cluster_domain` keeps the
`jenkins.` template prefix unless you edit `atlas-*.yml`.

## Phases

`provision` → `init` → `jenkins-agent`

## Reference

After init: `./cluster use <your-id>` (local org labs under `clusters/ci/` are optional / gitignored)  
Sibling product docs: `atlas-jenkins-agent` README (standalone `./run.sh`).

Regenerate this scaffold from a lab (maintainer; scrub hostnames/secrets after):

```bash
python3 -m clusterctl.tools.export_template --from <lab-id> --template jenkins_agent
```
