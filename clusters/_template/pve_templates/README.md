# Reference golden PVE templates — build-only leaf

Orchestration: **[`docs/stacks/compute-provision.md`](../../../docs/stacks/compute-provision.md)**

This scaffold builds shared cloud-init templates once. Stack leaves
(`k8s_full`, `postgresql`, …) **clone** them by key (`ubuntu-base` /
`oracle-base` / `debian-base`) and do **not** carry `image_url`.

```bash
./cluster init lab/pve-templates --template pve_templates --dns-suffix example.com
./cluster use lab/pve-templates
# fill atlas-compute-provision.secrets.yml; set provision_pve_host / target_node
./cluster validate --strict
./cluster run --phases templates
```

Phases: `templates` only (no Terraform guests).

| Key | Default VMID | Role |
|-----|--------------|------|
| `ubuntu-base` | 400100 | Ubuntu minimal cloud |
| `oracle-base` | 400101 | Oracle Linux KVM |
| `debian-base` | 400102 | Debian generic cloud |

Confirm VMIDs are free on the target PVE before first build. Stack default
phases start at `provision` — run this leaf (or an org equivalent) first.
