# Org baseline (`default/default`)

**Not deployable** — cascade layer 1 for hierarchical clusters.

This fragment is intentionally **empty** (skeleton only). Edit `playbooks`, `phases`, and
related keys for your organization, or copy structure from:

- `clusters/_template/k8s_full/cluster.yaml` — public full-k8s template

Cascade: `default/default` → `<env>/default` → `<env>/<name>`

Fixture helper (synthetic org merge):

```bash
python3 -m clusterctl.tools.generate_org_cluster_fixture
```
