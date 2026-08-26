# Kollektivgedaechtnis Tool 1 — SDD progress

Plan: docs/superpowers/plans/2026-08-12-kollektivgedaechtnis-tool1.md
Branch: tool1-implementation
Base: 723282c

Task 1: complete (commits bf57ae0..46ea07e, review clean — approved, no Critical/Important)
  Minor carried to final review: load_config silently falls back to defaults when the --config path is missing (brief-mandated).

Pre-flight scan: 9 findings, all fixed in plan (commit 6d02803). Nothing deferred.
Task 2: complete (commits 6d02803..0eb03d4, review clean after one fix round)
  Fix applied: Store._next_id was non-atomic (SQLite 3.34 has no RETURNING) -> threading.Lock + concurrency test.
  CARRY TO TASK 12 (open, must be handled there): the sqlite3 connection is opened check_same_thread=False,
  but only _next_id is locked. FastAPI runs sync route handlers in a threadpool, so /api/min_mentions,
  /api/hidden and /api/positions can write concurrently with the Core and hit
  "cannot start a transaction within a transaction". Task 12 must serialise Store writes (store-wide lock)
  or make the routes async and marshal writes onto the Core loop.

Task 3: complete (commits 5808dcb..046f759, review clean) — kg/sse.py, kg/transcript.py,
  kg/stt_client.py, docs/stt-contract.md. 27 tests passing at 046f759.

Task 4: complete (commits 046f759..ed8112a, review clean after two fix rounds) — kg/segmentation.py.
  Two defects found in review of 44addf7 and FIXED on Birk's decision (1e407a5), plan synced:
    (a) find_stop_phrase did a substring match on the normalised string, so a stop phrase matched
        inside a longer inflected word — "Die Aufnahme beendende Handlung war klar." falsely ended
        a live interview.
    (b) strip_stop_phrases hand-enumerated its own separator class, which diverged from detection's
        _PUNCT = [^\w\s]. "Bitte Aufnahme… beenden jetzt." was DETECTED but NOT stripped, leaking
        the raw command into the LLM extraction call.
  Root cause of (b) was the duplicated notion of "separator", not the missing character. Fixed
  structurally: one tokeniser (NFC -> \w+ -> _fuzzy) feeds BOTH functions, which now match a
  contiguous token SUBLIST and cut raw token spans. Detection and stripping can no longer diverge,
  and matches are word-anchored by construction. _word_pattern deleted.
  Follow-up fix (ed8112a): _phrase_tokens skipped the NFC step _tokenize does, so an NFD stop phrase
  from config.toml fragmented at its umlaut and never matched. Regression test added.
  Rationale for strictness (Birk): a false positive truncates a live interview and a leaked command
  permanently corrupts the graph; a missed mangled command is already covered by the
  interview_timeout_s safety net and the LLM end-detection in the extraction call.
  Minor carried to final review: strip_stop_phrases removes occurrences of EVERY configured phrase,
  so with future phrases sharing tokens the stripped span can exceed the phrase find_stop_phrase
  reports. By design per the brief; harmless for the current two-phrase config.

Task 5: complete (commit b3062a3, review clean first pass) — kg/session.py, tests/test_session.py.
  Pure SessionTracker/Transition state machine, verbatim from the plan. 51 tests passing at b3062a3.

Task 6: complete (commit dde57c2, review clean first pass) — kg/photos.py, tests/test_photos.py.
  Verbatim from the plan; reviewer additionally verified real EXIF-rotated JPEGs (tags 1/3/6/8),
  extreme aspect ratios, P/L/RGBA sources and circle anti-aliasing. 55 tests passing at dde57c2.
  Noted, not a defect: RGB conversion drops a transparent source's alpha without compositing —
  irrelevant for camera photos, out of scope for the brief.

Task 7: complete (commit 7c247b9, review clean after adjudication) — kg/telegram_bot.py.
  Verbatim from the plan. 60 tests passing at 7c247b9. Two findings, both in plan-mandated code:
  - Important, ADJUDICATED NOT REACHABLE: _handle_photo wraps only download+make_portrait, so an
    on_photo/on_text callback that raises escapes dispatch(). Not reachable in the plan's own wiring:
    Task 11 passes Core.on_photo/on_text, which are bare _queue.put_nowait calls on an unbounded
    queue, and Core.run_worker already has a catch-all. PTB's Application.process_update also
    catches handler exceptions. Re-check IF any later task ever calls dispatch() from its own loop.
  - Minor CARRIED TO FINAL REVIEW: when the download succeeds but make_portrait fails, the raw .jpg
    is left orphaned on disk (logged, no on_photo, no cleanup). Accumulates for the event's duration.

Task 8: complete (commit 0272cf4, review clean first pass) — kg/llm.py, kg/extraction.py. 69 tests passing.
  Anthropic API shape verified against current docs before dispatch: output_config={"effort", "format":
  {"type":"json_schema","schema":...}}, model claude-opus-5, stop_reason=="refusal" handled, no thinking/
  temperature. Reviewer confirmed EXTRACTION_SYSTEM byte-identical to the plan (typographic quotes,
  umlauts, line continuations) and that end-detection + extraction share ONE llm.parse call.
  Two Minors CARRIED TO FINAL REVIEW, both plan-mandated:
  - LLMClient.parse's `except Exception` retries deterministic failures too (schema-validation errors,
    refusals), burning an attempt on cases a second identical call cannot fix. Pinned by the plan's tests.
  - build_extraction_prompt does not escape the transcript, so a transcript containing the literal
    "--- ENDE TRANSKRIPT ---" produces a duplicate delimiter. Very low likelihood for unstructured STT.

DECISIONS BY BIRK (2026-08-13), both binding:
  D1 (Task 9 merge edges): the loser's edges FOLD ONTO THE WINNER; mention counts combine.
     Rationale: the live dial counts how many people mentioned a term (spec 7). If merging dropped
     edges the mention count would FALL and a node could become LESS visible by merging — the inverse
     of what merging means. Merging is the finding that more people meant the same thing, so the node
     must get stronger; dropping edges would contradict the station's core thesis. Edges must be
     de-duplicated when folding (one person must never end up with two edges to the winner).
  D2 (Task 12b): store-wide threading.RLock. Re-entrant is MANDATORY (_next_id is called from inside
     other write methods; a plain Lock would deadlock). Guard every public Store method, add a
     multi-threaded regression test that reproduces "cannot start a transaction within a transaction"
     without the fix, sync the corrected code into BOTH the plan's Task 2 and Task 12 code blocks.
     12b's review runs on the most capable model (the sanctioned exception to sonnet/haiku).

