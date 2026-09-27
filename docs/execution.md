# Execution runtime

Where ansible runs: on the controller (`local`) or in Docker (`docker`).

## Docker executor image

Default controller image for `--executor docker`:

| | |
|--|--|
| **Pull** | [`yokozu/krang:336`](https://hub.docker.com/r/yokozu/krang) |
| **Build** | [yokozu777/infrastructure-automation-toolkit](https://github.com/yokozu777/infrastructure-automation-toolkit) |

Templates ship `execution.image: yokozu/krang` and `execution.tag: latest`. Override per cluster or via `EXECUTION_DOCKER_IMAGE` / `EXECUTION_DOCKER_TAG`.

## cluster.yaml

```yaml
execution:
  mode: docker
  image: yokozu/krang
  tag: "336"
  repos_root: ../        # optional: sibling mount root
  extra_args: []         # optional docker run flags (not -d/--detach, not --user/-u)
```

Do **not** put `-d` / `--detach` (or combined short forms like `-itd`) in
`execution.extra_args`. The docker executor stages a per-run SSH key and
removes it when `docker run` returns; a detached container would keep running
after that cleanup and lose the mounted key.

Do **not** put `--user` / `-u` in `execution.extra_args`. clusterctl always
passes `--user $(id -u):$(id -g)` so bind-mount writes match the host runner.

Local only:

```yaml
execution:
  mode: local
```

When `mode: docker`, fields **`image` and `tag` are required** (no code defaults).

Docker bind-mounts:

- `$ATLAS_CLUSTER_ROOT` (controller checkout, includes `.config/`)
- SSH private key — **per-run host staging**, then mount (see below)
- Paths from `.config/config.yaml` / env that sit **outside** the checkout:
  `clusters.path` (`ATLAS_CLUSTERS_ROOT`) and `workspace.path` (`ATLAS_WORKSPACE_ROOT`).
  Sibling inventory+workspace under one parent collapse to a single parent `-v`.

The **right-hand** side of each `-v` (and env inside krang) is the path clusterctl
sees. The **left-hand** source is the Docker daemon host path: `docker inspect`
of the current container when clusterctl runs in atlas-ui worker, else
`ATLAS_CLUSTER_ROOT_HOST` / `ATLAS_CLUSTERS_ROOT_HOST` /
`ATLAS_WORKSPACE_ROOT_HOST`, else 1:1. That split is what lets Compose mount
host trees at `/atlas/clusterctl` (and friends) on Linux, macOS, and Windows.
- Local playbook repos (`source: local`) as needed

### SSH key staging (docker)

GitLab File variables (and some CI temp paths) are often mode `0644`/`0664`;
OpenSSH refuses them (`UNPROTECTED PRIVATE KEY FILE`). Before each
`docker run` / smoke, clusterctl:

1. Runs `preflight_docker` (docker CLI + SSH key present/readable →
   `ClusterctlError` on failure), then copies `SSH_KEY` into a unique host dir
   via `tempfile.mkdtemp(prefix="atlas-ssh-")` under
   `workspace/<cluster_id>/.atlas-ssh/` (directory mode `0700`, key file mode
   `0600`). Staging must live on a Docker-shareable bind-mount (the cluster
   workspace) — Docker Desktop / snap often **cannot** mount host `/tmp`, and
   we do **not** write identity under `$ATLAS_CLUSTER_ROOT/.cache/`. This is
   also **not** the legacy shared file
   `$ATLAS_CLUSTER_ROOT/.cache/docker-identity/id_rsa`.
2. Bind-mounts that copy read-only at container `/tmp/atlas-ssh/id_rsa`
   (`CONTAINER_SSH_KEY`; path **inside the container** is unchanged across
   releases — do not confuse with the host staging dir).
3. Removes the staging dir in `finally` (success, failed `docker run`, or build
   failure after prepare).

Parallel docker runs with different keys no longer share one file. Ansible/git
inside the container see only `/tmp/atlas-ssh/id_rsa` via `SSH_KEY` /
`ANSIBLE_PRIVATE_KEY_FILE` / `GIT_SSH_COMMAND` — never a host workspace
`.atlas-ssh/…` path and never the host `atlas-ssh-*` staging path as an env
value.

Older clusterctl wrote `$ATLAS_CLUSTER_ROOT/.cache/docker-identity/id_rsa`. That
path is **no longer created**. A leftover tree is safe to remove:

```bash
rm -rf "$ATLAS_CLUSTER_ROOT/.cache/docker-identity"
# or, if empty aside from that leftover:
# rm -rf "$ATLAS_CLUSTER_ROOT/.cache"
```

Keep `/.cache/` in `.gitignore` — CI may still leave a pip/other cache there;
clusterctl does **not** write SSH identity under controller `.cache/`.

The container runs as the **host uid:gid** (`docker run --user $(id -u):$(id -g)`).
`HOME` is set to `/tmp/clusterctl-home` (created in the container before the
inner command) so non-root tooling does not need `/root`. For non-root uids the
image must provide **`nss_wrapper`** (`/usr/lib/libnss_wrapper.so` — krang
**≥336**); clusterctl writes a fake passwd/group under `HOME` and sets
`LD_PRELOAD` so `git`/`ssh` get a username via NSS. Without that library the
container exits immediately with `docker: nss_wrapper required…`. clusterctl does **not** run post-run `chown` — new files under bind mounts already belong to
the runner. Legacy root-owned trees from older root-image runs may still need
a one-time host cleanup, for example:

```bash
sudo chown -R "$(id -u):$(id -g)" workspace/<cluster_id>/ INV/tfstate INV/.git
```

(`extra_args` must not include `--user` — see above.)

Inside the container, `ATLAS_CLUSTERS_ROOT` and `ATLAS_WORKSPACE_ROOT` are set so
resolution matches the host. Before the inner command, clusterctl runs
`mkdir -p /tmp/clusterctl/<workspace_id> /tmp/clusterctl-home /tmp/clusterctl-home/.ansible_async`
(Ansible controller temp, HOME, and `ANSIBLE_ASYNC_DIR` on container-local FS).
`ANSIBLE_ASYNC_DIR` is an absolute path so `async` / `async_status` do not
split between `$HOME/.ansible_async` and `/root/.ansible_async` when the
container is uid 0 (Windows Compose / root workers). Local mode needs no
mounts — paths are used as-is.

## Mode priority

1. `--executor local|docker`
2. `CLUSTER_EXECUTOR`
3. `execution.mode` in `cluster.yaml`
4. default: `local`

Legacy `execution.mode: krang` and `--executor krang` are **removed** — use `docker`.

## image:tag priority (docker)

1. `EXECUTION_DOCKER_IMAGE` / `EXECUTION_DOCKER_TAG`
2. `execution.image` / `execution.tag` in YAML

Jenkins: parameter `EXECUTION_DOCKER_TAG` empty by default → tag from `cluster.yaml`.

## Visual selection diagrams

```
Executor mode priority:

  --executor (CLI)  -->  if set, use it
         |
         v  (else)
  CLUSTER_EXECUTOR  -->  if set, use it
         |
         v  (else)
  execution.mode    -->  if set, use it
         |
         v  (else)
  default: local

image:tag priority (docker mode):

  EXECUTION_DOCKER_IMAGE / TAG  -->  if set, use ENV
         |
         v  (else)
  execution.image / tag         -->  if set, use YAML
         |
         v  (else)
  ERROR: docker requires image+tag
```

## CLI

```bash
./cluster --executor local run --phases init..redis
./cluster --executor docker run --phases init..redis
./cluster config show
./cluster validate --skip-docker-smoke    # skip docker pull / in-container smoke
```

## Docker mounts (concept)

```
  docker container
       |
       +-- atlas-clusterctl checkout
       +-- sibling playbook repos
       +-- SSH key → /tmp/atlas-ssh/id_rsa (host: workspace/<id>/.atlas-ssh/atlas-ssh-*/id_rsa)
       +-- workspace bind (state/logs)
```

Container receives:

- checkout of `atlas-clusterctl`
- sibling playbook repos (`repos_root` / materialized `workspace/.../repos`)
- SSH key for git / Ansible at `/tmp/atlas-ssh/id_rsa` (per-run host copy)
- workspace bind for state/logs

Exact flag set is assembled by the clusterctl executor — do not hand-roll `docker run` when `./cluster --executor docker …` suffices.

See [jenkins.md](jenkins.md), [validate.md](validate.md).
