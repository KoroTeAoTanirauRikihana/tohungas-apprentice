"""Copies the current Apprentice knowledge base out of its own dedicated
vault (Tohungas_Apprentice_Vault - separate from Koro's personal
Obsidian vault, 2026-08-27) into this standalone project's own knowledge/
folder, so the public app's backend never has a live path dependency into
Koro's own machine - it only ever reads a deliberately-synced, filtered
snapshot.

Real filtering, not a blind copy - Koro's own instruction, 2026-08-27:
"make it refresh by itself only verified information to keep the app
honest." Every research document in this project already tags each real
claim with an honest confidence level (see workers/apprentice_research.py's
own SYSTEM_PROMPT, which requires this): "High confidence", "Solid but
singular-source", "Living/oral tradition", "Varies by iwi/hapu" are all
real, cited claims - kept. "Gap - flagged rather than filled with
assumption" (an explicit admission nothing real was found) and "Lower
confidence / commercial or informal source" (the weakest sourcing tier)
are dropped before anything reaches the public app. This reuses the
project's own existing honesty discipline as the verification gate,
rather than inventing a separate review process - see _is_verified_
paragraph() below for the actual rule.

Called two ways: as a one-off CLI script (`python sync_knowledge.py`), and
imported by app.py's background refresh thread for the automatic periodic
sync Koro asked for.
"""
from __future__ import annotations

import re
from pathlib import Path

SOURCE = (
    Path.home()
    / "Documents"
    / "Tohungas_Apprentice_Vault"
    / "Knowledge"
)
DEST = Path(__file__).resolve().parent / "knowledge"

# Case-insensitive match against the exact confidence-tag phrasing already
# used consistently across every research document in this project (see
# "01 - Tohunga Types and Specialisations.md" and
# "02 - Tikanga and Kawa Across Iwi.md"'s own "How to read the confidence
# marks" sections for the source vocabulary this filter relies on).
_UNVERIFIED_MARKERS = (
    re.compile(r"gap\s*[-—]\s*flagged", re.IGNORECASE),
    re.compile(r"lower confidence", re.IGNORECASE),
)


def _is_verified_paragraph(paragraph: str) -> bool:
    """A paragraph is excluded from the public snapshot only if it carries
    one of the two tags that mean "not really established" - everything
    else (including headers, and paragraphs with no confidence tag at all,
    e.g. section intros) is kept."""
    return not any(marker.search(paragraph) for marker in _UNVERIFIED_MARKERS)


def _filter_verified(text: str) -> str:
    paragraphs = re.split(r"\n\s*\n", text)
    kept = [p for p in paragraphs if _is_verified_paragraph(p)]
    return "\n\n".join(kept)


def sync() -> dict:
    """Real return value used by both the CLI entry point and app.py's
    background refresh thread, so both report the same real counts.

    Recursive, and preserves the vault's real Foundations/Iwi-Specific
    folder structure (2026-08-27 reorganisation) rather than flattening
    everything - app.py's retrieval relies on that structure plus each
    file's real frontmatter, not just raw text."""
    if not SOURCE.is_dir():
        raise FileNotFoundError(f"Source knowledge folder not found: {SOURCE}")
    DEST.mkdir(parents=True, exist_ok=True)
    for old in DEST.glob("**/*.md"):
        old.unlink()

    synced_files = 0
    dropped_paragraphs = 0
    for path in sorted(SOURCE.glob("**/*.md")):
        original = path.read_text(encoding="utf-8")
        filtered = _filter_verified(original)
        dropped_paragraphs += len(re.split(r"\n\s*\n", original)) - len(
            re.split(r"\n\s*\n", filtered)
        )
        relative = path.relative_to(SOURCE)
        dest_path = DEST / relative
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_text(filtered, encoding="utf-8")
        synced_files += 1

    return {"synced_files": synced_files, "dropped_paragraphs": dropped_paragraphs}


def main() -> None:
    result = sync()
    print(
        f"Synced {result['synced_files']} knowledge file(s) from {SOURCE} to {DEST} "
        f"(dropped {result['dropped_paragraphs']} unverified paragraph(s): "
        "gap-flagged or lower-confidence content excluded from the public app)."
    )


if __name__ == "__main__":
    main()
