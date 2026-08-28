"""The Tohunga's Apprentice - standalone public backend.

Deliberately separate from Koro Global Hub (same reasoning as the Cultural
Check Agent): the Hub holds Koro's private tasks, family info, and other
workers, none of which should ever face the public internet. This service
does exactly one thing - answer questions from the same knowledge base the
private Hub worker uses, with the same "apprentice, not tohunga" honesty
rules baked in - and nothing else. It has no access to the Hub, the vault,
or any of Koro's other systems.

Knowledge is a deliberately-synced snapshot (see sync_knowledge.py), never
a live read of Koro's personal vault - this process should be safely
deployable to a public host with zero path dependency on his own machine.

Real, honest cost note (read before deploying this publicly): every /ask
call makes one real, paid OpenAI API call. MAX_REQUESTS_PER_DAY below is a
blunt, real safeguard against unbounded spend from public traffic - raise
it deliberately once real usage and real cost are being watched, not
before.
"""
from __future__ import annotations

import os
import re
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request
from openai import OpenAI

import sync_knowledge

BASE_DIR = Path(__file__).resolve().parent
KNOWLEDGE_DIR = BASE_DIR / "knowledge"


def _load_api_key() -> str:
    """Real deployment (Render/Railway/etc) should always set OPENAI_API_KEY
    as a real environment variable - that's the standard, correct way on a
    cloud host. This falls back to Windows Credential Manager (via keyring)
    only for local development on Koro's own machine, so the raw key never
    has to sit in a plaintext .env file even for local testing."""
    from_env = os.environ.get("OPENAI_API_KEY", "")
    if from_env:
        return from_env
    try:
        import keyring

        from_keyring = keyring.get_password("TohungasApprenticeApp", "openai_api_key")
        return from_keyring or ""
    except Exception:
        return ""


OPENAI_API_KEY = _load_api_key()
MODEL = os.environ.get("TOHUNGAS_APPRENTICE_MODEL", "gpt-4o-mini")

# A real, blunt cost/abuse safeguard - not a business rate-limit product,
# just enough to stop one bad actor or a runaway client from generating
# unbounded real API spend against Koro's own key. In-memory only
# (deliberately simple for a first deploy) - resets if the process
# restarts, and does not share state across multiple server instances.
MAX_REQUESTS_PER_DAY_PER_IP = int(os.environ.get("MAX_REQUESTS_PER_DAY_PER_IP", "40"))
_request_log: dict[str, list[float]] = defaultdict(list)

APP_NAME = "The Tohunga's Apprentice"

DISCLAIMER = (
    "I'm the Tohunga's Apprentice, not a tohunga myself - I carry real, "
    "sourced research about Maori tikanga and tohunga traditions, but real "
    "tohunga status and real authority over tapu matters belongs to your "
    "own kaumatua, hapu, and iwi, never to an app. Tikanga genuinely "
    "differs by iwi and marae - treat what I say as a starting point, and "
    "confirm anything that matters with your own people."
)

SYSTEM_PROMPT = f"""
You are {APP_NAME} - a free, public knowledge-consultation assistant
carrying deeply researched, real, sourced knowledge about traditional
Maori tohunga (specialist/expert) roles, and about tikanga and kawa
(protocol) across iwi.

VOICE: speak with the warmth, patience, and unhurried care of someone
raised close to wise elders - take the question seriously, acknowledge
what's actually being asked before answering, and never sound rushed or
clinical. This is a tone, not a status: it never becomes a claim to BE an
elder or a tohunga (see below) - a genuinely well-raised apprentice speaks
this way precisely because of who taught them, while staying clear about
what they themselves are.

CRITICAL, NEVER DROP: you are an apprentice, not a tohunga, and must never
imply, claim, or accept that title for yourself. Real tohunga status is
earned and bestowed by a person's own people (kaumatua, hapu, whanau) -
never self-declared, never conferred by AI. Whenever a question touches
something genuinely tapu, personal, or consequential (a real ceremony, a
real body marking, a real karakia, anything affecting a real person's
spiritual life), say plainly that what you're offering is knowledge and
context, not authority - the real next step is talking to real kaumatua
or a recognised tohunga.

CRITICAL, ON TIKANGA SPECIFICALLY: tikanga and kawa genuinely differ by
iwi, hapu, and even individual marae - there is no single "correct
national version". Give the real documented general shape, say plainly
where practice is known to vary, and point toward confirming with the
specific iwi/marae/whanau involved rather than presenting one variant as
universal. If the question names a specific iwi/hapu and the excerpts
below contain real, specific documented facts about that iwi (not just
the general pattern), lead with those specific facts before the general
material - a specific real fact beats a generic hedge every time.

You are talking to members of the public through a free app, most of whom
you know nothing about - you cannot assume they share Koro's own whakapapa
or context. Be especially careful never to let an answer read as more
authoritative than it is.

Answer only from the real, sourced knowledge excerpts provided below, plus
your own general knowledge where it is clearly reliable - never invent
specific traditional details, names, whakapapa, or claims. Mark your own
confidence honestly, the same way the source research does. The excerpts
below are the most relevant sections retrieved for this specific
question, not the entire knowledge base - if they genuinely don't cover
something the question asked about, say so plainly rather than guessing;
do not assume silence in the excerpts means nothing is known anywhere.
""".strip()


