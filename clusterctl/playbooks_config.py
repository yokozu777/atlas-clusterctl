"""Cluster config v2: playbooks (repo catalog + entries) and phases (run order).

Schema design: docs/cluster-config-v2.md
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any, Mapping

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PyYAML required") from exc

from clusterctl.exceptions import ClusterctlError, PhaseAliasesRemovedError, StacksRemovedError

SCHEMA_VERSION = 2

SOURCES: frozenset[str] = frozenset({"git", "local"})
PATH_RELATIVE_TO_VALUES: frozenset[str] = frozenset({"sibling", "repo_root", "absolute"})
SYNC_VALUES: frozenset[str] = frozenset({"always", "if_missing", "never"})
ANSIBLE_STRATEGIES: frozenset[str] = frozenset({"linear", "mitogen_linear", "free", "host_pinned"})

_PHASE_REF_RE = re.compile(r"^([^/]+)/([^/]+)$")
_REPO_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
_ENTRY_NAME_RE = _REPO_NAME_RE
_PHASE_ALIAS_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


def _validate_phase_alias_name(alias: str) -> None:
    text = str(alias).strip()
    if not text:
        raise ClusterctlError("phase alias must be non-empty")
    if "/" in text:
        raise ClusterctlError(
            f"phase alias {text!r} must not contain '/' — use a short name, "
            f"full refs belong in the map value"
        )
    if not _PHASE_ALIAS_RE.fullmatch(text):
        raise ClusterctlError(
            f"invalid phase alias {text!r} — use letters, digits, '.', '_', '-'"
        )


def _parse_phases_list_item(item: object) -> tuple[str | None, str]:
    """Return ``(alias_or_none, phase_ref)`` for one ``phases:`` list entry."""
    if isinstance(item, str):
        ref = item.strip()
        if not ref:
            raise ClusterctlError("phases entries must be non-empty")
        parse_phase_ref(ref)
        return None, ref
    if isinstance(item, Mapping):
        if len(item) != 1:
            raise ClusterctlError(
                "phases map entries must have exactly one key "
                "(alias: repo/entry)"
            )
        alias_raw, ref_raw = next(iter(item.items()))
        alias = str(alias_raw).strip()
        ref = str(ref_raw).strip()
        _validate_phase_alias_name(alias)
        if not ref:
            raise ClusterctlError(f"phase alias {alias!r} value must be non-empty")
        parse_phase_ref(ref)
        return alias, ref
    raise ClusterctlError(
        "phases entries must be a repo/entry string or a single-key "
        "{alias: repo/entry} mapping"
    )

@dataclass(frozen=True)
class AnsibleSettings:
    strategy: str = "mitogen_linear"
    forks: int = 100

    def validate(self) -> None:
        if self.strategy not in ANSIBLE_STRATEGIES:
            raise ClusterctlError(
                f"ansible.strategy must be one of {sorted(ANSIBLE_STRATEGIES)}, "
                f"got {self.strategy!r}"
            )
        if self.forks < 1:
            raise ClusterctlError(f"ansible.forks must be >= 1, got {self.forks}")


@dataclass(frozen=True)
class PhaseWhen:
    """Declarative skip/filter rules for a playbook entry (ex-stacks)."""

    inventory_groups_any: tuple[str, ...] = ()
    inventory_groups_all: tuple[str, ...] = ()
    vars: dict[str, Any] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return (
            not self.inventory_groups_any
            and not self.inventory_groups_all
            and not self.vars
        )

    def validate(self) -> None:
        for group in (*self.inventory_groups_any, *self.inventory_groups_all):
            text = str(group).strip()
            if not text:
                raise ClusterctlError("when inventory group names must be non-empty")


@dataclass(frozen=True)
class InvocationSpec:
    tags: str
    limit: str | None = None
    root_ssh: bool = False
    extra_e: tuple[str, ...] = ()

    def validate(self) -> None:
        if not self.tags.strip():
            raise ClusterctlError("invocation.tags is required")


@dataclass(frozen=True)
class PlaybookEntrySpec:
    file: str
    git_ssh: bool = False
    ansible: AnsibleSettings = field(default_factory=AnsibleSettings)
    when: PhaseWhen = field(default_factory=PhaseWhen)
    invocations: tuple[InvocationSpec, ...] = ()

    def validate(self, *, repo_name: str, entry_name: str) -> None:
        if not self.file.strip():
            raise ClusterctlError(
                f"playbooks.{repo_name}.entries.{entry_name}.file is required"
            )
        self.ansible.validate()
        self.when.validate()
        if not self.invocations:
            raise ClusterctlError(
                f"playbooks.{repo_name}.entries.{entry_name} "
                "requires at least one invocation"
            )
        for index, invocation in enumerate(self.invocations, start=1):
            try:
                invocation.validate()
            except ClusterctlError as exc:
                raise ClusterctlError(
                    f"playbooks.{repo_name}.entries.{entry_name} "
                    f"invocation #{index}: {exc}"
                ) from exc


@dataclass(frozen=True)
class PlaybookRepoSpec:
    name: str
    source: str = "git"
    url: str | None = None
    ref: str | None = None
    path: str | None = None
    path_relative_to: str = "sibling"
    layout: str | None = None
    shallow: bool = True
    sync: str = "always"
    readiness_markers: tuple[str, ...] = ()
    entries: dict[str, PlaybookEntrySpec] = field(default_factory=dict)

    def default_sync_for_source(self) -> str:
        return "never" if self.source == "local" else "always"

    @property
    def effective_sync(self) -> str:
        return self.sync if self.sync in SYNC_VALUES else self.default_sync_for_source()

    def validate(self) -> None:
        _validate_repo_name(self.name)
        source = self.source.strip().lower()
        if source not in SOURCES:
            raise ClusterctlError(
                f"playbooks.{self.name}.source must be git or local, got {self.source!r}"
            )
        if source == "git" and not (self.url and str(self.url).strip()):
            raise ClusterctlError(f"playbooks.{self.name}: git source requires url")
        if source == "local" and not (self.path and str(self.path).strip()):
            raise ClusterctlError(f"playbooks.{self.name}: local source requires path")
        if self.path_relative_to not in PATH_RELATIVE_TO_VALUES:
            raise ClusterctlError(
                f"playbooks.{self.name}.path_relative_to must be one of "
                f"{sorted(PATH_RELATIVE_TO_VALUES)}"
            )
        if self.effective_sync not in SYNC_VALUES:
            raise ClusterctlError(
                f"playbooks.{self.name}.sync must be one of {sorted(SYNC_VALUES)}"
            )
        for marker in self.readiness_markers:
            if not marker.strip():
                raise ClusterctlError(
                    f"playbooks.{self.name}.readiness_markers entries must be non-empty"
                )
            if "/" in marker or "\\" in marker or marker in (".", ".."):
                raise ClusterctlError(
                    f"playbooks.{self.name}.readiness_markers must be single dir names, "
                    f"got {marker!r}"
                )
        for entry_name, entry in self.entries.items():
            _validate_entry_name(entry_name)
            entry.validate(repo_name=self.name, entry_name=entry_name)


@dataclass(frozen=True)
class PlaybooksConfig:
    """Catalog of playbook repos (sync + entries). Run order lives in cluster ``phases``."""

    repos: dict[str, PlaybookRepoSpec]

    def validate(self) -> None:
        for name, repo in self.repos.items():
            repo.validate()

    def resolve_entry(self, phase_ref: str) -> tuple[PlaybookRepoSpec, PlaybookEntrySpec]:
        repo_name, entry_name = parse_phase_ref(phase_ref)
        repo = self.repos.get(repo_name)
        if repo is None:
            raise ClusterctlError(f"unknown playbook repo {repo_name!r}")
        entry = repo.entries.get(entry_name)
        if entry is None:
            raise ClusterctlError(f"unknown playbook entry {phase_ref!r}")
        return repo, entry


@dataclass(frozen=True)
class PhasesConfig:
    phases: tuple[str, ...] = ()
    phase_aliases: dict[str, str] = field(default_factory=dict)

    def validate(self, playbooks: PlaybooksConfig | None) -> None:
        if not self.phases:
            raise ClusterctlError("phases must be a non-empty ordered list")
        seen_refs: set[str] = set()
        for phase_ref in self.phases:
            parse_phase_ref(phase_ref)
            if phase_ref in seen_refs:
                raise ClusterctlError(f"duplicate phase ref {phase_ref!r}")
            seen_refs.add(phase_ref)
            if playbooks is not None:
                playbooks.resolve_entry(phase_ref)
        for alias, target in self.phase_aliases.items():
            _validate_phase_alias_name(alias)
            parse_phase_ref(target)
            if target not in seen_refs:
                raise ClusterctlError(
                    f"phase alias {alias!r} target {target!r} is not in phases:"
                )

    def repos_for_phases(self, playbooks: PlaybooksConfig) -> tuple[str, ...]:
        names: list[str] = []
        seen: set[str] = set()
        for phase_ref in self.phases:
            repo_name, _ = parse_phase_ref(phase_ref)
            if repo_name not in seen:
                names.append(repo_name)
                seen.add(repo_name)
        return tuple(names)

    def invocation_count(self, playbooks: PlaybooksConfig) -> int:
        total = 0
        for phase_ref in self.phases:
            _, entry = playbooks.resolve_entry(phase_ref)
            total += len(entry.invocations)
        return total


@dataclass(frozen=True)
class ClusterConfigV2:
    """Merged cluster.yaml fragment (schema v2)."""

    schema_version: int = SCHEMA_VERSION
    cluster_id: str | None = None
    display_name: str | None = None
    inventory: str | None = None
    playbooks_enabled: bool | None = None
    playbooks: PlaybooksConfig | None = None
    phases: PhasesConfig | None = None
    execution: dict[str, Any] = field(default_factory=dict)
    workspace_id: str | None = None
    deployable: bool | None = None
    cluster_id_aliases: dict[str, str] = field(default_factory=dict)

    def effective_playbooks_enabled(self) -> bool:
        if self.playbooks_enabled is not None:
            return self.playbooks_enabled
        return bool(self.playbooks and self.playbooks.repos)

    def validate(self, *, require_playbooks: bool | None = None) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ClusterctlError(
                f"unsupported schema_version {self.schema_version} "
                f"(expected {SCHEMA_VERSION})"
            )
        needs_playbooks = (
            self.effective_playbooks_enabled()
            if require_playbooks is None
            else require_playbooks
        )
        if needs_playbooks:
            if self.playbooks is None:
                raise ClusterctlError(
                    "playbooks runner is enabled but playbooks: section is missing "
                    "(add playbooks: or set playbooks_enabled: false — "
                    "see docs/cluster-config-v2.md / ADR 006)"
                )
            self.playbooks.validate()
            if self.phases is not None:
                self.phases.validate(self.playbooks)


def playbooks_feature_enabled(raw: Mapping[str, Any] | None) -> bool:
    """Whether playbook sync/resolver is active for a single YAML mapping.

    Explicit ``playbooks_enabled`` wins. When omitted, **infer** enabled from a
    non-empty ``playbooks`` mapping (ADR 006). Prefer
    ``ClusterConfigV2.effective_playbooks_enabled`` /
    ``resolve_playbooks_enabled`` for cascade-aware loads.
    """
    if not raw:
        return False
    explicit = parse_playbooks_enabled_explicit(raw)
    if explicit is not None:
        return explicit
    playbooks = raw.get("playbooks")
    return isinstance(playbooks, Mapping) and bool(playbooks)


def parse_playbooks_enabled_explicit(raw: Mapping[str, Any] | None) -> bool | None:
    """Explicit playbooks flag from a YAML fragment (None = inherit in cascade)."""
    if not raw:
        return None
    if "role_repos_enabled" in raw:
        raise ClusterctlError(
            "role_repos_enabled removed in schema v2 — use playbooks: "
            "(optional playbooks_enabled: false to disable; see docs/cluster-config-v2.md)"
        )
    if "role_repos" in raw and raw.get("role_repos"):
        raise ClusterctlError(
            "cluster.yaml role_repos removed — use playbooks overrides in cascade "
            "(see docs/cluster-config-v2.md)"
        )
    if "playbooks_enabled" in raw:
        return bool(raw.get("playbooks_enabled"))
    return None


def parse_playbooks_enabled_from_fragment(raw: Mapping[str, Any]) -> bool | None:
    """Parse playbooks_enabled from one cluster.yaml fragment (cascade-aware)."""
    return parse_playbooks_enabled_explicit(raw)


def resolve_playbooks_enabled(
    cluster_data: Mapping[str, Any] | None,
    *,
    config_v2: ClusterConfigV2 | None = None,
) -> bool:
    """Effective playbooks sync flag from leaf YAML + merged v2 config."""
    leaf_explicit = parse_playbooks_enabled_explicit(cluster_data)
    if leaf_explicit is not None:
        return leaf_explicit
    if config_v2 is not None:
        return config_v2.effective_playbooks_enabled()
    return playbooks_feature_enabled(cluster_data)


def parse_phase_ref(value: object) -> tuple[str, str]:
    text = str(value).strip()
    match = _PHASE_REF_RE.fullmatch(text)
    if not match:
        raise ClusterctlError(
            f"invalid phase ref {value!r} — expected format repo/entry "
            f"(e.g. my-stack/install)"
        )
    repo_name, entry_name = match.group(1), match.group(2)
    _validate_repo_name(repo_name)
    _validate_entry_name(entry_name)
    return repo_name, entry_name


def format_phase_ref(repo_name: str, entry_name: str) -> str:
    _validate_repo_name(repo_name)
    _validate_entry_name(entry_name)
    return f"{repo_name}/{entry_name}"


def resolve_phase_alias(
    name: str,
    aliases: Mapping[str, str],
) -> str:
    candidate = str(name).strip()
    if "/" in candidate:
        parse_phase_ref(candidate)
        return candidate
    target = aliases.get(candidate)
    if target is None:
        raise ClusterctlError(f"unknown phase alias {candidate!r}")
    return target


def phase_ref_to_alias_map(aliases: Mapping[str, str]) -> dict[str, str]:
    """Map phase_ref → first alias key (declaration order preserved)."""
    inverse: dict[str, str] = {}
    for alias, target in aliases.items():
        if target not in inverse:
            inverse[target] = alias
    return inverse


def stage_name_for_phase_ref(phase_ref: str, aliases: Mapping[str, str]) -> str:
    """CLI stage name: first matching alias, else playbook entry id."""
    inverse = phase_ref_to_alias_map(aliases)
    if phase_ref in inverse:
        return inverse[phase_ref]
    _, entry_id = parse_phase_ref(phase_ref)
    return entry_id


def _validate_repo_name(name: str) -> None:
    text = str(name).strip()
    if not text or not _REPO_NAME_RE.fullmatch(text):
        raise ClusterctlError(f"invalid playbook repo name {name!r}")


def _validate_entry_name(name: str) -> None:
    text = str(name).strip()
    if not text or not _ENTRY_NAME_RE.fullmatch(text):
        raise ClusterctlError(f"invalid playbook entry name {name!r}")


def _parse_ansible_settings(raw: object | None) -> AnsibleSettings:
    if raw is None:
        return AnsibleSettings()
    if not isinstance(raw, dict):
        raise ClusterctlError("ansible must be a mapping")
    strategy = str(raw.get("strategy", "mitogen_linear")).strip() or "mitogen_linear"
    forks_raw = raw.get("forks", 100)
    try:
        forks = int(forks_raw)
    except (TypeError, ValueError) as exc:
        raise ClusterctlError("ansible.forks must be an integer") from exc
    return AnsibleSettings(strategy=strategy, forks=forks)


def _parse_phase_when(raw: object | None) -> PhaseWhen:
    if raw is None:
        return PhaseWhen()
    if not isinstance(raw, dict):
        raise ClusterctlError("when must be a mapping")

    def _groups(key: str) -> tuple[str, ...]:
        value = raw.get(key)
        if value is None:
            return ()
        if isinstance(value, str):
            items = [item.strip() for item in value.split(",") if item.strip()]
        elif isinstance(value, list):
            items = [str(item).strip() for item in value if str(item).strip()]
        else:
            raise ClusterctlError(f"when.{key} must be a list or comma-separated string")
        return tuple(items)

    vars_raw = raw.get("vars") or {}
    if not isinstance(vars_raw, dict):
        raise ClusterctlError("when.vars must be a mapping")
    return PhaseWhen(
        inventory_groups_any=_groups("inventory_groups_any"),
        inventory_groups_all=_groups("inventory_groups_all"),
        vars=dict(vars_raw),
    )


def _parse_invocation(raw: object, *, context: str) -> InvocationSpec:
    if not isinstance(raw, dict):
        raise ClusterctlError(f"{context} must be a mapping")
    tags = str(raw.get("tags", "")).strip()
    limit = raw.get("limit")
    extra_raw = raw.get("extra_e") or raw.get("extra_vars") or []
    if isinstance(extra_raw, str):
        extra_items = [extra_raw]
    elif isinstance(extra_raw, list):
        extra_items = [str(item) for item in extra_raw]
    else:
        raise ClusterctlError(f"{context} extra_e must be a list or string")
    return InvocationSpec(
        tags=tags,
        limit=str(limit).strip() if limit else None,
        root_ssh=bool(raw.get("root_ssh", False)),
        extra_e=tuple(extra_items),
    )


def _parse_readiness_markers(raw: object | None, *, repo_name: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ClusterctlError(f"playbooks.{repo_name}.readiness_markers must be a list")
    markers: list[str] = []
    for index, item in enumerate(raw, start=1):
        text = str(item).strip()
        if not text:
            raise ClusterctlError(
                f"playbooks.{repo_name}.readiness_markers[{index}] must be non-empty"
            )
        if "/" in text or "\\" in text or text in (".", ".."):
            raise ClusterctlError(
                f"playbooks.{repo_name}.readiness_markers[{index}] must be a single dir name, "
                f"got {text!r}"
            )
        markers.append(text)
    return tuple(markers)


def _parse_playbook_entry(
    entry_name: str,
    raw: object,
    *,
    repo_name: str,
) -> PlaybookEntrySpec:
    if not isinstance(raw, dict):
        raise ClusterctlError(
            f"playbooks.{repo_name}.entries.{entry_name} must be a mapping"
        )
    invocations_raw = raw.get("invocations")
    if not isinstance(invocations_raw, list) or not invocations_raw:
        raise ClusterctlError(
            f"playbooks.{repo_name}.entries.{entry_name} "
            "requires non-empty invocations"
        )
    invocations = tuple(
        _parse_invocation(
            item,
            context=f"playbooks.{repo_name}.entries.{entry_name} invocation #{index}",
        )
        for index, item in enumerate(invocations_raw, start=1)
    )
    return PlaybookEntrySpec(
        file=str(raw.get("file", "")).strip(),
        git_ssh=bool(raw.get("git_ssh", False)),
        ansible=_parse_ansible_settings(raw.get("ansible")),
        when=_parse_phase_when(raw.get("when")),
        invocations=invocations,
    )


def _parse_playbook_repo(name: str, raw: object) -> PlaybookRepoSpec:
    _validate_repo_name(name)
    if not isinstance(raw, dict):
        raise ClusterctlError(f"playbooks.{name} must be a mapping")
    entries_raw = raw.get("entries") or {}
    if not isinstance(entries_raw, dict):
        raise ClusterctlError(f"playbooks.{name}.entries must be a mapping")
    entries = {
        str(entry_name).strip(): _parse_playbook_entry(
            str(entry_name).strip(),
            entry_raw,
            repo_name=name,
        )
        for entry_name, entry_raw in entries_raw.items()
    }
    source = str(raw.get("source", "git")).strip().lower() or "git"
    layout_raw = raw.get("layout")
    if layout_raw is None:
        layout_text: str | None = None
    else:
        layout_text = str(layout_raw)
    return PlaybookRepoSpec(
        name=name,
        source=source,
        url=str(raw.get("url")).strip() if raw.get("url") else None,
        ref=str(raw.get("ref")).strip() if raw.get("ref") else None,
        path=str(raw.get("path")).strip() if raw.get("path") else None,
        path_relative_to=str(raw.get("path_relative_to", "sibling")).strip() or "sibling",
        layout=layout_text,
        shallow=bool(raw.get("shallow", True)),
        sync=str(raw.get("sync", "")).strip() or "",
        readiness_markers=_parse_readiness_markers(raw.get("readiness_markers"), repo_name=name),
        entries=entries,
    )


def parse_playbooks_config(raw: object | None) -> PlaybooksConfig | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ClusterctlError("playbooks must be a mapping at the top level")

    repos: dict[str, PlaybookRepoSpec] = {}
    for repo_name, repo_raw in raw.items():
        repos[str(repo_name).strip()] = _parse_playbook_repo(str(repo_name).strip(), repo_raw)

    if not repos:
        return None
    return PlaybooksConfig(repos=repos)


def parse_phases_config(
    phases_raw: object | None,
    aliases_raw: object | None = None,
) -> PhasesConfig | None:
    """Parse ``phases:`` list (ADR 007 inline aliases).

    ``aliases_raw`` is rejected when present (legacy top-level ``phase_aliases:``).
    Prefer calling via ``parse_cluster_config_v2_fragment``, which raises
    ``PhaseAliasesRemovedError`` for the YAML key.
    """
    if aliases_raw is not None:
        raise PhaseAliasesRemovedError("phases parse")
    if phases_raw is None:
        return None
    if not isinstance(phases_raw, list):
        raise ClusterctlError("phases must be a list")

    phases: list[str] = []
    aliases_map: dict[str, str] = {}
    seen_aliases: set[str] = set()
    seen_refs: set[str] = set()
    for item in phases_raw:
        alias, ref = _parse_phases_list_item(item)
        if ref in seen_refs:
            raise ClusterctlError(f"duplicate phase ref {ref!r}")
        seen_refs.add(ref)
        phases.append(ref)
        if alias is None:
            continue
        if alias in seen_aliases:
            raise ClusterctlError(f"duplicate phase alias {alias!r}")
        seen_aliases.add(alias)
        aliases_map[alias] = ref
    return PhasesConfig(phases=tuple(phases), phase_aliases=aliases_map)


def _repo_to_raw(repo: PlaybookRepoSpec) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "source": repo.source,
        "layout": repo.layout,
        "shallow": repo.shallow,
        "sync": repo.effective_sync,
    }
    if repo.url:
        raw["url"] = repo.url
    if repo.ref:
        raw["ref"] = repo.ref
    if repo.path:
        raw["path"] = repo.path
    if repo.path_relative_to != "sibling":
        raw["path_relative_to"] = repo.path_relative_to
    if repo.readiness_markers:
        raw["readiness_markers"] = list(repo.readiness_markers)
    if repo.entries:
        raw["entries"] = {name: _entry_to_raw(entry) for name, entry in repo.entries.items()}
    return raw


def _entry_to_raw(entry: PlaybookEntrySpec) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "file": entry.file,
        "invocations": [_invocation_to_raw(inv) for inv in entry.invocations],
    }
    if entry.git_ssh:
        raw["git_ssh"] = True
    if entry.ansible != AnsibleSettings():
        raw["ansible"] = {
            "strategy": entry.ansible.strategy,
            "forks": entry.ansible.forks,
        }
    if not entry.when.is_empty:
        raw["when"] = _when_to_raw(entry.when)
    return raw


def _invocation_to_raw(invocation: InvocationSpec) -> dict[str, Any]:
    raw: dict[str, Any] = {"tags": invocation.tags}
    if invocation.limit:
        raw["limit"] = invocation.limit
    if invocation.root_ssh:
        raw["root_ssh"] = True
    if invocation.extra_e:
        raw["extra_e"] = list(invocation.extra_e)
    return raw


def _when_to_raw(when: PhaseWhen) -> dict[str, Any]:
    raw: dict[str, Any] = {}
    if when.inventory_groups_any:
        raw["inventory_groups_any"] = list(when.inventory_groups_any)
    if when.inventory_groups_all:
        raw["inventory_groups_all"] = list(when.inventory_groups_all)
    if when.vars:
        raw["vars"] = dict(when.vars)
    return raw


def playbooks_config_to_raw(config: PlaybooksConfig) -> dict[str, Any]:
    return {name: _repo_to_raw(repo) for name, repo in sorted(config.repos.items())}


def phases_config_to_raw(config: PhasesConfig) -> dict[str, Any]:
    """Dump phases with inline aliases (ADR 007) — no top-level ``phase_aliases:``.

    Rejects inconsistent ``PhasesConfig`` values (duplicate refs, drifted aliases)
    so dump cannot silently invent a non-round-trippable YAML shape.
    """
    seen_refs: set[str] = set()
    for ref in config.phases:
        if ref in seen_refs:
            raise ClusterctlError(f"duplicate phase ref {ref!r}")
        seen_refs.add(ref)

    ref_to_alias: dict[str, str] = {}
    for alias, target in config.phase_aliases.items():
        if target not in seen_refs:
            raise ClusterctlError(
                f"phase alias {alias!r} target {target!r} is not in phases:"
            )
        prior = ref_to_alias.get(target)
        if prior is not None:
            raise ClusterctlError(
                f"duplicate phase aliases {prior!r} and {alias!r} "
                f"for phase ref {target!r}"
            )
        ref_to_alias[target] = alias

    items: list[Any] = []
    for ref in config.phases:
        alias = ref_to_alias.get(ref)
        if alias is not None:
            items.append({alias: ref})
        else:
            items.append(ref)
    return {"phases": items}


def _finalize_playbook_repo_spec(spec: PlaybookRepoSpec) -> PlaybookRepoSpec:
    if spec.layout is not None:
        return spec
    return replace(spec, layout="roles/")


def _merge_repo_specs(
    base: PlaybookRepoSpec | None,
    override: PlaybookRepoSpec,
) -> PlaybookRepoSpec:
    if base is None:
        return _finalize_playbook_repo_spec(override)
    merged_entries = dict(base.entries)
    merged_entries.update(override.entries)
    merged = replace(
        base,
        source=override.source or base.source,
        url=override.url if override.url is not None else base.url,
        ref=override.ref if override.ref is not None else base.ref,
        path=override.path if override.path is not None else base.path,
        path_relative_to=override.path_relative_to or base.path_relative_to,
        layout=override.layout if override.layout is not None else base.layout,
        shallow=override.shallow,
        sync=override.sync or base.sync,
        readiness_markers=override.readiness_markers or base.readiness_markers,
        entries=merged_entries,
    )
    return _finalize_playbook_repo_spec(merged)


def merge_playbooks_configs(
    base: PlaybooksConfig | None,
    override: PlaybooksConfig | None,
) -> PlaybooksConfig | None:
    if base is None:
        return override
    if override is None:
        return base

    merged_repos = dict(base.repos)
    for name, repo in override.repos.items():
        merged_repos[name] = _merge_repo_specs(merged_repos.get(name), repo)

    return PlaybooksConfig(repos=merged_repos)


def merge_phases_configs(
    base: PhasesConfig | None,
    override: PhasesConfig | None,
) -> PhasesConfig | None:
    if base is None:
        return override
    if override is None:
        return base
    # List replace (ADR 007): an explicit ``phases:`` (including ``[]``) wins;
    # omit (``None``) inherits. Aliases come from the winning list only.
    return PhasesConfig(
        phases=override.phases,
        phase_aliases=dict(override.phase_aliases),
    )


def _load_yaml_mapping(path: str | Any) -> dict[str, Any]:
    if isinstance(path, dict):
        return dict(path)
    raise ClusterctlError("expected mapping")


def parse_cluster_id_aliases(raw: object | None) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ClusterctlError("cluster_id_aliases must be a mapping")
    aliases: dict[str, str] = {}
    for alias, target in raw.items():
        alias_text = str(alias).strip()
        target_text = str(target).strip()
        if not alias_text or not target_text:
            raise ClusterctlError("cluster_id_aliases entries must be non-empty strings")
        aliases[alias_text] = target_text
    return aliases


def parse_cluster_config_v2_fragment(raw: object | None) -> ClusterConfigV2:
    data = _load_yaml_mapping(raw or {})
    from clusterctl.cluster_config import (
        reject_removed_phase_aliases_key,
        reject_removed_stacks_key,
    )

    reject_removed_stacks_key(data, source="cluster.yaml fragment")
    reject_removed_phase_aliases_key(data, source="cluster.yaml fragment")
    schema_version = int(data.get("schema_version", SCHEMA_VERSION))
    playbooks = parse_playbooks_config(data.get("playbooks"))
    phases = parse_phases_config(data.get("phases"))

    cluster_id = data.get("id")
    display_name = data.get("display_name")
    inventory = data.get("inventory")
    workspace_id = data.get("workspace_id")
    deployable = data.get("deployable")
    execution_raw = data.get("execution") or {}
    if not isinstance(execution_raw, dict):
        raise ClusterctlError("execution must be a mapping")

    return ClusterConfigV2(
        schema_version=schema_version,
        cluster_id=str(cluster_id).strip() if cluster_id is not None else None,
        display_name=str(display_name).strip() if display_name is not None else None,
        inventory=str(inventory).strip() if inventory is not None else None,
        playbooks_enabled=parse_playbooks_enabled_from_fragment(data),
        playbooks=playbooks,
        phases=phases,
        execution=dict(execution_raw),
        workspace_id=str(workspace_id).strip() if workspace_id is not None else None,
        deployable=bool(deployable) if deployable is not None else None,
        cluster_id_aliases=parse_cluster_id_aliases(data.get("cluster_id_aliases")),
    )


def merge_cluster_config_v2(
    base: ClusterConfigV2 | None,
    override: ClusterConfigV2,
) -> ClusterConfigV2:
    if base is None:
        return override

    playbooks = merge_playbooks_configs(base.playbooks, override.playbooks)
    phases = merge_phases_configs(base.phases, override.phases)
    execution = dict(base.execution)
    execution.update(override.execution)
    cluster_id_aliases = dict(base.cluster_id_aliases)
    cluster_id_aliases.update(override.cluster_id_aliases)
    playbooks_enabled = (
        override.playbooks_enabled
        if override.playbooks_enabled is not None
        else base.playbooks_enabled
    )

    return ClusterConfigV2(
        schema_version=override.schema_version or base.schema_version,
        cluster_id=override.cluster_id or base.cluster_id,
        display_name=override.display_name or base.display_name,
        inventory=override.inventory or base.inventory,
        playbooks_enabled=playbooks_enabled,
        playbooks=playbooks,
        phases=phases,
        execution=execution,
        workspace_id=override.workspace_id or base.workspace_id,
        deployable=override.deployable if override.deployable is not None else base.deployable,
        cluster_id_aliases=cluster_id_aliases,
    )


def load_cluster_config_v2_yaml(path: Any) -> ClusterConfigV2:
    from pathlib import Path

    file_path = Path(path)
    with file_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ClusterctlError(f"invalid cluster config (expected mapping): {file_path}")
    try:
        return parse_cluster_config_v2_fragment(data)
    except StacksRemovedError as exc:
        raise exc.with_source(str(file_path)) from exc
    except PhaseAliasesRemovedError as exc:
        raise exc.with_source(str(file_path)) from exc
