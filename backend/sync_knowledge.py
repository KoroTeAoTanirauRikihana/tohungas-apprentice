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
import os as _os
import shutil as _shutil
import threading as _threading
import time as _time
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

# --- Contributed taonga must NEVER reach the public app. --------------------
#
# Added 2026-09-06 alongside Koro_Global_Hub/core/taonga_release.py. Knowledge
# GIVEN by a named holder on their own conditions lives in the vault's
# "Taonga Tuku Iho" folder, which is a sibling of Knowledge/ and therefore
# already outside SOURCE - the same way "Media Watch" has always been.
#
# This is the SECOND layer, not the first. The first is that the folder sits
# outside SOURCE at all. This exists because sync() copies everything under
# SOURCE recursively, so a single mistaken file move - dragging one contributed
# file into Knowledge/ - would publish a kaumatua's words to the open web with
# no other check in the way. That must not be possible by accident.
#
# Fails closed and loudly: a matching file is skipped entirely (not filtered
# paragraph-by-paragraph like unverified research), and sync() reports the
# count so the mistake is visible rather than silent.
_RESTRICTED_DIR_NAMES = {"taonga tuku iho", "taonga_tuku_iho"}
_RESTRICTED_MARKERS = (
    re.compile(r"^\s*contributed_by\s*:", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*release\s*:\s*(whanau|hapu|iwi|maori|closed)\b", re.IGNORECASE | re.MULTILINE),
)

# The phrase "taonga tuku iho" is checked in the FRONTMATTER only, never in
# body prose. A file that DECLARES itself contributed taonga is blocked; a
# sourced reference file that merely MENTIONS the concept is not.
#
# Fixed 2026-09-09: the old bare-text marker `re.compile(r"TAONGA TUKU IHO")`
# matched any prose mention, and was silently blocking FIVE legitimate,
# fully-sourced reference files from ever reaching the public app - the
# Tainui-Waikato iwi file (which names Waikato-Tainui's own archive team,
# "Ngaa Taonga Tuku Iho"), Te Ture Whenua Maori Act, the Maori Land Court,
# Wahi Tapu heritage protection, and Maori dairy. Contributed taonga is
# always caught by the two frontmatter markers above and by the
# restricted-directory check, which is where the real protection lives;
# verified 2026-09-09 that NO file inside Knowledge/ carries contributed_by
# or a non-open release, so nothing that should be blocked slips through.
_TAONGA_SELF_DECLARATION = re.compile(r"taonga tuku iho", re.IGNORECASE)


def _frontmatter(text: str) -> str:
    """Return the YAML frontmatter block (between the leading --- fences), or
    an empty string if the file has none. Used to distinguish a file that
    declares itself taonga from one that only discusses the concept."""
    match = re.match(r"^\s*---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    return match.group(1) if match else ""


def _is_restricted(path: Path, relative: Path, text: str) -> bool:
    """True if this file is contributed taonga and must not be published.

    Checked three ways, any one of which is enough: it sits under a restricted
    folder name anywhere in its path, its frontmatter carries a giver or a
    non-open release level, or its frontmatter declares it taonga tuku iho.
    A prose mention of the concept in an otherwise-sourced reference file does
    NOT block it (see the note above _TAONGA_SELF_DECLARATION).
    """
    parts = {part.lower() for part in relative.parts}
    if parts & _RESTRICTED_DIR_NAMES:
        return True
    if any(marker.search(text) for marker in _RESTRICTED_MARKERS):
        return True
    return bool(_TAONGA_SELF_DECLARATION.search(_frontmatter(text)))


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


def _sync_into_dest() -> dict:
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
    blocked_taonga: list[str] = []
    for path in sorted(SOURCE.glob("**/*.md")):
        original = path.read_text(encoding="utf-8")
        relative = path.relative_to(SOURCE)

        # Hard stop, checked before any filtering: contributed taonga is
        # skipped whole, never paragraph-filtered and published in part.
        if _is_restricted(path, relative, original):
            blocked_taonga.append(str(relative))
            continue

        filtered = _filter_verified(original)
        dropped_paragraphs += len(re.split(r"\n\s*\n", original)) - len(
            re.split(r"\n\s*\n", filtered)
        )
        dest_path = DEST / relative
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_text(filtered, encoding="utf-8")
        synced_files += 1

    return {
        "synced_files": synced_files,
        "dropped_paragraphs": dropped_paragraphs,
        "blocked_taonga": blocked_taonga,
    }


_SYNC_LOCK = _threading.Lock()


def _swap_in(staging: Path, retired: Path, attempts: int = 10) -> None:
    """Move staging into place as DEST, retrying briefly.

    A directory rename on Windows fails while another thread holds a file
    inside it open. Reads here are short, so a few retries clear it; if it
    genuinely cannot swap, the existing knowledge folder is left untouched
    and working rather than half-replaced.
    """
    last_error = None
    for attempt in range(attempts):
        try:
            if DEST.exists():
                DEST.rename(retired)
            staging.rename(DEST)
            return
        except OSError as exc:
            last_error = exc
            if retired.exists() and not DEST.exists():
                retired.rename(DEST)  # put the working copy straight back
            _time.sleep(0.1 * (attempt + 1))
    _shutil.rmtree(staging, ignore_errors=True)
    raise RuntimeError(f"Could not swap the new knowledge folder into place: {last_error}")


def sync() -> dict:
    """Rebuild the local knowledge folder from the vault, atomically.

    Real bug this fixes, found 2026-09-09: the sync used to unlink every
    knowledge/*.md in place and write the new ones one at a time, while
    the running app read that same folder. A question arriving inside that
    window saw a half-built knowledge base - once measured at 81 of 144
    sections - and nothing said so. A reader now sees the old folder, or
    the new one, never a partial one.

    The original body is untouched below as _sync_into_dest(); it writes
    to the module-level DEST, which is pointed at a staging folder here.
    """
    with _SYNC_LOCK:
        return _sync_locked()


def _sync_locked() -> dict:
    global DEST
    real_dest = DEST
    # Staging is named for THIS process. These apps often run two processes,
    # each with its own refresh thread; a shared staging name let one delete
    # the other's half-written copy and swap the remains into place - measured
    # live as 64 files where the same sync reported writing 492, with no error
    # raised, because neither process saw a failure. An in-process lock cannot
    # fix a collision between processes over one folder on disk. A pid-scoped
    # name can.
    _tag = f".new.{_os.getpid()}"
    staging = real_dest.parent / (real_dest.name + _tag)
    retired = real_dest.parent / (real_dest.name + f".old.{_os.getpid()}")
    for leftover in (staging, retired):
        if leftover.exists():
            _shutil.rmtree(leftover, ignore_errors=True)

    DEST = staging
    try:
        result = _sync_into_dest()
    except BaseException:
        DEST = real_dest
        _shutil.rmtree(staging, ignore_errors=True)
        raise
    DEST = real_dest

    if not result.get("synced_files"):
        # Never swap an empty knowledge base in over a working one.
        _shutil.rmtree(staging, ignore_errors=True)
        raise RuntimeError("Refusing to sync: no knowledge files found in the source vault")

    _swap_in(staging, retired)
    _shutil.rmtree(retired, ignore_errors=True)
    return result


def main() -> None:
    result = sync()
    print(
        f"Synced {result['synced_files']} knowledge file(s) from {SOURCE} to {DEST} "
        f"(dropped {result['dropped_paragraphs']} unverified paragraph(s): "
        "gap-flagged or lower-confidence content excluded from the public app)."
    )
    blocked = result.get("blocked_taonga") or []
    if blocked:
        # Loud on purpose. Reaching this means a contributed file was found
        # inside Knowledge/, where it does not belong - it was NOT published,
        # but it needs moving back to the vault's "Taonga Tuku Iho" folder.
        print(
            f"\n*** BLOCKED {len(blocked)} contributed taonga file(s) from the public app. ***\n"
            "These were NOT published. They should not be under Knowledge/ at all - "
            "move them back to the vault's 'Taonga Tuku Iho' folder:"
        )
        for name in blocked:
            print(f"  - {name}")


if __name__ == "__main__":
    main()
