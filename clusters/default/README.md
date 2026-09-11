# `clusters/default/` — empty scaffold

**Not deployable.** Runtime copy-source for legacy `init --from default`
(`hosts` / `pub_keys`). Org baseline vars live under `default/default/`.

This directory is intentionally **minimal**. For new clusters prefer:

```bash
./cluster init prod/k8s --template k8s_full
```

| Path | Purpose |
|------|---------|
| `default/default/cluster.yaml` | Org baseline skeleton (customize) |
| `default/default/group_vars/` | Org baseline overlays (workspace-id fallback SoT) |
| `default/` (this dir) | Empty `hosts` / `pub_keys` scaffold for `init --from default` |
| `_template/k8s_full/` | Public full-k8s init template |

Edit `default/default/group_vars` when you need shared org defaults, or start from `_template/*`.
