"""Pure-Python data classes for character sheets and registries.

The dataclasses here are deliberately *plain* — no pydantic, no
attrs — so they can be round-tripped through YAML, JSON, or
``model_dump``-style dicts without any adapter-specific quirks.
Pydantic v2's :func:`model_validate` will gladly consume a dict
produced by :meth:`CharacterSheet.to_dict` if a caller wants a
schema-validated wrapper later.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Iterable, Iterator

# ---- Reference-slot constants ------------------------------------------------

#: Canonical reference-image slots. The order matches the typical art-bible
#: reading order: "hero shot" (front) → angle variants → silhouette/style.
REFERENCE_FRONT: str = "front"
REFERENCE_THREE_QUARTER: str = "three_quarter"
REFERENCE_PROFILE: str = "profile"
REFERENCE_FULL_BODY: str = "full_body"
REFERENCE_STYLE: str = "style"

#: Tuple of the canonical reference slots, in canonical order.
REFERENCE_SLOTS: tuple[str, ...] = (
    REFERENCE_FRONT,
    REFERENCE_THREE_QUARTER,
    REFERENCE_PROFILE,
    REFERENCE_FULL_BODY,
    REFERENCE_STYLE,
)

#: Valid engine identifiers; these map 1-to-1 to a ComfyUI workflow under
#: ``backend/workflows/`` and to a scene type in
#: ``melosviz.conductor.registry``. Adding a new engine requires both a
#: workflow file *and* a registry entry.
ENGINE_IPADAPTER: str = "ipadapter"
ENGINE_PULID: str = "pulid"
SUPPORTED_ENGINES: frozenset[str] = frozenset({ENGINE_IPADAPTER, ENGINE_PULID})

# Convenience aliases for the workflow JSON filenames — kept here so the
# CLI / orchestrator / adapter all agree on the constant.
CHARACTER_IPADAPTER: str = "ipadapter_character"
CHARACTER_PULID: str = "pulid_character"


def _empty_references() -> dict[str, str]:
    """Return a fresh ``{slot: ""}`` dict with every canonical slot.

    Centralised so :meth:`CharacterSheet.to_dict` and
    :meth:`CharacterSheet.from_dict` cannot drift on slot ordering
    or missing keys.
    """
    return {slot: "" for slot in REFERENCE_SLOTS}


@dataclass
class CharacterSheet:
    """A single recurring character in a music-video storyboard.

    Fields fall into three groups:

    * **Identity** — ``name``, ``description``, ``style_prompt``,
      ``negative_prompt``; the human-facing bits an art director
      fills in.
    * **Reference images** — ``references[slot] = path`` where
      ``slot`` is one of :data:`REFERENCE_SLOTS`. Paths may be
      absolute or relative to the directory the sheet was loaded
      from.
    * **Engine hint** — ``engine`` is one of
      :data:`SUPPORTED_ENGINES`. It tells the renderer which
      ComfyUI workflow to use when this character is named in a
      scene. ``ipadapter`` (IP-Adapter-FaceID) is the default;
      ``pulid`` is a lighter alternative when face-only is enough.

    The dataclass is intentionally permissive — no pydantic, no
    strict validators — so it can be built incrementally during
    an interactive ``viz character add`` flow and only validated
    at the boundary (CLI parse, YAML load).
    """

    name: str = ""
    description: str = ""
    style_prompt: str = ""
    negative_prompt: str = ""
    engine: str = ENGINE_IPADAPTER
    references: dict[str, str] = field(default_factory=_empty_references)
    # Free-form metadata: tags, notes, voice actor, costume ID, etc.
    metadata: dict[str, Any] = field(default_factory=dict)

    # ---- validation helpers -------------------------------------------------

    def __post_init__(self) -> None:
        # Coerce engine to a known constant if possible. Unknown engines are
        # preserved verbatim — better to surface a workflow-missing error at
        # dispatch time than to silently re-route to IP-Adapter.
        if not isinstance(self.engine, str):
            self.engine = ENGINE_IPADAPTER
        # Normalise references dict so every canonical key exists. Unknown keys
        # are preserved (forward-compat) but won't be picked up by the
        # adapter's _SafeDict unless an entry is added there.
        if not isinstance(self.references, dict):
            self.references = _empty_references()
        for slot in REFERENCE_SLOTS:
            self.references.setdefault(slot, "")
        if not isinstance(self.metadata, dict):
            self.metadata = {}

    @property
    def is_complete(self) -> bool:
        """``True`` when the sheet has the minimum fields needed to render.

        "Minimum" = a name, at least one reference image, and a
        recognised engine. Used by the CLI ``add`` flow to warn the
        user before they save a half-filled sheet.
        """
        if not self.name:
            return False
        if self.engine not in SUPPORTED_ENGINES:
            return False
        return any(self.references.get(slot) for slot in REFERENCE_SLOTS)

    @property
    def engine_workflow(self) -> str:
        """Name of the ComfyUI workflow this character should route to.

        Returns the workflow filename stem (``ipadapter_character`` or
        ``pulid_character``) — the adapter looks them up via
        :data:`melosviz.render.comfyui_adapter.DEFAULT_WORKFLOWS`.
        """
        if self.engine == ENGINE_PULID:
            return CHARACTER_PULID
        # Default + explicit ipadapter both route here.
        return CHARACTER_IPADAPTER

    # ---- (de)serialisation --------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict suitable for ``json.dump`` / ``yaml.dump``.

        Reference paths are preserved as-is — the caller is responsible
        for making them absolute before persisting, or for resolving
        them relative to the sheet's source directory on load.
        """
        d = asdict(self)
        # asdict() already deep-copies via copy.deepcopy(), so it's safe
        # to return directly. Strip nothing — the keys are documented.
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CharacterSheet":
        """Build a :class:`CharacterSheet` from a dict (e.g. parsed YAML).

        Extra keys in ``data`` are silently dropped; missing keys use
        the dataclass default. Unknown reference slots are kept on
        a best-effort basis (merged into ``references`` after the
        canonical slots are normalised).
        """
        if not isinstance(data, dict):
            raise TypeError(
                f"CharacterSheet.from_dict expected a dict, got {type(data).__name__}"
            )
        # Pull only known top-level fields. ``pop`` rather than ``get``
        # so we surface typos in the YAML at construction time.
        kwargs: dict[str, Any] = {}
        for key in (
            "name",
            "description",
            "style_prompt",
            "negative_prompt",
            "engine",
            "references",
            "metadata",
        ):
            if key in data:
                kwargs[key] = data[key]
        sheet = cls(**kwargs)
        # Merge in any non-canonical reference slots (forward compat).
        if isinstance(data.get("references"), dict):
            for slot, path in data["references"].items():
                sheet.references[slot] = path
        # Merge in any top-level metadata-only fields (so e.g. ``tags: [...]``
        # at the root still lands in ``sheet.metadata``).
        if isinstance(data.get("metadata"), dict):
            for k, v in data["metadata"].items():
                sheet.metadata.setdefault(k, v)
        return sheet