Task 9: COMPLETE (commits ab0fa56 + 951bfca + 0134a00, review clean after the fix round under D1).
  124 tests passing at 0134a00. All five review findings fixed, each TDD'd RED->GREEN:
  - C1/C2 unified: apply_merges now resolves EVERY member to an existing term, picks one winner and
    folds all other existing terms into it via the new Store.fold_term; a canonical_label collision
    is folded in as just another loser, and the rename to canonical_label happens AFTER the colliding
    term is gone — rename_term can no longer raise IntegrityError.
  - fold_term (kg/store.py) moves aliases first, then edges through the idempotent add_edge (so one
    person cannot end up with two edges to the winner), then deletes the loser's stale edges, its
    position row (node_id "term:<id>") and its term row last — FK-safe under PRAGMA foreign_keys=ON.
    Reviewer hand-traced this order against the schema.
  - C3: new re-entrant Store.transaction() suppresses inner per-method commits (every write method now
    calls _commit()), commits once, rolls back on exception. apply_merges is all-or-nothing.
    Reviewer verified by grep that NO write method still calls self.conn.commit() directly.
  - I4 (label in two LLM groups): a member already claimed by an earlier group is dropped from later
    groups; a group left with <2 members is skipped and the leftover falls back standalone. Matches
    MERGE_SYSTEM's own contract ("Gib nur Gruppen mit mindestens zwei Mitgliedern zurück").
  - I5: OpenRouterEmbedder now rejects a response whose rows are missing, extra, or missing/duplicate
    an "index" (a missing index no longer defaults to 0 and collides).
  Follow-up commit 0134a00: plan's OpenRouterEmbedder block synced byte-for-byte (controller verified),
  stale "Expected: PASS" counts corrected (Task 2 12->17, Task 9 19->26), and an N=3 fold test added —
  it passed unmodified, so the winner/losers unpacking already generalised.
  Reviewer ⚠️ RESOLVED BY DESIGN, HANDED TO 12b: transaction()'s _tx_depth is an unguarded plain int.
  Task 12b's brief now requires _tx_depth to be read/mutated only under the store-wide RLock.
  Both demonstrated live, both inherited verbatim from the plan's apply_merges (not implementer slips):
  - CRITICAL 1: merging two already-EXISTING terms orphans the loser. add_alias is INSERT OR REPLACE, so
    the loser's surface form repoints to the winner, but its term row and all its edge rows survive.
    Result: two nodes on the public wall for one concept, loser's mention count stranded. Reachable
    because the merge prompt shows existing neighbour labels as candidates and nothing stops the LLM
    putting two of them in one group.
  - CRITICAL 2: a canonical_label colliding with a DIFFERENT existing term's label raises
    sqlite3.IntegrityError (term.label is UNIQUE) and aborts the interview. Reachable — the prompt tells
    the LLM to prefer an existing formulation. Each store call auto-commits individually while
    record_merge_decision runs only after the loop, so a crash leaves earlier groups' renames/aliases
    committed with no decision logged. (Task 11's pipeline wraps this in a catch-all, so the STATION
    survives — the interview is marked "failed". The half-applied graph state is the remaining damage.)
  - Important: same label in two LLM groups silently conflates them (group 1's aliases are visible to
    group 2 within the same call).
  - Important: OpenRouterEmbedder does not validate response row count; a short response mis-pairs
    vectors via zip and degrades preselection (rows missing "index" default to 0 and can collide).
  OPEN QUESTION FOR BIRK (blocks the fix): when two live nodes merge, do the loser's edges fold onto the
  winner (mention counts combine) or are they dropped (merged node keeps only the winner's history)?
  Recommended fix once decided: fold edges onto the winner; resolve a label collision as a merge with the
  colliding term instead of crashing; wrap apply_merges in ONE transaction so an interview is all-or-nothing.

Task 10: complete (commit 3d4425a, review clean first pass) — kg/export.py, tests/test_export.py.
  93 tests passing. Reviewer verified the JSON contract field-by-field (it is the read-only interface for
  Tool 2), that nothing is filtered out, that the .tmp file is in the destination directory so os.replace
  is genuinely atomic, and that umlauts are written as literal UTF-8 (ensure_ascii=False).
  Three Minors CARRIED TO FINAL REVIEW, all plan-mandated: a stray graph.json.tmp can survive a crash
  mid-write (harmless, deterministic name, overwritten next time); build_graph does one mention_count
  query per term (N+1, fine at conference scale); int(get_setting("min_mentions","1")) would raise on a
  non-numeric setting (no code path writes one today).

Task 11: complete (commit c400d52, review clean after adjudication) — kg/pipeline.py. 100 tests passing.
  First task exercising Tasks 2/3/4/8/9/10 together. Reviewer verified the spec order holds as EXECUTED,
  that only stripped text reaches extract() (raw is never reused), and that the merge call is skipped when
  every label already has a persisted decision. Two findings, both in plan-mandated code:
  - Critical, ADJUDICATED NOT REACHABLE: set_person_status/text_between/strip_stop_phrases sit OUTSIDE the
    try, so an I/O error there propagates out of process_interview and leaves the person in "processing".
    The plan's own caller handles it: Core._process wraps the processor in try/except, sets status
    "failed", and re-broadcasts graph+state. Re-check IF any later task calls process_interview directly.
  - Important -> downgraded to Minor, CARRIED TO FINAL REVIEW: `text[:end].strip() or text.strip()` means
    an interview_end_index of 0 (the model saying "none of this is interview content") falls back to the
    FULL tail-inclusive text, defeating end-detection exactly when it fired. The reviewer called this a
    public-wall leak; that is overstated — the transcript is NOT part of graph.json (see the Task 10 shape),
    so the damage is a bad stored transcript, not wrong text under a portrait on the wall. Terms and quotes
    come from the extraction result, which the prompt governs separately.
  - Minor CARRIED: store.add_quote has no dedup (unlike add_edge), so re-running the pipeline for one
    person_id would duplicate quotes. No code path re-runs it today.

Task 12: SPLIT INTO TWO COMMITS.
  12a COMPLETE (commit 4d01d2f, review clean first pass — Approved, no Critical/Important).
    Reviewer byte-compared kg/bus.py and kg/server.py against the brief (identical), verified all 12
    endpoints, and checked each in-scope global constraint (one dial, hide-only curation, persisted
    positions, German UI strings, serial interview). Its one ⚠️ (does Store really persist positions/
    hidden to SQLite for crash recovery — Task 2 code, outside the diff) RESOLVED by the controller:
    store.set_hidden, save_positions (upsert) and get_positions all write/read SQLite and commit.
    Three Minors CARRIED TO FINAL REVIEW (see roll-up below).
  12a details — kg/bus.py, kg/server.py, minimal frontend, plan
    verbatim. 111 tests passing. NOTE for Tasks 13-15: frontend/static/vendor/ was created empty and git
    does not track empty dirs, so the vendored Cytoscape drop needs to create it.
  12b IMPLEMENTED (commit ac4c74e) — store-wide threading.RLock per D2. 125 tests passing.
    REVIEWED ON OPUS (the sanctioned exception). Verdict: Approved, NO Critical. The reviewer
    AST-enumerated Store and confirmed all 32 public methods carry @_locked (reads included), that
    every read materialises rows inside the locked body (no cursor escapes), that transaction()'s
    `with self._lock` encloses the yield so the lock spans the caller's whole block (the
    @contextlib.contextmanager trap — decorating the factory instead of the body — was correctly
    avoided), that _tx_depth is touched only under the lock on both success and rollback paths,
    that NO caller holds the lock across network I/O (the LLM/embedding calls all sit outside any
    transaction in pipeline.py), and that no second lock exists to invert against (bus.publish is
    put_nowait; the embedding cache owns a separate connection). It independently reproduced RED by
    neutralising _locked in a /tmp copy. Re-entrancy verified live on both nesting chains
    (apply_merges->record_merge_decision->_next_id, fold_term->transaction->add_edge->_next_id).
    Fix round: commit 32119f4, RE-REVIEW CLEAN (Approved, no Critical/Important). All five applied:
      (1) the stale comment in tests/test_store.py that claimed create_person's INSERT+commit were
          deliberately unprotected — it now stated the OPPOSITE of the shipped invariant and invited a
          maintainer to re-fix serialisation outside kg/store.py, which the spec forbids;
      (2) join(timeout=60) + assert not is_alive() — the opus reviewer PROVED that regressing RLock to
          Lock made the test deadlock silently forever instead of failing;
      (3) the test now asserts the OPERATOR threads' writes survived too, not just the pipeline's;
      (4) _commit() takes the lock instead of relying on a docstring invariant;
      (5) BEHAVIOUR CHANGE, deliberate: transaction() catches BaseException, not Exception. A
          KeyboardInterrupt on operator shutdown previously skipped the rollback while finally still
          zeroed _tx_depth and released the lock, so the NEXT unrelated write's _commit() would commit
          a half-applied fold_term (loser deleted, edges not moved) permanently to disk.
      Re-reviewer independently re-verified the two hardest-to-fake claims: the plan's Task 2 Store
      block diffs byte-for-byte against kg/store.py (exit 0), and the item-5 test observes the rollback
      through a genuinely SEPARATE sqlite connection. 126 tests passing at 32119f4.
  TASK 12 COMPLETE (12a 4d01d2f + 12b ac4c74e + 32119f4).
  12b original defect description — the carried Task 2 concurrency fix. CONFIRMED still unaddressed: the plan's Task 12
    route handlers are sync `def`, so FastAPI runs them in a threadpool and /api/min_mentions, /api/hidden,
    /api/camera and /api/positions can write on the shared sqlite connection concurrently with the Core and
    the pipeline. Plan of record: give Store a store-wide threading.RLock (RE-ENTRANT — _next_id is called
    from inside other write methods, so a plain Lock would deadlock), guard every public method, add a
    multi-threaded test, and sync the fix back into the plan's Task 2 AND Task 12 code blocks.
    Split out so the concurrency diff gets its own focused review on the most capable model.

