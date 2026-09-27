# Public scaffold `_template/default` (exported from `dev/default`)

Env-policy overlay for `./cluster init … --template default`. **Not a stack**
and not a substitute for:

- `_template/` — minimal empty scaffold (`./cluster init lab --template`)
- `clusters/default/default/` — org baseline
- `./cluster init --from default` — copies `clusters/default/`

Regenerate:

```bash
python3 -m clusterctl.tools.export_template --from dev/default --template default
```

Init of ``<env>/<name>`` copies this tree to ``clusters/<env>/default/`` when
that env-policy directory does not exist yet. Do not use ``--flatten-cascade``
here — shared knobs stay on this layer, stack leaves stay thin.

# Dev environment policy

**Not deployable** — cascade layer 2 style fragment (shared compute / node-foundation knobs).

Add env-wide overrides here (local sibling repos, `cluster_id_aliases`, execution defaults).
Reference a full stack via another `--template` (for example `k8s_full`).