def _load_knowledge() -> str:
    files = sorted(KNOWLEDGE_DIR.glob("**/*.md")) if KNOWLEDGE_DIR.is_dir() else []
    if not files:
        return ""
    sections = [
        f"# SOURCE FILE: {path.name}\n\n{path.read_text(encoding='utf-8')}"
        for path in files
    ]
    return "\n\n---\n\n".join(sections)


# Real retrieval, not "dump the whole knowledge base into every prompt" -
# built 2026-08-27 after a real, live test caught it failing: asked about
# Te Arawa tangihanga tikanga, the app gave vague hedge language instead
# of the real, specific, documented Te Arawa facts that ARE in the
# knowledge base (strict male-only paepae with a protective rationale,
# tau utuutu speaking order, the kawa/tikanga terminology flip). Root
# cause: stuffing the entire ~100,000-character corpus into one prompt
# buries specific facts in volume. This only gets worse as the standing
# research worker keeps growing the knowledge base - a real reason to fix
# this now rather than let it quietly degrade over time.
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z'-]{2,}")
_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "have", "what", "when",
    "where", "which", "should", "would", "could", "about", "from",
    "their", "they", "them", "does", "did", "are", "was", "were", "will",
    "can", "know", "tell", "explain", "please", "real", "someone",
    "something", "having", "person", "there",
}


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Minimal, dependency-free YAML frontmatter reader - handles the two
    real shapes this project's own generated files use: `key: value` and
    `key: [a, b, c]`. Not a general YAML parser, deliberately - the vault's
    frontmatter is hand/code-generated in this exact simple shape (see the
    organizing-obsidian-for-ai skill), so a full YAML dependency isn't
    needed."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    meta: dict = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            meta[key] = [v.strip().strip('"\'') for v in value[1:-1].split(",") if v.strip()]
        else:
            meta[key] = value.strip('"\'')
    return meta, text[match.end():]


def _split_into_sections(text: str) -> list[tuple[str, str]]:
    matches = list(_HEADING_RE.finditer(text))
    sections: list[tuple[str, str]] = []
    if not matches:
        return [("(whole file)", text)]
    if matches[0].start() > 0:
        intro = text[: matches[0].start()].strip()
        if intro:
            sections.append(("(intro)", intro))
    for i, m in enumerate(matches):
        heading = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        if content:
            sections.append((heading, content))
    return sections


def _all_sections() -> list[dict]:
    # Recursive - the vault (and this synced copy of it) is organised into
    # Foundations/ and Iwi-Specific/ subfolders (2026-08-27 reorganisation).
    files = sorted(KNOWLEDGE_DIR.glob("**/*.md")) if KNOWLEDGE_DIR.is_dir() else []
    result = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        meta, body = _parse_frontmatter(text)
        iwi_tags = [str(i).lower() for i in meta.get("iwi", [])]
        for heading, content in _split_into_sections(body):
            result.append(
                {"file": path.name, "heading": heading, "content": content, "iwi_tags": iwi_tags}
            )
    return result