@dataclass
class CharacterRegistry:
    """In-memory collection of :class:`CharacterSheet` keyed by name.

    The registry is the single object threaded through every adapter
    dispatch. It is intentionally tiny — add / get / remove / iterate
    — because anything more elaborate belongs in the orchestrator
    or in the CLI's persistence layer.
    """

    sheets: dict[str, CharacterSheet] = field(default_factory=dict)
    source_root: str = ""

    # ---- basic collection protocol -----------------------------------------

    def __iter__(self) -> Iterator[CharacterSheet]:
        return iter(self.sheets.values())

    def __len__(self) -> int:
        return len(self.sheets)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self.sheets

    def names(self) -> list[str]:
        """Return all character names in insertion order."""
        return list(self.sheets.keys())

    def add(self, sheet: CharacterSheet, *, overwrite: bool = False) -> None:
        """Insert ``sheet`` keyed by ``sheet.name``.

        Raises :class:`ValueError` on a duplicate name unless
        ``overwrite=True``. Empty names are rejected outright —
        the registry keys on name, so an unnamed sheet cannot be
        looked up.
        """
        if not sheet.name:
            raise ValueError("CharacterSheet.name is required to add to a registry")
        if not overwrite and sheet.name in self.sheets:
            raise ValueError(
                f"character {sheet.name!r} already in registry "
                f"(pass overwrite=True to replace)"
            )
        self.sheets[sheet.name] = sheet

    def remove(self, name: str) -> bool:
        """Remove a sheet by name. Returns ``True`` if it existed."""
        return self.sheets.pop(name, None) is not None

    def get(self, name: str) -> CharacterSheet | None:
        """Look up a sheet by name, returning ``None`` if missing."""
        return self.sheets.get(name)

    def require(self, name: str) -> CharacterSheet:
        """Look up a sheet by name, raising ``KeyError`` if missing.

        Use this at dispatch time so the orchestrator's error
        message is concrete: "character 'alice' not in registry"
        beats an opaque ``AttributeError`` from the adapter.
        """
        try:
            return self.sheets[name]
        except KeyError as exc:
            raise KeyError(
                f"character {name!r} not in registry "
                f"(known: {', '.join(self.names()) or '—'})"
            ) from exc

    # ---- bulk helpers -------------------------------------------------------

    def extend(self, sheets: Iterable[CharacterSheet], *, overwrite: bool = False) -> None:
        """Add many sheets at once. See :meth:`add` for overwrite semantics."""
        for s in sheets:
            self.add(s, overwrite=overwrite)

    def to_list(self) -> list[dict[str, Any]]:
        """Serialise every sheet via :meth:`CharacterSheet.to_dict`."""
        return [s.to_dict() for s in self.sheets.values()]

    @classmethod
    def from_iterable(
        cls,
        sheets: Iterable[CharacterSheet],
        *,
        source_root: str = "",
    ) -> "CharacterRegistry":
        """Build a registry from any iterable of sheets.

        Duplicate names keep the *first* occurrence. Pass
        ``overwrite=True`` via :meth:`extend` if you need last-wins.
        """
        reg = cls(source_root=source_root)
        reg.extend(sheets)
        return reg