# The Tohunga's Apprentice - Public App

A free app carrying real, sourced knowledge of Maori tohunga traditions and
tikanga/kawa across iwi - built to help people do things the way their own
ancestors would have, given away free, for anyone to use.

Deliberately a **separate, standalone project** from Koro Global Hub - the
Hub holds Koro's private tasks, family info, and other workers, none of
which should ever face the public internet. This app only ever talks to
its own small `backend/`, which does exactly one thing.

## What's built so far (2026-08-27)

- `backend/` - a real, working, tested Flask API (`POST /ask`) carrying the
  same knowledge base and honesty rules as the private Hub worker. Tested
  locally: boots, loads the 3 current knowledge files, responds correctly.
  Not yet deployed anywhere public - see "Going live" below.
- `backend/sync_knowledge.py` - run this any time the Hub's
  `apprentice_research` worker has grown the knowledge base further, to
  pull a fresh snapshot into this project. Deliberately manual, not
  automatic - each sync is a real "this is ready to go out publicly"
  decision.

## What's still needed - real, concrete next steps

### 1. Get a real OpenAI API key for THIS app specifically

Don't reuse a personal key indefinitely for a public app - public traffic
means real, unpredictable, ongoing cost. `backend/app.py` reads
`OPENAI_API_KEY` from the environment, and has a blunt built-in safeguard
(`MAX_REQUESTS_PER_DAY_PER_IP`, default 40/day) to stop unbounded spend
from one bad actor - raise it only once you're actually watching real
usage and real cost, not before.

### 2. Decide where the backend actually runs (Koro's decision - real ongoing cost)

It can't stay on your laptop long-term (needs to be always-on, and your
laptop already runs the private Hub - keep them separate). Real, cheap
options worth comparing when ready: Render, Railway, Fly.io (all have
free or near-free starter tiers, real monthly cost once traffic grows
past that). This is a real recurring-cost decision, not a one-time build
step - worth a short conversation before committing.

### 3. The app itself - two real developer accounts, only you can create these

These need your own identity/payment details - not something built for
you, has to be done by you:
- **Apple Developer Program** - developer.apple.com, $99/year (individual
  account is enough to start).
- **Google Play Console** - play.google.com/console, $25 one-time.

### 4. Building the actual app (no Mac needed - real plan for your setup)

Your machine is Windows-only with no Mac, so real iOS builds need a cloud
build service rather than local Xcode. **Expo + EAS Build** is the real,
standard, free-to-start path for exactly this situation - it builds both
the Android and iOS app in the cloud from one codebase, no Mac required.
Real next step once accounts above exist: scaffold the actual Expo app in
this folder (`app/`), point it at the deployed backend, and walk through
a real EAS Build + submission together.

### 5. What ships in the app, non-negotiable

The disclaimer ("I'm the Apprentice, not a tohunga - check with your own
people") has to be visible in the app itself, every time, not buried in
a settings screen - see `backend/app.py`'s `DISCLAIMER` constant, which
the app's UI should surface prominently on every answer.

## Honest status

This is a real, working backend, not a mockup - but "an app you can
download" still needs: a funded OpenAI key, a real hosting decision, two
developer accounts only Koro can create, and the actual Expo app build.
Each of those is a real next step, tracked here rather than assumed done.