def _question_terms(question: str) -> list[str]:
    words = [w.lower() for w in _WORD_RE.findall(question)]
    return [w for w in words if w not in _STOPWORDS]


_BOILERPLATE_HEADINGS = {
    "sources referenced", "(intro)", "honest limits of this document",
    "how to read the confidence marks in this document",
}


def _retrieve_relevant(question: str, char_budget: int = 9000, min_sections: int = 3) -> str:
    """Score every section by real keyword overlap with the question, and
    include only the highest-scoring ones - a specific named iwi/topic in
    the question (e.g. "Te Arawa") now reliably pulls in the sections that
    actually mention it, instead of getting diluted by everything else.

    Real fix, same problem the Hub's own hub_knowledge.py retrieval already
    solved: a term repeated across most sections of a document (like
    "tikanga" in a document that is literally about tikanga) can't actually
    discriminate relevant from irrelevant content, however often it's
    repeated - it's down-weighted here in proportion to how common it is,
    so a rare, specific term (like an iwi name) dominates scoring instead
    of a generic one that happens to occur more times."""
    sections = [s for s in _all_sections() if s["heading"].strip().lower() not in _BOILERPLATE_HEADINGS]
    if not sections:
        return ""
    terms = _question_terms(question)
    if not terms:
        terms = []

    total = len(sections)
    doc_freq = {
        term: sum(1 for s in sections if term in s["content"].lower() or term in s["heading"].lower())
        for term in terms
    }

    scored = []
    for sec in sections:
        heading_l = sec["heading"].lower()
        content_l = sec["content"].lower()
        score = 0.0
        matched_terms = 0
        for term in terms:
            freq = doc_freq.get(term, 0)
            if freq == 0 or freq / total > 0.5:
                continue  # present in >half of all sections - not discriminative
            weight = 1.0 / freq  # rarer terms count for more
            local = 0.0
            if term in heading_l:
                local += 15 * weight
            occurrences = content_l.count(term)
            if occurrences:
                local += min(occurrences, 5) * 4 * weight
                matched_terms += 1
            score += local
        # Real frontmatter tag match - ground truth, not inferred from raw
        # text, so it outranks pure keyword scoring: a question naming an
        # iwi that this file's own "iwi:" frontmatter names gets a strong,
        # flat boost regardless of how the file's prose happens to be worded.
        if any(any(term in tag for tag in sec["iwi_tags"]) for term in terms):
            score += 40
        if matched_terms >= 2:
            score *= 1.5  # real co-occurrence of multiple distinct terms outranks one repeated word
        scored.append((score, sec))
    scored.sort(key=lambda item: -item[0])

    selected: list[str] = []
    used = 0
    for score, sec in scored:
        if score <= 0 or used >= char_budget:
            break
        block = f"[{sec['file']} — {sec['heading']}]\n{sec['content']}"
        selected.append(block)
        used += len(block)

    # Real questions can be broad enough to score nothing highly (e.g. "what
    # is tikanga?") - fall back to the next-best sections regardless of
    # score so the model still has real grounding, never an empty prompt.
    if len(selected) < min_sections:
        for score, sec in scored:
            if len(selected) >= min_sections or used >= char_budget:
                break
            block = f"[{sec['file']} — {sec['heading']}]\n{sec['content']}"
            if block in selected:
                continue
            selected.append(block)
            used += len(block)

    return "\n\n---\n\n".join(selected)


KNOWLEDGE = _load_knowledge()
_last_refresh: dict = {"at": None, "synced_files": 0, "dropped_paragraphs": 0, "error": None}

# Real automatic refresh, not a manual step - Koro's own instruction,
# 2026-08-27: "make it refresh by itself only verified information to
# keep the app honest." Runs only while this process has real access to
# Koro's private vault (true today, since this runs on his own machine
# behind a Cloudflare tunnel) - if this backend is later moved to a real
# cloud host with no path into his machine, this loop will simply find
# nothing to sync and log that plainly rather than crash; a different
# sync mechanism (e.g. Koro pushing a filtered snapshot to the host)
# would be the real next step for that deployment shape.
REFRESH_INTERVAL_HOURS = float(os.environ.get("TOHUNGAS_APPRENTICE_REFRESH_HOURS", "24"))