Task 13: COMPLETE (commit 26520c9 + doc-sync 28f4a21, review clean first pass — Approved, no
  Critical/Important). frontend/static/graph-model.js (visibleGraph / toCytoscape / newNodeIds),
  frontend/static/test-harness.html, frontend/static/vendor/cytoscape.min.js, tests/conftest.py,
  tests/test_graph_model.py. 134 tests passing at 26520c9 (8 new, Playwright-driven).
  ENVIRONMENT FACTS FOR TASKS 14/15/20 (do not rediscover):
  - unpkg.com and cdn.jsdelivr.net are UNREACHABLE from this machine (connection times out);
    registry.npmjs.org and pypi.org work. Cytoscape 3.30.2 was vendored from the npm tarball
    (sha256 83e8c54a...dac81, controller-verified) and IS committed — the empty untracked
    frontend/static/vendor/ carried item is now CLOSED.
  - Playwright chromium is already installed (~/.cache/ms-playwright). This Debian 11 host cannot
    `playwright install` the pinned revision, so conftest's browser fixture falls back to the cached
    build via executable_path. The fallback is conditional and re-raises if nothing is found, so a
    working machine never enters it.
  DEVIATION SIGNED OFF BY THE CONTROLLER: the brief mandated a session-scoped `browser` fixture;
  shipped as module-scoped because session scope leaves playwright's greenlet-held event loop marked
  running and broke 7 pytest-asyncio tests ("Cannot run the event loop while another loop is
  running"). Cost is one extra browser launch per test module — negligible at this size. Plan synced
  in 28f4a21, so Task 14 must NOT "restore" session scope.
  Three Minors CARRIED TO FINAL REVIEW (see roll-up below).

Task 14: COMPLETE (commits 5342dbc + bea19bb + fb9d326, clean after two fix rounds). 149 tests at
  fb9d326. frontend/static/{camera.js,projection.js,base.css,theme-a/b/c.css,render-harness.html},
  frontend/projection.html, tests/test_camera.py, tests/test_projection.py.
  Verified by review and still asserted: no-reshuffle (existing nodes lock()ed around the cose run,
  randomize:false, tested against real Cytoscape), person↔term only, one dial, no store writes beyond
  POST /api/positions, no true black anywhere, bare net (projection.html is only <div id="cy"> + the
  theme <link>), person = portrait circle + golden ring with label:'', term = the only text.
  Three defects found in the plan's OWN verbatim Task 14 code, all fixed and synced back:
  - `background-image: 'data(portrait)'` CRASHED Cytoscape's style parser for a person whose portrait
    failed to generate -> now `(ele) => ele.data('portrait') || 'none'`; that node still renders as a
    person (fill + gold ring survive).
  - single-quoted `Georgia, 'Times New Roman', serif` silently fell back to the default font.
  - theme-c's `--label-outline-color: #000000` violated the spec's own no-true-black constraint
    -> #101014. NOTE FOR BIRK: this contradicted the plan's literal example value; the Global
    Constraint was treated as governing. Say if you want the literal value back.
  THE BIG ONE (would have shipped invisibly): `?theme=` never reached the Cytoscape elements at all.
  projection.html swapped the <link> href and called createGraphView in the SAME tick, but
  createGraphView bakes its style array from getComputedStyle — which still returned the PREVIOUS
  stylesheet. Every theme rendered theme-a nodes with only the background switching, which would have
  silently invalidated Task 20's whole A-D comparison series. Now gated on the stylesheet's real
  `load` event (same-href assignment fires no event in Chromium — handled), with the `?theme=` value
  validated against the a/b/c allowlist and an `error` listener that warns and resolves anyway:
  a bad theme degrades, it can never hang the wall blank. Regression test reads a real Cytoscape-baked
  style (.style('border-color')) per theme, not the page background.
  Camera interactivity is now gated on mode (manual = pan/zoom/grab enabled; fit and pan = all three
  disabled, applied at construction too), so a stray touch at the unattended wall can no longer drag
  a node off its persisted position — which nothing would have corrected, since update() never
  repositions nodes already in cy.
  Minor CARRIED: onPositions reports ALL node positions on every layout run, not just the newly
  placed ones (harmless — the server overwrite is idempotent and never re-broadcasts).
  Minor CARRIED: the `error`-listener backstop itself has no automated test (simulating a
  deploy-time-missing but allowlisted theme file needs a proxy/mock the project does not otherwise
  use); the query-param path IS tested. Controller read the shipped code and confirmed the handler.
  NOTE FOR TASK 16: frontend/testpattern.html will need the same double-quoted font-family fix.

Task 15: operator UI (commit 1b8d840, 156 tests) — frontend/operator.html, static/operator.js,
  static/operator.css, tests/test_operator_ui.py, shipped verbatim from the brief. Review found two
  Importants, both in plan-mandated code; fix round dispatched for the first.
  Reviewer resolved the two questions I flagged: (a) the hide/unhide TOGGLE is ONE action, not two —
  spec 8 says verbatim "hiding is the same mechanism, just another flag"; the entry has exactly one
  <button class="hide"> and the test asserts button count == hide-button count; (b) the fetch-mock
  defect the implementer fixed with `; void 0;` is REAL — the reviewer reproduced it independently
  against this venv's Chromium (Playwright's page.evaluate invokes a function-valued completion value
  with no args, so the mock threw TypeError on `.body`). Plan synced.
  OPEN QUESTION FOR BIRK (does NOT block; keeping the plan's version and continuing):
    The brief mandates two PASSIVE readouts the spec's own enumeration does not list — an #stt
    connection badge and an #interview running indicator. Spec 3's architecture sketch says
    "operator UI: transcript / slider / hide" and the Global Constraint says the page has EXACTLY
    those elements. The readouts write nothing (they only render `state`), the brief's tests require
    them, and an operator with no STT indicator cannot tell a dead transcription feed from a quiet
    room — so I kept them. Say the word if you want them gone; it is a small deletion plus two tests.
  Controller-resolved ⚠️: the reviewer noted min_mentions is never applied server-side in
  kg/export.py. That is CORRECT BY DESIGN — spec 7 makes the dial a pure BROWSER display filter
  (Task 13's visibleGraph); graph.json ships every node plus the min_mentions value and the browser
  filters. Do not "fix" export.py to filter.
  Minor CARRIED: the "STT" badge label is an untranslated English acronym (defensible as a technical
  abbreviation; "Transkription" would be fully German).

Task 16: legibility test pattern (commit 8915090, review Approved — one Important, fix dispatched).
  frontend/testpattern.html, frontend/static/theme-d.css, /testpattern route in kg/server.py,
  tests/test_testpattern.py. 162 tests. 11-step monotonic greyscale wedge (true black legitimate HERE
  as the measurement reference — it is the whole point of the page) + 7-rung font ladder
  (14/18/22/26/30/36/44) with a real project term. Reviewer checked the page's own box model
  (~735px of content in a fixed 1080px body) to confirm the no-overflow assertion is a real trap.
  Implementer fixed a real brief inconsistency: Step 3's HTML duplicated base.css's four
  declarations inline while never linking base.css, which Step 4's prose assumed. Plan synced.
  The second claimed "defect" (single-quoted 'Times New Roman') is NOT one: in a real <style> block
  single and double quotes are equivalent. The JS-string trap is real only where a CSS custom
  property is forwarded into a cytoscape style object (projection.js's cssVar('--label-font')).
  Change kept as harmless consistency.
  Important, fix dispatched: /testpattern had NO server-level test — tests/test_testpattern.py loads
  the static file directly, bypassing FastAPI, so the one production line this task adds to
  kg/server.py shipped unverified (its /projection and /operator siblings both have status assertions).
  Minor CARRIED: at the 50%% wedge step the label is white on rgb(128,128,128) — the lowest-contrast
  rung on the ramp (inherited from the brief, not introduced).

Task 17: core wiring + entrypoint (commit 561bf0f, 173 tests) — kg/core.py, kg/__main__.py, plus an
  open_since param on SessionTracker. REVIEWED ON OPUS (integration keystone: crash recovery + the
  serial-interview guarantee live or die here). Fix round dispatched for 4 of 5 Importants.
  Implementer found a REAL defect in the brief's own Core.__init__: SessionTracker was never resumed
  from store.open_person(), so a crash mid-interview plus restart left TWO interviews open — the
  pre-crash person would sit with stopped_at IS NULL forever, invisible to every code path (
  open_person() ORDER BY started_at DESC returns the NEW one). Fixed and plan-synced.
  Reviewer CONFIRMED, by inspection of the wired modules: the catch-all around process_interview is
  genuinely there and sets "failed" AND re-broadcasts on both paths; no Store.transaction() is ever
  held across an LLM or embedding call (decide_merges and build_candidates both complete BEFORE the
  transaction opens); _handle/_open/_close contain no await, so no loop callback can interleave
  between a tracker mutation and its store write; set_setting_default keeps an operator-set
  min_mentions across a restart; anthropic 0.121.0 does not raise on a missing key at construction,
  so the --no-stt --no-telegram smoke path really does start without credentials.
  Four Importants sent to the fix round (brief: .superpowers/sdd/task-17-fix-brief.md):
    1. The resume covers ONLY the open state. A person closed-but-unprocessed, or dead mid-
       "processing", is stranded FOREVER and INVISIBLY — build_graph does not export person.status
       and current_state reports only the open interview, so the operator sees a portrait with no
       terms and no error. Trigger is mundane: laptop shut down after the day's last interview, or
       the kiosk auto-restart firing during a pipeline. Replay needed add_quote dedup (the carried
       item — now CLOSED by this fix) and a decision on record_merge_decision replay.
    2. Two pipelines can run CONCURRENTLY (one background task per close, no serialisation) over the
       EmbeddingCache's own unlocked sqlite connection. Either it throws and the visitor's interview
       is marked "failed", or worse it does not: both merges decide against a term snapshot the other
       thread is mutating, creating near-duplicate nodes no later merge will revisit.
    3. write_graph_json's fixed graph.json.tmp now has genuinely concurrent writers from three
       threads (pipeline, event loop, Starlette threadpool). The dial turned mid-pipeline can produce
       an interleaved file. HTTP /graph.json is unaffected (it rebuilds from the store); the on-disk
       file is Tool 2's interface and the crash artefact.
    4. No shutdown path: drain() never called, PTB never stop()/shutdown()-ed, store never closed,
       and an in-flight _process cancelled with CancelledError is NOT caught by `except Exception`,
       so the "failed" fallback does not run either.
  DEFECT FOUND (tail_seconds) — RESOLVED BY BIRK, see Task 17b below:
    cfg.tail_seconds (default 120 s) NEVER CAPTURED ANYTHING in live operation. process_interview
    cut text_between(started_at, stopped_at + tail_seconds), and spec 6.1 wanted a generous tail so
    the LLM can find the real end and a forgotten stop is harmless — but _close schedules the
    pipeline IMMEDIATELY at the stop instant, so the log holds nothing past stopped_at. The tail was
    empty by construction. Tests never caught it because test_pipeline pre-populates the log.

Task 17b: tail_seconds removed, settle delay on the telegram path only
  (commit f311f29 + doc-sync, 181 tests passing). kg/config.py, config.example.toml, kg/pipeline.py,
  kg/core.py, tests/test_{config,pipeline,core}.py. Reviewed by the controller (opus) directly —
  async timing on the core interview path is where a bug is invisible.
  DECISION BY BIRK (2026-08-14), binding. He REJECTED the first proposal (keep the tail, add a
  settle delay on all paths); this is the revised decision and it is what shipped:
    D3a REMOVE tail_seconds ENTIRELY — dead configuration that pretends to solve a problem it does
       not solve. On the timeout path a tail is MEANINGLESS: the timeout is ALREADY an arbitrary
       cut, so adding 2 minutes just moves the arbitrary cut later. If 15 minutes is too short the
       honest fix is to raise interview_timeout_s, not to append a tail.
    D3b SETTLE DELAY ON EXACTLY ONE PATH, because the only real issue is STT DELIVERY LATENCY, not
       doubt about end-detection:
       - spoken stop  -> IMMEDIATE. The command arrived AS a transcript final, so by construction
         every earlier utterance has already been delivered (finals are ordered). Waiting gains
         nothing.
       - timeout      -> IMMEDIATE. 15 minutes have passed; nothing is in flight.
       - telegram text-> wait UP TO 3 s, but proceed AS SOON AS a final arrives whose timestamp is
         after the stop marker (typically ~1 s). NOT a fixed 3 s sleep. This is the one path where
         a human keypress races an utterance still inside ElevenLabs' server VAD.
       - new_photo    -> IMMEDIATE (explicitly out of scope for this decision).
    D3c The LLM end-detection in the extraction call STAYS. Unaffected, and it still earns its keep
       (e.g. small talk after the interview but before someone stopped).
  Shipped shape: kg.core.SETTLE_TIMEOUT_S = 3.0 / SETTLE_POLL_S = 0.1 and the module-level coroutine
  settle_cut_end(transcript_log, stopped_at, timeout, poll_interval) -> float. It POLLS THE LOG, not
  an in-memory final counter: the log is exactly what text_between will read, so waiting on the log
  is what guarantees the data is there to be cut (a callback signal can run ahead of the file write).
  Core.__init__ gained settle_timeout_s/settle_poll_s — code-level knobs and TEST SEAMS, deliberately
  NOT config-file keys (this task removed a config key; it must not trade it for another).
  Core._close now passes transition.reason into _process, which settles only on "text" and hands
  process_interview a keyword-only cut_end (default None -> stopped_at).
  Per docs/stt-contract.md a final's timestamp is WALL CLOCK AT PUBLICATION (on_committed_transcript),
  not the utterance start — which is why the racing final lands AFTER the stop marker and the cut end
  must move to it. Bounded by 3 s; not a tail.
  8 new tests, all three paths covered: the telegram path captures a final appended 0.05 s after the
  stop marker (cut_end == 200.6, and it returns early rather than sleeping out the window); the
  telegram path falls back to stopped_at when nothing arrives; the spoken and timeout paths are
  each proven NOT to wait by giving them settle_timeout_s=5.0 and asserting elapsed < 1.0 s.
  Plan synced (Task 1 config block, Task 11 pipeline block + interface line + tests, Task 17 Core
  block + interface line); the plan's kg/core.py, kg/pipeline.py and kg/config.py blocks all diff
  byte-for-byte against the shipped files (controller-verified). Spec synced: §5 gained the
  "Settle delay — only on the text-message path" block, §6.1 step 1 no longer says "generous tail".
  Minor CARRIED TO FINAL REVIEW: if a NEW photo opens the next interview within the 3 s settle
  window and that visitor speaks immediately, settle_cut_end could return their final's timestamp
  and drag a fragment into the previous interview's cut. Needs a photo + speech inside 3 s of a text
  stop; the LLM end-detection is exactly the guard for trailing non-interview content.

Task 20: pre-render comparison series A-D (commit 7528753 + nit fix, 188 tests) — sim/__init__.py,
  sim/seed_graph.py, sim/prerender.py, tests/test_seed_graph.py, tests/test_prerender.py.
  RUN OUT OF ORDER, AHEAD OF TASKS 18 AND 19, on Birk's instruction (2026-08-14): he needs the
  series urgently and the weekly token budget is tight. TASKS 18 AND 19 ARE STILL OPEN — do not
  read this ledger as "the simulation exists".
  DECISION BY BIRK, binding: Task 20 must NOT depend on the simulation. The graph state is built
  DIRECTLY THROUGH THE STORE — ~50 person nodes plus terms, realistic long German term labels, a
  realistic edge distribution, portraits substituted by placeholder images. Rationale: the point of
  the series is legibility, stroke weight and black level on a whiteboard, which needs realistic
  DENSITY and LABEL LENGTHS, not real LLM extraction. Spec 10.4 amended (it had said "fed by real
  graph states from the simulation, not fixtures"); plan's Task 20 rewritten to match.
  sim/seed_graph.py: 100 curated German labels (Bauwende / Stadt der Zukunft), list order IS the
  Zipf popularity ranking (weight 1/(i+1)**0.85), 4-6 terms per person drawn weighted-without-
  replacement, only drawn labels get a term row (a zero-mention term is a node the live system
  cannot produce). Placeholder photos are generated with PIL and pushed through the REAL
  kg.photos.make_portrait, so the wall sees production-shaped portraits. Deterministic:
  one random.Random(seed), a fixed epoch base, never time.time().
  Delivered shape at persons=50, seed=20260814: 50 persons, 75 distinct terms, 253 edges, 25 terms
  mentioned exactly once. Render wall-clock ~62 s.
  Controller fix after review: close_person used reason="stop_phrase", which kg.session can never
  emit (text/spoken/timeout/new_photo) -> "spoken", re-seeded and re-rendered.
  ARTEFACTS (git-ignored, regenerable): out/prerender/{a,b,c,d}.png, all verified exactly 1920x1080.
  FINDINGS FOR BIRK'S WHITEBOARD DECISION (spec 10.3's three named outcomes):
  - At fit-all with 50 persons the labels OVERLAP HEAVILY and are small in all three themes. This
    is the empirical answer the series existed to produce: outcome (1) "everything is sensibly
    displayable at once" does NOT hold at this density. Zoom (2) or auto-pan (3) will be needed.
    The camera already supports all three modes — this is a setting, not a rebuild.
  - The graph occupies only the middle ~55% of the 1920px width; the fit leaves large empty side
    margins. Widening the fit would buy real label size for free. Worth checking before the event.
  - The colourful discs are PLACEHOLDER portraits, not photographs. Real portraits will be
    photographic and mostly mid-tone, so judge the black level from theme D's wedge, not from them.
  Known deviation, NOT fixed (would cost a re-render for no gain to what the series measures): the
  Zipf exponent the controller specified made the head too hot — the top term landed at 33/50
  mentions (66%) where real interviews would give high teens. Distinct-term count, edge count and
  the singleton tail are all realistic; label lengths and density are what the series measures, and
  those are right. Lower the exponent if the seed is ever reused for anything mention-count-sensitive.

Task 18: synthetic interview corpus and expectations — BLOCKED, partial.
  `sim/generate_interviews.py` and `tests/test_sim_generator.py` implemented per plan Step 3/Step 1
  verbatim (plus the `--model` CLI arg / `DEFAULT_GENERATION_MODEL` / `"model"` payload key mandated
  by Birk's binding decision, 2026-08-19: corpus generation runs on **claude-sonnet-5**, not the Opus
  `cfg.llm_model` default used for real extraction/merge-judge calls). 8 tests passing (7 from the plan
  + 1 asserting the `--model` default is `claude-sonnet-5`, permitted by controller resolution 5).
  Found and fixed a real bug in the plan's own Step 3 code block: the Füllwörter/planted-phrasing
  string literals pair the German opening quote „ (U+201E) with a straight ASCII " as if it were the
  closing quote, inside an ASCII-`"`-delimited Python string — transcribed verbatim this is a
  SyntaxError, not valid Python. Fixed by using the correct German closing quote U+201C " instead of
  the stray ASCII ", preserving the load-bearing typographic-quote intent. No test depends on which
  quote character is used (only content substrings are asserted), so this had no effect on the test
  suite; flagging for whoever maintains the plan since transcribing it literally reproduces the bug.
  Fixed the `.gitignore` trap (deliverable 5): line 4 was the bare pattern `data/`, which git matches
  at any depth, so it was silently swallowing `sim/data/` along with the intended top-level runtime
  `data/`. Anchored it to `/data/`. Verified with `git check-ignore -v` on probe files: `sim/data/`
  interviews and expectations.yaml are NOT ignored, `sim/data/runs/` still IS (its own rule, line 7,
  unchanged), and top-level `data/` is still ignored. Probe files removed after verification.
  BLOCKER: `ANTHROPIC_API_KEY` is exported in this execution environment but EMPTY (0 characters, not
  merely unset) — verified via `printenv | wc -c`, Python `os.environ`, and a live `anthropic.Anthropic`
  client call, which fails with `TypeError: Could not resolve authentication method`. `kg.config.
  load_config()` sources the key only from `os.environ.get("ANTHROPIC_API_KEY")` (kg/config.py:115),
  so there is no other path to a working credential inside this environment. Did NOT read
  `~/.hermes/.env`, did NOT fabricate a key or fake transcript text. Consequently the 60 generated
  fixtures under `sim/data/interviews/`, `sim/data/expectations.yaml`, the Step 5 speech-vs-prose
  quality gate, and the cost estimate could not be produced. Deliberately did NOT generate
  `expectations.yaml` standalone (it is pure/deterministic and could have been produced without any
  LLM call) — doing so ahead of the corpus it describes would be a partial artefact masquerading as
  done. NOTHING COMMITTED: `sim/generate_interviews.py`, `tests/test_sim_generator.py` and the
  `.gitignore` fix sit as verified, passing, uncommitted working-tree changes. Needs either a working
  `ANTHROPIC_API_KEY` in this environment, or the Step 5 generation run from a context that has one.
  Full suite run once regardless (code/tests don't depend on the key): 250 passed, 1 warning
  (pre-existing httpx/starlette deprecation notice), 1081s — 242 baseline + 8 new
  (tests/test_sim_generator.py). No regressions from the .gitignore change or the new module.
  See `.superpowers/sdd/task-18-report.md` for full evidence.

## Carried to the final whole-branch review (roll-up — triage before merge)
- T1: load_config silently falls back to defaults when the --config path is missing (brief-mandated).
- T4: strip_stop_phrases strips EVERY configured phrase, so the stripped span can exceed the phrase
  find_stop_phrase reports (harmless for the current two-phrase config).
- T7: download OK + make_portrait failure leaves an orphaned raw .jpg on disk (logged, never cleaned).
- T8: LLMClient.parse's `except Exception` retries deterministic failures (schema errors, refusals).
- T8: build_extraction_prompt does not escape the transcript ("--- ENDE TRANSKRIPT ---" collision).
- T10: stray graph.json.tmp can survive a crash mid-write; build_graph is N+1 on mention_count;
  int(get_setting("min_mentions","1")) raises on a non-numeric setting.
- T11: `text[:end].strip() or text.strip()` — interview_end_index 0 falls back to the FULL text,
  defeating end-detection exactly when it fired (bad stored transcript, not a public-wall leak).
- T11: store.add_quote has NO dedup (add_edge has it), so re-running the pipeline for one person_id
  would duplicate quotes. No code path re-runs it today.
- T13: tests/conftest.py's browser fixture catches bare `except Exception` around chromium.launch(),
  so an unrelated launch error (TypeError, transient failure) also routes into the cache-glob branch.
  Low risk (it re-raises when nothing is found), but the intent would be clearer narrowed to
  playwright's own error type.
- T13: no test covers minMentions <= 0 — the one piece of defensive logic in graph-model.js
  (Math.max(1, Number(minMentions) || 1)) has no assertion behind it.
- T13: static_server's background thread is never joined after httpd.shutdown() (untidy teardown,
  harmless at process exit).
- T12b (opus reviewer, deferred by design): kg/export.py build_graph makes ~7+N separately-locked
  Store calls with NO enclosing transaction(), so the composite read is not atomic — an operator
  hitting /api/hidden can interleave list_terms() before and list_edges() after the pipeline commits
  a new term+edge, producing a graph.json whose edge targets a node absent from `nodes`. Not
  corruption (os.replace is atomic, the next broadcast repairs it) but a possible transient renderer
  glitch on the wall. 12b is what makes the natural fix — wrapping build_graph in
  `with store.transaction():` — safe. Consider before the exhibition.
- T12b (opus reviewer, latent): RLock is THREAD-owned. If anyone later opens `with
  store.transaction():` inside a coroutine and awaits within it, other coroutines on the same loop
  thread would re-acquire re-entrantly and silently interleave inside the open transaction. Nothing
  does this today (only two transaction callers, both sync). Guard this in review of any async work.
- T12a: /events' async stream() calls build_graph/current_state on the event-loop thread (plan-mandated;
  negligible at ~50 nodes, but no threadpool hop unlike the sync routes).
- T12a: no test exercises /events itself (streaming body, SSE framing, keep-alive) — inherited gap,
  the brief's prescribed test file covers only the REST endpoints.
- T12a: test output carries StarletteDeprecationWarning ("Using httpx with starlette.testclient is
  deprecated; install httpx2") — dependency pin, not a code defect, but the output is not pristine.
- T12a: frontend/static/vendor/ is an empty UNTRACKED dir — git does not track empty dirs, so the
  vendored Cytoscape drop (Tasks 13-15) must create it.
- T19: the canonical label always renames the winner, so a later group can rename an established
  node into something that no longer describes it (p38 renamed the recycling node to `Vorzeitiger
  Gebäudeabriss`, hiding it from the embedder and costing Recycling-Beton its fourth interview).
- T19: `merge_neighbours=5` is the dominant remaining cause of missed merges (7 of 8 near-misses at
  rank 7-56). Raising it to ~12 needs one more full run to confirm — awaiting Birk's go-ahead.
- T19: extraction labels (kg/pipeline.py:54) are not passed through unquote_label, and
  EXTRACTION_SYSTEM quotes its examples the same way the merge prompt does. Measured 0 occurrences
  in 382 labels across runs 19 and 19b, so prophylaxis rather than a defect.

Task 18: IN PROGRESS — BLOCKED ON CREDENTIALS (commit 3dbc0df, 250 tests passing).
  Code half is DONE and committed: sim/generate_interviews.py, tests/test_sim_generator.py
  (8 tests = plan's 7 + a DEFAULT_GENERATION_MODEL assertion), .gitignore fix, plan synced
  (Step 1 and Step 3 blocks now diff byte-for-byte against the shipped files, controller-verified).
  The 60 fixtures and expectations.yaml are NOT generated — ANTHROPIC_API_KEY is exported but
  EMPTY (0 chars) in this session's environment; no `ant` CLI, no ~/.config/anthropic profile,
  no ANTHROPIC_AUTH_TOKEN, no ANTHROPIC_BASE_URL. api.anthropic.com:443 IS reachable, so the
  network is fine — it is purely a missing credential. Waiting on Birk.
  Generation model per Birk's binding decision (2026-08-19): claude-sonnet-5, effort="medium",
  exposed as --model, recorded in each fixture's "model" field.
  Two real defects found in the plan's own Task 18 code, both fixed and synced:
  - Step 3's build_generation_prompt did NOT PARSE: „also", „ähm", „ne" and the two planted-
    phrasing lines opened with German „ (U+201E) and closed with ASCII " inside a double-quoted
    Python string, terminating the literal early -> SyntaxError. Closed with U+201C.
  - .gitignore line 4 was the bare pattern `data/`, which git matches at ANY depth, so the entire
    corpus under sim/data/ was silently ignored — exactly the trap the brief warned about (the
    brief's own description of the trap was wrong: it said only sim/data/runs/ was ignored).
    Anchored to `/data/` (the live runtime state dir at the repo root); sim/data/runs/ still ignored.
    Verified with git check-ignore -v on all four paths.
  NOT yet done, all blocked on the key: 60 fixtures, expectations.yaml, the speech-vs-prose
  quality gate on three transcripts, the cost figure, the task review.

Task 18: complete (commits 3dbc0df + d8c1f33) — sim/generate_interviews.py, tests/test_sim_generator.py,
  sim/data/interviews/*.json (60), sim/data/expectations.yaml. 250 tests passing (242 baseline + 8 new).
  DECISION BY BIRK (2026-08-19), binding: corpus generated on SONNET (claude-sonnet-5, effort=medium),
  not Opus. Rationale: writing synthetic spoken German does not need Opus reasoning, and 60 Opus calls
  is a large slice of the weekly budget for a fixture set. Extraction and merge-judge in Task 19 stay
  on Opus, where model quality decides the outcome. Exposed as --model, not hardcoded; the model id is
  recorded in each fixture's "model" field.
  TWO REAL DEFECTS IN THE PLAN'S OWN TASK 18 CODE, both found by the implementer and fixed:
  (a) Step 3 did not parse. The generator prompt's German quotes open with „ (U+201E) but closed with
      ASCII " — inside a double-quoted Python string that terminates the literal early (SyntaxError for
      anyone transcribing the block literally). Closed with U+201C, plan synced byte-for-byte.
  (b) .gitignore line 4 was the bare pattern `data/`, which git matches at ANY depth — so sim/data/ and
      the entire corpus were ignored, not just sim/data/runs/. Proven with `git check-ignore -v`.
      Anchored to `/data/` (the runtime state dir at repo root). Without this the 60 fixtures would have
      existed locally and vanished on the next clone.
  CREDENTIALS — worth knowing for Task 19: this box has NO ANTHROPIC_API_KEY (the .env entry is empty).
  It runs against Birk's local Anthropic subscription proxy at http://127.0.0.1:28764, so the generator
  is run with ANTHROPIC_BASE_URL pointed at it and a dummy key the proxy ignores. Costs go against the
  subscription, not API credit.
  PITFALL, cost one failed turn: do NOT export ANTHROPIC_BASE_URL into the shell that launches Claude
  Code itself — the agent's OWN requests then route through the proxy, which rejects them with
  "400 context_management: Extra inputs are not permitted". Set it only for the generator subprocess.
  The generator is a deterministic script and needs no agent at all; running it directly is the right
  call and avoids the whole class of problem.
  QUALITY GATE performed for real (plan Step 5). Sample, fixture 000 (speaker "sehr knapp, zwei Sätze,
  fast unwillig", planted "Roboter auf der Baustelle"):
    "ähm ja weniger von Hand gemacht würd ich sagen also so Maschinen die den Beton selber aufsprühen
     so Drohnen halt das wär mir schon wichtig ne. mehr will ich dazu eigentlich gar nicht sagen."
  Reads as speech, not prose: filler words, no sentence punctuation, run-on structure. Fixture 017
  (polemic) carries 12x "äh"/7x "also"; fixture 044 (Fachjargon) 8x "also"/6x "äh" with real planning
  vocabulary. Lengths 183–4991 chars, median 1801 — the speaker-type spread is genuinely there.
  CORPUS SHAPE VERIFIED beyond the tests: 20 of 60 fixtures carry a planted overlap (1/3, as designed),
  5 concepts x 4 interviews each, 3 distinct phrasings per concept, and NO fixture contains its own
  concept term verbatim — so Task 19's merge scoring cannot be passed by naive string matching.

Task 19: replay harness + the quote fix + calibration run 19b — DONE (commits 83b3008, 1016421;
  261 tests passing, full suite 18m39s). Harness committed as written: `sim/replay.py`,
  `tests/test_replay.py` (7 tests), plan synced.
  THE BUG (diagnosed in `.superpowers/sdd/task-19-rootcause.md` from run 19's own db, not re-derived):
  `build_merge_prompt` renders labels as „Label“, the model echoes the quote characters back inside
  `group.members`, `apply_merges` looked them up verbatim, matched nothing, created a duplicate term
  for the canonical label and left every real term unmerged. Every merge was logged and none applied.
  FIX: `kg.merging.unquote_label` — one normalisation used for BOTH the lookup and the alias write, so
  detection and storage cannot diverge (same lesson as Task 4's stop-phrase bug). Not "stop quoting in
  the prompt": the quotes disambiguate multi-word labels and the model may quote regardless.
  TDD ORDER VERIFIED EXPLICITLY: the two regression tests were run against the unmodified
  `apply_merges` first and failed with the bug's exact signature (`assert 2 == 1`, two terms surviving
  where one was decided; `assert 3 == 1` with a literal `„Ländlicher Leerstand“` term created), then
  passed after the fix. Edge case found while fixing: a canonical label of only quotes strips to "" —
  the group now falls back to naming itself after its first member instead of creating a term named "".
  RUN 19b (out/sim19b/sim.db, defaults, 60/60 interviews `done`, no failures): score 0.2 (1 of 5), NOT
  the "high" the root-cause doc predicted. The fix is verifiably live — **0 of 269 aliases carry „…“
  where run 19 had 100 of 368**, and 170 terms instead of 212 from the same corpus (42 folds that
  previously did nothing). Singletons 126/170 (74%), was 183/212 (86%). 4.35 terms/interview, 261
  edges, 88 groups decided across 60 merge calls.
  THE REMAINING CAUSE IS PRESELECTION RECALL, NOT THE JUDGE. In 7 of the 8 near-misses the concept's
  own node was in the pool but at rank 7, 10, 11, 14, 20, 31, 56 — outside `merge_neighbours=5`, so
  the judge never saw it. Exactly one miss (`Mauerroboter` → `Betonsprühende Drohnen`, rank 1) was the
  judge declining under the current merge_style, where a bricklaying robot arguably IS a different
  thing from a spraying drone. One further miss is not a merge failure at all: p34's planted phrasing
  came out of extraction as `Investorenmacht am Planungstisch`, the inverted framing — the concept was
  gone before merging ran.
  NEW DEFECT FOUND, NOT FIXED (needs a design decision, not a dial): the canonical label always
  renames the winner, so a later group can rename an established node into something that no longer
  describes it. p38 merged the new `Vorzeitiger Gebäudeabriss` into the recycling node
  `Abbruchschutt als Wandmaterial` and renamed it — stripping the node of its recycling identity for
  both the wall and the embedder. p52 then found `Bauteilrecycling` (rank 1) instead of the old node
  (rank 14), and Recycling-Beton lost its fourth interview.
  CALIBRATION written into `config.example.toml` naming run 19b: `default_min_mentions` 1 → **2** (the
  one value this run determines outright: 44 shared terms on the wall instead of 170 with 126
  singletons; the `Config` dataclass default stays 1, which test_config.py pins);
  `terms_per_interview` stays 5 (the model self-limits to 4.35, so the cap is not the density lever);
  `merge_style` unchanged (only 1 of 8 misses was the judge's call — loosening it would also loosen
  the 49 of 60 interviews it currently gets right). `merge_neighbours` left at 5 with the rank
  evidence written in as a comment: raising it to ~12 is the change with the clearest evidence and is
  nearly free (embeddings cached), but it is a THIRD full run — asked Birk rather than spending it.
  Full evidence, quoted decisions and alias rows per failed concept: `.superpowers/sdd/task-19-report.md`.

Task 19: complete (commits 83b3008, 1016421, 09b8b6b + this one) — sim/replay.py, tests/test_replay.py,
  kg/merging.py, kg/store.py, kg/config.py, config.example.toml. Three full 60-interview runs.

  RUN 19a (defaults): score 0/5, 212 terms. NOT a model problem — a string bug.
    build_merge_prompt renders labels as „Label“; the LLM echoes members back WITH the quote
    characters; apply_merges looked them up verbatim against unquoted stored labels, never matched,
    and created a duplicate term instead of folding. The decision was logged and changed nothing.
    Proof from out/sim19/sim.db: alias „Zugepflasterte Landschaft“ -> t50 while the real term
    Zugepflasterte Landschaft lived on as t170. Embedding preselection was measured separately and
    was fine (target at rank 1 in 5 of 7 probes, e.g. Gemeinschaftlicher Hausbesitz -> Gemeinsamer
    Hausbesitz cos 0.934); the judge decided correctly in 51 of 60 interviews. Fixed in 1016421 by
    normalising the model's strings ONCE, for both lookup and alias write, so detection and storage
    cannot diverge (same failure class as Task 4's stop-phrase bug).

  RUN 19b (after the quote fix): score 1/5, 170 terms. Exposed a REAL design defect:
    the canonical label ALWAYS renamed the winner, so one mediocre naming choice could hijack a grown
    node. Observed: p7+p22 had built „Baustoff mit Geschichte“; interview 037 correctly merged
    „Wiedereinbau von Abrissmaterial“ into it and renamed the node to „Vorzeitiger Gebäudeabriss“ —
    close to the opposite meaning, on the wall, at 4 mentions. Because the label is also the
    embedder's text for that node, p52 then matched Bauteilrecycling (rank 1) instead of the
    established node (rank 14): a bad rename both misrepresents a node AND blocks further
    consolidation.

  DECISION BY BIRK (2026-08-19), binding — D5: A TERM'S LABEL IS FROZEN once a SECOND distinct person
    has mentioned it. While a term belongs to one person an unlucky first name may still be corrected;
    after that the name is public property. Chosen over "freeze always" and "leave as is" because it
    fixes exactly the observed damage while still allowing an early correction.
    Implementation: the gate sits in Store.rename_term, next to the write, so no caller can bypass it.
    ORDER MATTERS and is pinned by a test: apply_merges measures mention_count BEFORE folding the
    losers and passes it in as mentions_before_merge — after the fold the winner's count already
    includes the losers' persons, which would refuse a rename that was legitimate when the judge made
    it. Merge and naming are ONE decision, not two. A refused rename never aborts the merge: the fold
    happens, and the rejected canonical label is still written as an alias, so a future interview
    phrasing it that way still lands on the node.

  RUN 19c (D5 + merge_neighbours 5 -> 12): score 2/5, 163 terms, 267 edges, 0 failed interviews.
    D5 VERIFIED IN THE RUN DATA, not just in tests: no node carries a name from a merge decided after
    it reached 2 mentions. The Recycling node kept a sane identity this time — „Wiederverwendeter
    Abbruchschutt“ at 5 mentions, aliases [Beton aus Abbruchmaterial, Recycelter Beton,
    Wiederverwendung von Abbruchmaterial, Bauschutt neu anmischen]. Ländlicher Leerstand and
    Genossenschaftliches Wohnen now score; Roboter/Recycling/Bodenversiegelung consolidated
    substantially without reaching a single node.
    5/5 was explicitly NOT the target: run 19b's probes showed genuine semantic distance in the
    residue (3D-Drucker vs Betonsprühende Drohnen cos 0.389; one candidate at rank 56), which a wider
    window cannot fix and which inflating merge_neighbours further would only paper over with noise.

  CALIBRATED VALUES (config.example.toml, naming run 19c):
    terms_per_interview = 5   (the model self-limits to ~4.4 against this cap; lowering trims good terms)
    merge_neighbours    = 12  (19b: in 7 of 8 near-misses the right node sat at rank 7-56, unseen)
    merge_style         unchanged (only 1 of 8 near-misses was the judge's decision; loosening it would
                                   also loosen the ~50 of 60 interviews where it currently decides well)
    default_min_mentions = 2  (19c: 163 terms, 114 singletons; at 2 the wall shows 49, all shared; at 3, 26)

  INFRASTRUCTURE NOTE: run 19c died once mid-run with sqlite3.OperationalError "database or disk is
    full" — / was at 99%. Not a code fault. Freed 2.3GB (npm + uv caches) and re-ran. /var/log holds
    3.0GB and is root-owned: an admin step, already in docs/root-cause-backlog.md (2026-08-10).

  CARRIED TO FINAL REVIEW: kg/pipeline.py extraction labels carry the same latent quote-echo risk
    (EXTRACTION_SYSTEM quotes its examples too), but 0 of 382 labels across the runs contained a quote
    character, so it was left unfixed rather than widening the change. Run 19a produced one label
    literally called ".text" (a field name leaked into a label); it did not recur in 19b/19c.

Task 21 + 21b: complete — tests/test_resilience.py, scripts/start.sh, docs/operations.md,
  kg/server.py, frontend/operator.html, frontend/static/operator.js, frontend/projection.html,
  tests/test_server.py, tests/test_operator_ui.py. 277 tests passing (was 269).
  RUN BY THE CONTROLLER DIRECTLY, not delegated: the delegated Claude Code run died on the very
  first step with "You've hit your monthly spend limit" (session f0a18fa8), producing no commit and
  no file. Cost $1.63 for nothing.

  PLAN CORRECTION — SessionTracker.adopt() and Core.recover() were NOT built, deliberately.
    The plan's Task 21 Steps 3 prescribes both plus a call in __main__.py. They are redundant: Task
    17's implementer already found the same defect in the plan's Core.__init__ (a crash mid-interview
    plus restart left TWO interviews open) and fixed it AT CONSTRUCTION TIME — Core.__init__ reads
    store.open_person() and seeds SessionTracker(open_since=...). Five of the six resilience tests
    passed on first run against unmodified code, which is the evidence. Building recover() anyway
    would have created a SECOND path for one notion — the exact shape of Task 4's stop-phrase bug,
    where a duplicated notion of "separator" diverged and leaked a command into the LLM call.
    The test therefore asserts the BEHAVIOUR (tracker.open_since is adopted; the interview can still
    be closed and processed after a restart), not the prescribed method name.
    The sixth test failed only because the test's own processor stub lacked the keyword-only
    `cut_end` parameter that process_interview grew in Task 17b. Test fixed, not production code.

  Task 21b — camera zoom exposed in the operator UI (Birk asked for it after D4).
    Motivation: D4 says zoom is set on site, but Camera.setZoomFactor was reachable ONLY through the
    constructor — not in the state payload, not in projection.html's state branch, not in the
    operator UI. Without a touchscreen at the projection machine an operator could not zoom AT ALL.
    Shape: a `camera_zoom` setting in the Store, carried in current_state(); POST /api/camera_zoom
    bounded to [1, 4]; a select in operator.html (1x / 1.5x / 2x); projection.html applies it in the
    same state branch as setMode, guarded (`if (zoom >= 1)`) because setZoomFactor throws below 1 and
    an exhibition wall must degrade rather than stop rendering.
    Bounds are not arbitrary: below 1 the camera shows LESS than the net without filling the wall
    (and Camera throws); above 4 a stray value would zoom the unattended wall into a single node.
    Tests pin the rejections AND that a rejected write does not move the stored value.
    Against spec §7 ("exactly one runtime dial"): §7 governs controls that change EXTRACTION or
    MERGING. The camera mode select was already a display-only control alongside the density dial;
    the zoom select is the same class, not a second dial.

  scripts/start.sh — two deliberate deviations from the plan's template:
    (a) the fixed `sleep 8` before launching the browsers is replaced by a real readiness poll against
        /api/state (60x1s). A slow first start would otherwise open BOTH windows on a connection error
        — on the exhibition day, in front of visitors.
    (b) added a cleanup trap killing the process group: without it the restart loops survive Ctrl-C
        and keep respawning chromium.
    Also parameterised the beamer position (KG_PROJECTION_POS) — 1920,0 only holds if the beamer sits
    to the right of a 1920-wide laptop panel.

  docs/operations.md — carries the REAL calibrated values from run 19c, no placeholders. Every claim
    was checked against the code before writing it: --no-telegram/--no-stt exist in __main__.py, and
    the documented "zoom does not re-frame in manual mode" is what camera.js actually does (manual is
    the visitor's mode; re-framing would fight their hand). The touchscreen is documented as CONFIRMED
    (spec §14.3 closed as YES) but the verification commands are KEPT — confirmed-on-paper is not
    working-on-the-day. The merge score is presented as a state of affairs, not a defect: the wall
    shows two related nodes instead of one for three of five planted concepts, which is the honest
    outcome at genuine semantic distance.

  BRIEF CHECK ANSWERED: docs/operations.md documents nothing that cannot be reached from the operator
  UI. That check is exactly why 21b exists — before it, the runbook would have had to describe zoom as
  "touch the projection machine".


===== TOOL 2 (Kollektivtraum) =====
Plan: docs/superpowers/plans/2026-08-25-kollektivtraum-tool2.md (18 tasks)
Branch: tool1-implementation (same branch as Tool 1; not master)
NOTE: no ANTHROPIC_API_KEY / OPENROUTER_API_KEY in this environment. Every task
  builds and tests offline; the real-API steps (Task 8 probe, 15, 16, 17 --generate)
  are flagged for Birk to run.

Task 1: complete (commits 1673e2e..d2d4e34, review clean after 3 fix rounds).
  Spec §3.1 corrected with a dated note in BOTH specs — server_host was already
  LAN-bindable; the spec's claim that it "must become" so was wrong.
  Only kg/__main__.py touched under kg/, as the plan's Global Constraints require.
  THREE REAL DEFECTS in the plan's own prescribed code, all found by review:
   1. resolved_host fell back to 127.0.0.1 when the UDP route probe failed,
      justified by the false claim that "no default route means unreachable".
      An isolated exhibition LAN with static IPs and no gateway has a fine
      address and no default route — the fallback reproduced the exact
      unopenable URL the function exists to prevent.
   2. The first fix (gethostbyname_ex) was a NO-OP on Debian-family hosts:
      /etc/hosts ships `127.0.1.1 <hostname>` and assigning a static IP never
      updates it, so it returns only loopback. Reviewer verified this
      empirically on this very box. Real fix: `ip -4 -o addr show scope global`
      as a subprocess (2 s timeout), which is what the runbook already tells the
      operator to type by hand.
   3. subprocess.run(text=True) decodes strict; UnicodeDecodeError is a
      ValueError and was caught by neither `OSError` nor `SubprocessError`, so a
      non-UTF-8 locale would crash an unattended startup. Fixed with
      errors="replace".
  Chain is now: UDP route probe -> `ip ... scope global` -> gethostbyname_ex ->
  127.0.0.1, total, never raises. Verified by hand end to end.
  Minor findings NOT fixed, carried to the final review: `::` takes the IPv4
  path (never produced by this codebase); the new console line mixes an English
  label with a German parenthetical (matches the two lines beside it).
  tests/test_dream_bind.py: 11 passing. Tool 1 regression: 251 passing.

Task 2: complete (commit 835560f, review clean first pass).
  kg2/__init__.py, kg2/config.py, config2.example.toml, tests/test_dream_config.py;
  pyproject.toml gains packages=["kg","kg2"], .gitignore gains dream-data/.
  Separate config file, NOT a section in Tool 1's config.toml — Tool 2 runs on
  its own machine, so a shared file would describe a sharing that does not exist.
  Reviewer verified by probe that a config2.toml containing anthropic_api_key
  cannot override the environment: _FIELD_NAMES filters it out before the
  constructor, so file-based credential injection is impossible. _FIELD_NAMES was
  also diffed programmatically against dataclasses.fields(DreamConfig) — the only
  omissions are data_dir (handled specially) and the two key fields (deliberate).
  server_port=8810 deliberately, so both tools can run on one box during dev.
  DEFAULT_GUIDING_QUESTION / DEFAULT_VISUAL_REGISTER are intentional placeholders
  Birk replaces from the artefacts built in Tasks 15/16 — not unfinished work.
  Minor NOT fixed, carried to the final review: unused `import pytest` in
  tests/test_dream_config.py (came from the plan's own test code).
  Note: frontend2/static deliberately not created here — Task 10 creates it.
  tests/test_dream_config.py: 6 passing. Tool 1 spot check test_config.py: 4 passing.

Task 3: complete (commit 8b521f8, review clean first pass).
  sim/data/graph-19c.json (REAL sim/replay.py run-19c artefact, counts verified
  60/163/267/117 before copying), its provenance doc, kg2/graph_client.py, and
  tests/test_dream_contract.py; tests/conftest.py gains the `real_graph` fixture.
  Reviewer confirmed the drift guard is NOT vacuous: type_map collapses 223 nodes
  /267 edges/117 quotes to 18 path entries, and the fixture-vs-live comparison
  uses set(type_map(...)) — PATH NAMES only — so the legitimate difference
  between the fixture (every x/y null, nothing hidden) and live_graph (placed
  nodes, a hidden term) cannot produce a false positive. Type-level protection
  comes from the two REQUIRED-vs-{fixture,live} tests instead.
  Spec §13 properties 1-4 pinned here; property 5 (broadcast_graph fires AFTER
  the pipeline) is a timing property and belongs to Task 5's trigger tests.
  THREE Minor limitations recorded, none fixed, all carried to the final review:
   1. type_map has a blind spot for a field that is sometimes an object and
      sometimes null — it would emit two disjoint paths. kg.export.build_graph
      emits only flat scalars today (verified), so it cannot misfire yet.
   2. fetch_graph's _REQUIRED_KEYS guard checks key PRESENCE, not value types:
      {"version":1,"nodes":"corrupted","edges":[]} passes and is handed on.
      >>> RELEVANT TO TASKS 5/6: make absorbed_persons and build_material
      >>> defensive about node/edge shape rather than trusting the guard.
   3. test_the_graph_client_has_no_way_to_write_to_tool_1 is a substring check:
      httpx.request("POST", ...) or getattr(httpx,"post") would evade it, and a
      docstring merely mentioning ".post(" would false-positive it. It catches
      the casual case, which is what its own docstring claims.
  tests/test_dream_contract.py: 11 passing. Tool 1 spot check: 26 passing.