def _refresh_loop() -> None:
    global KNOWLEDGE
    while True:
        try:
            if sync_knowledge.SOURCE.is_dir():
                result = sync_knowledge.sync()
                KNOWLEDGE = _load_knowledge()
                _last_refresh.update(
                    at=datetime.now(timezone.utc).isoformat(),
                    synced_files=result["synced_files"],
                    dropped_paragraphs=result["dropped_paragraphs"],
                    error=None,
                )
            else:
                _last_refresh.update(
                    at=datetime.now(timezone.utc).isoformat(),
                    error=f"Private vault not reachable from this process: {sync_knowledge.SOURCE}",
                )
        except Exception as exc:  # noqa: BLE001 - a failed refresh should never crash the server
            _last_refresh.update(at=datetime.now(timezone.utc).isoformat(), error=str(exc))
        time.sleep(max(300, REFRESH_INTERVAL_HOURS * 3600))


threading.Thread(target=_refresh_loop, daemon=True).start()

# The Expo web export (see app/, "npx expo export --platform web") is
# served directly by this same Flask process at "/" - one backend, one
# public URL, one tunnel, for both the web app and its API. Falls back to
# a plain JSON status page if the web app hasn't been built yet (dist/
# missing), so the API is still usable/testable on its own.
WEB_DIST_DIR = BASE_DIR.parent / "app" / "dist"
_web_app_built = WEB_DIST_DIR.is_dir() and (WEB_DIST_DIR / "index.html").is_file()

app = Flask(
    __name__,
    static_folder=str(WEB_DIST_DIR) if _web_app_built else None,
    static_url_path="",
)


def _rate_limited(ip: str) -> bool:
    now = time.time()
    window_start = now - 86400
    recent = [t for t in _request_log[ip] if t > window_start]
    _request_log[ip] = recent
    if len(recent) >= MAX_REQUESTS_PER_DAY_PER_IP:
        return True
    _request_log[ip].append(now)
    return False


@app.get("/")
def index():
    if _web_app_built:
        return app.send_static_file("index.html")
    return jsonify(
        {
            "name": APP_NAME,
            "status": "ok" if OPENAI_API_KEY else "not configured (missing OPENAI_API_KEY)",
            "web_app_built": _web_app_built,
            "knowledge_files_loaded": len(list(KNOWLEDGE_DIR.glob("**/*.md"))) if KNOWLEDGE_DIR.is_dir() else 0,
            "disclaimer": DISCLAIMER,
        }
    )


@app.get("/api/status")
def status():
    return jsonify(
        {
            "name": APP_NAME,
            "status": "ok" if OPENAI_API_KEY else "not configured (missing OPENAI_API_KEY)",
            "web_app_built": _web_app_built,
            "knowledge_files_loaded": len(list(KNOWLEDGE_DIR.glob("**/*.md"))) if KNOWLEDGE_DIR.is_dir() else 0,
            "last_verified_refresh": _last_refresh,
            "disclaimer": DISCLAIMER,
        }
    )


@app.post("/ask")
def ask():
    if not OPENAI_API_KEY:
        return jsonify({"error": "Server not configured - no OPENAI_API_KEY set."}), 500

    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
    if _rate_limited(ip):
        return jsonify(
            {"error": f"Daily question limit reached ({MAX_REQUESTS_PER_DAY_PER_IP}/day). Try again tomorrow."}
        ), 429

    payload = request.get_json(silent=True) or {}
    question = str(payload.get("question", "")).strip()
    if not question:
        return jsonify({"error": "A question is required."}), 400
    if not KNOWLEDGE:
        return jsonify({"error": "Knowledge base is empty - run sync_knowledge.py first."}), 500

    relevant = _retrieve_relevant(question)
    client = OpenAI(api_key=OPENAI_API_KEY)
    prompt = f"Relevant knowledge excerpts:\n\n{relevant}\n\n---\n\nQuestion: {question}"
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        answer = response.choices[0].message.content
    except Exception as exc:  # noqa: BLE001 - surfaced to the caller as a plain error
        return jsonify({"error": f"Failed to get an answer: {exc}"}), 502

    return jsonify({"answer": answer, "disclaimer": DISCLAIMER})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8420"))
    app.run(host="0.0.0.0", port=port)
