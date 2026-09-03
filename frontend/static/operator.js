// One action per entry: hide. No approving, no editing, no queue (spec 8).

import { selectVisibleTermIds } from './graph-model.js';

// The last graph/state a render() call actually received — from the server,
// via /events, not merely attempted. post() reverts to these on failure, so
// this is the exhibition's only feedback for a control the server never
// confirmed (see the catch below): no toast/banner, just the control
// snapping back to the truth.
let lastGraph = { nodes: [], edges: [], quotes: [] };
let lastState = {
  max_terms: 32,
  camera_mode: 'fit',
  camera_min_label: 40,
  camera_speed: 1,
  portrait_size: 120,
  stt_connected: false,
  // Der physische Schalter am Mikrofon (STT-Server, --mic-gate). Default an:
  // eine Station ohne Schalter meldet nie etwas und hat ein offenes Mikrofon.
  mic_on: true,
  // `interview` fehlt hier ABSICHTLICH, und das ist kein vergessenes Feld:
  // Solange der Server nichts gemeldet hat, ist der Zustand unbekannt.
  // `interview: null` hiesse „kein Interview" — eine Behauptung, die den
  // Startknopf scharf stellt, waehrend im Raum vielleicht laengst jemand
  // spricht. Der Server schickt das Feld in JEDER Zustandsmeldung
  // (`current_state`), sein Fehlen heisst also verlaesslich „noch keine
  // Meldung gesehen".
};

function post(url, body) {
  return fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  })
    .then((response) => {
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
      return { ok: true, fehler: '' };
    })
    .catch((error) => {
      // This is the sole human control surface for the exhibition: a write
      // that the server never confirmed must not leave the operator staring
      // at a control showing a change that did not happen.
      console.warn(`request to ${url} failed`, error);
      render(lastGraph, lastState);
      // Der Ausgang wird ZURUECKGEGEBEN, statt nur verschluckt zu werden:
      // Fuer Regler und Ausblenden-Knoepfe reicht das Zurueckspringen als
      // Rueckmeldung, weil man dem Regler ansieht, wo er steht. Der
      // Interviewschalter braucht mehr — sein Ergebnis passiert im Nebenraum
      // — und holt sich hier den Grund fuer seine eigene Meldung.
      return { ok: false, fehler: String(error.message || error) };
    });
}

/** How a person reads in the list. They carry no label — only a portrait and
 * the moment the photo was taken (`created_at`, the interview's start).
 *
 * The portrait is the identification; the time is what tells two portraits of
 * the same room apart, and it is the one thing an operator standing at the
 * station can match against their own clock ("the one from just before three").
 * Hours and minutes, nothing finer: seconds are noise at this resolution. */
function personLabel(node) {
  const seconds = Number(node.created_at);
  if (!Number.isFinite(seconds) || seconds <= 0) return 'Person';
  const time = new Date(seconds * 1000).toLocaleTimeString('de-DE', {
    hour: '2-digit',
    minute: '2-digit',
  });
  return `Person ${time}`;
}

/** The second identifying mark: how many terms hang off this person.
 *
 * "keine Begriffe" is exactly what a test portrait from the morning's setup
 * looks like (nobody spoke to it) — the case Birk could not get off the wall
 * on 2026-08-30. It is also the honest answer while an interview is still
 * being condensed, so it must not read as an error. */
function termCountText(count) {
  if (count === 0) return 'keine Begriffe';
  return count === 1 ? '1 Begriff' : `${count} Begriffe`;
}

/** Die Personenzeile trägt statt eines Labels ein Namensfeld.
 *
 * Der Name kommt aus dem Transkript — die Person stellt sich zu Beginn des
 * Interviews vor — und die Spracherkennung verhört Namen zuverlässiger als
 * alles andere. Korrigiert wird deshalb genau dort, wo die Person in dieser
 * Liste ohnehin identifiziert wird: neben ihrem Porträt.
 *
 * Ohne Namen bleibt das Feld leer und der `placeholder` zeigt weiter die
 * Uhrzeit-Kennung von `personLabel()`. Eine namenlose Zeile bleibt damit
 * genauso wiederzufinden wie vor dieser Änderung („die von kurz vor drei"),
 * und der leere Kasten sagt zugleich, dass hier etwas fehlt, das man
 * hinschreiben darf.
 */
function nameField(node, draft) {
  const field = document.createElement('input');
  field.type = 'text';
  // Behält die Label-Klasse: Das Feld steht an der Stelle des Labels, nimmt
  // dessen Breite in der Zeile ein und wird beim Ausblenden mit durchgestrichen.
  field.className = 'label name';
  field.dataset.nameFor = node.id;
  field.placeholder = personLabel(node);
  field.maxLength = 120; // dieselbe Grenze wie PersonName.name im Server
  // Ein laufender Entwurf schlägt den Servertext: siehe editingDraft() unten.
  field.value = draft && draft.personId === node.id ? draft.value : node.name || '';

  // Gespeichert wird beim Verlassen des Feldes, nicht beim Tippen. `input`
  // würde pro Tastendruck feuern und damit pro Buchstabe eine Graph-Rundmeldung
  // an jeden SSE-Client schicken — dieselbe Überlegung wie bei den Reglern
  // (frontend/operator.html) und mit derselben Antwort: `change`.
  field.addEventListener('change', () =>
    post('/api/person_name', { person_id: node.id, name: field.value.trim() }),
  );
  // Enter heißt „fertig" und wird deshalb genau darauf abgebildet: Das Feld
  // gibt den Fokus ab, der Browser feuert daraufhin `change` — einmal, und nur
  // wenn sich wirklich etwas geändert hat. Hier selbst zu posten würde bei
  // geändertem Wert zweimal speichern, und der Fokus bliebe im Feld: Eine
  // fehlgeschlagene Speicherung ließe den falschen Text dann stehen, statt ihn
  // wie jeden anderen Bedienschritt auf den Serverstand zurückspringen zu
  // lassen (siehe post()).
  field.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') field.blur();
  });
  return field;
}

function entryRow(node, termCounts, draft) {
  const item = document.createElement('li');
  item.className = `entry ${node.type} ${node.hidden ? 'hidden' : ''}`.trim();
  item.id = `entry-${node.id}`;

  if (node.type === 'person' && node.portrait) {
    const portrait = document.createElement('img');
    portrait.className = 'portrait';
    portrait.src = node.portrait;
    // Decorative in this row: the text next to it already names the person and
    // the time, and no screen reader is at the station anyway.
    portrait.alt = '';
    item.appendChild(portrait);
  }

  if (node.type === 'person') {
    item.appendChild(nameField(node, draft));
  } else {
    const label = document.createElement('span');
    label.className = 'label';
    label.textContent = node.label;
    item.appendChild(label);
  }

  const meta = document.createElement('span');
  meta.className = 'meta';
  meta.textContent =
    node.type === 'person' ? termCountText(termCounts.get(node.id) || 0) : `${node.mentions}×`;
  item.appendChild(meta);

  const button = document.createElement('button');
  button.className = 'hide';
  button.textContent = node.hidden ? 'einblenden' : 'ausblenden';
  button.addEventListener('click', () =>
    post('/api/hidden', { node_id: `${node.type}:${node.id}`, hidden: !node.hidden }),
  );
  item.appendChild(button);
  return item;
}

/** Append to each cap step how many terms it would actually leave on the wall.
 *
 * The count used to sit on the touchscreen's own density buttons; it followed
 * the dial here when the visitor controls lost it (2026-08-26), because the
 * knowledge behind it must not be lost with them: a step with nothing behind
 * it empties the wall and reads as a broken control unless it says so first.
 * Also catches the case a plain cap number cannot show on its own: "alle"
 * (999) on a graph with only 14 terms still says "alle (14)", not "alle
 * (999)".
 *
 * Counted the way the wall counts — hidden terms are not on it, so they are in
 * no step. Deliberately not the operator list's own rule below, which keeps
 * hidden entries so "einblenden" stays reachable; that is a different question
 * from "what would the room see". Same selection rule the wall itself applies
 * (`graph-model.js`), so the number is never a different count than what a
 * visitor would actually see at that step. */
function showDensityCounts(graph) {
  const terms = (graph.nodes || []).filter((node) => node.type === 'term');
  for (const option of document.getElementById('max-terms').options) {
    // The markup's text is the base label. Cached on first pass so a second
    // render appends to the label, not to the label plus its last count.
    if (option.dataset.label === undefined) option.dataset.label = option.textContent;
    const cap = Number(option.value);
    const count = selectVisibleTermIds(terms, cap).size;
    option.textContent = `${option.dataset.label} (${count})`;
  }
}

/** Was gerade in ein Namensfeld getippt wird — oder `null`, wenn keines den
 * Fokus hat.
 *
 * Die Liste wird bei JEDEM Push komplett neu gebaut (`replaceChildren()`
 * unten). Für einen Knopf ist das folgenlos, für ein Textfeld nicht: Ein Push
 * mitten im Tippen — ein beendetes Interview, ein anderer Bedienschritt, die
 * eigene Speicherung — ersetzte sonst das halbfertige Wort durch den
 * Servertext und schöbe den Cursor in eine Zeile, die es nicht mehr gibt.
 * Genau das ist am Bedienpult nicht theoretisch: Interviews landen im Minutentakt.
 *
 * Also merkt sich render() vor dem Neubau dieses eine Feld mit Inhalt und
 * Cursorposition und stellt es danach wieder her. Der Servertext gewinnt
 * wieder, sobald das Feld den Fokus abgibt — dann ist gespeichert und beide
 * sagen ohnehin dasselbe. Der Entwurf wird bewusst NICHT global gehalten,
 * sondern pro Neubau frisch aus dem Dokument gelesen: So kann er nicht länger
 * leben als der Fokus, den er beschreibt. */
function editingDraft(list) {
  const active = document.activeElement;
  if (!active || active.dataset?.nameFor === undefined || !list.contains(active)) return null;
  return {
    personId: active.dataset.nameFor,
    value: active.value,
    start: active.selectionStart,
    end: active.selectionEnd,
  };
}

function restoreDraft(list, draft) {
  if (!draft) return;
  const field = list.querySelector(`input[data-name-for="${draft.personId}"]`);
  // Die Person kann inzwischen aus der Liste verschwunden sein. Dann gibt es
  // nichts wiederherzustellen — und nichts, was der Operator dort noch tippen
  // könnte.
  if (!field) return;
  field.focus();
  field.setSelectionRange(draft.start, draft.end);
}

// ─── Der Interviewschalter ─────────────────────────────────────────────────
//
// Zwei Knöpfe, kein Umschalter, und jeder trägt seinen absoluten Wert fest im
// Code — der ganze Grund dafür steht in frontend/operator.html (der Vorfall um
// 01:14:51 in der Nacht zum 2026-09-02). Hier steht nur, was daraus für den
// Ablauf folgt.

/** Wie lange die eigene Übernahme (siehe `schalteInterview`) einer
 * widersprechenden Servermeldung standhält.
 *
 * Nicht null, weil zwischen dem Druck und dem geöffneten Interview jede
 * beliebige andere Zustandsmeldung liegen kann — ein verschobener Regler etwa,
 * der noch `interview: null` mitträgt, weil der Worker die Warteschlange noch
 * nicht abgearbeitet hat. Ihr sofort zu folgen ließe den Knopf zurückspringen:
 * genau das Flackern, das nach einem nicht angekommenen Druck aussieht.
 *
 * Aber auch nicht unendlich, denn das Bedienpult ZEIGT den Zustand, es besitzt
 * ihn nicht: Es gibt einen zweiten Steuerweg (den Schalter am Mikrofon, an
 * denselben Endpunkt). Legt den jemand um, während hier noch eine Erwartung
 * steht, muss die Anzeige nach spätestens dieser Frist wieder dem Server
 * folgen. Fünf Sekunden sind reichlich für eine Warteschlange, die im
 * Normalfall im Millisekundenbereich antwortet, und kurz genug, dass ein
 * falscher Stand nicht stehen bleibt. */
const INTERVIEW_ERWARTUNG_MS = 5000;

/** Wie lange „Interview beenden" nachlaeuft, bevor es wirklich beendet.
 *
 * 🔴 Birk, 2026-09-02, nach einem echten Schaden an der Wand: „Ich will das
 * Interview schon recht zeitig beenden, um dann mit den Menschen reden zu
 * koennen." Genau das ist an diesem Tag schiefgegangen — p14 (Martin Kranz)
 * wurde mitten in seiner Antwort auf die letzte Frage gestoppt. Den Rest
 * sprach er zu Ende, das Transkript-Final kam sechs Minuten spaeter, und weil
 * `kg/transcript.py` allein nach dem Zeitstempel schneidet, landeten drei
 * seiner Begriffe („Grosse Kueche", „Verzicht auf Keller", „Weniger Raum,
 * mehr Natur") bei der NAECHSTEN Person.
 *
 * Acht Sekunden sind Birks Zahl (zuerst 6, am selben Tag auf 8 erhoeht). Sie
 * decken die gemessene STT-Laufzeit ab: an diesem Tag 2,8 bis 7,7 s „from
 * speech end to final" (`~/kg-logs/stt.log`), im Mittel rund 4 s — 6 s haetten
 * den langsamsten Fall knapp verfehlt. Ein noch laengerer Nachlauf faenge
 * mehr, hielte aber auch das Mikrofon laenger fuer die naechste Person offen
 * — und das ist derselbe Fehler in die andere Richtung.
 *
 * Ueberschreibbar fuer die Tests, damit sie nicht acht Sekunden schlafen. */
const STOP_NACHLAUF_MS = 8000;
let stopNachlauf = null;      // laufender Timer, oder null
let stopNachlaufBis = 0;      // wann er ablaeuft (fuer die Anzeige)
let stopNachlaufTakt = null;  // der Sekundentakt der Anzeige

// Was der letzte Druck bewirken sollte (`true`/`false`), oder `null`: keine
// offene Erwartung, es gilt allein der Server.
let interviewErwartet = null;
let interviewErwartetSeit = 0;
// Solange eine Anfrage unterwegs ist, sind beide Knöpfe zu — ein zweiter Druck
// auf einen Knopf, dessen erster noch fliegt, hilft niemandem.
let interviewSendet = false;

/** Was der Server über das Interview sagt: `true`, `false` — oder `null` für
 * „noch nichts gesagt". Siehe den Kommentar an `lastState` oben. */
function interviewLautServer(state) {
  if (state.interview === undefined) return null;
  return Boolean(state.interview);
}

function zeigeInterviewMeldung(text, fehler) {
  const feld = document.getElementById('interview-meldung');
  feld.textContent = text;
  feld.classList.toggle('fehler', Boolean(fehler));
}

/** Zustandstext und die beiden Knöpfe, aus einer einzigen Quelle.
 *
 * Es gibt drei Lagen, und alle drei stehen sichtbar am Gerät: „Interview
 * läuft" (beenden ist offen), „kein Interview" (starten ist offen) und
 * „Zustand unbekannt" — dann ist beides zu, weil raten hier die eine
 * gefährliche Handlung wäre.
 *
 * Gesperrt und nicht versteckt: Ein Knopf, der kommt und geht, lässt das
 * Bedienpult im Leerlauf so aussehen, als gäbe es diesen Weg gar nicht — und
 * genau den sucht jemand, der ihn eilig braucht. Der graue Knopf sagt beides
 * zugleich: dass es ihn gibt, und dass er jetzt nicht dran ist. Ausprobieren
 * lässt er sich trotzdem nicht, was der ursprüngliche Grund fürs Verstecken
 * war (2026-09-01). */
function zeigeInterviewSchalter(state) {
  let laeuft = interviewLautServer(state);
  if (interviewErwartet !== null) {
    if (laeuft === interviewErwartet || Date.now() - interviewErwartetSeit > INTERVIEW_ERWARTUNG_MS) {
      // Der Server sagt inzwischen dasselbe, oder die Frist ist abgelaufen:
      // Die Erwartung hat ihren Dienst getan und tritt ab.
      interviewErwartet = null;
    } else {
      laeuft = interviewErwartet;
    }
  }
  document.getElementById('interview').textContent =
    laeuft === null ? 'Zustand unbekannt' : laeuft ? 'Interview läuft' : 'kein Interview';
  // `laeuft !== false` statt `laeuft`: Bei `null` ist NICHT „kein Interview"
  // gemeint, sondern „unbekannt", und dann muss auch der Startknopf zu sein.
  document.getElementById('interview-start').disabled = interviewSendet || laeuft !== false;
  document.getElementById('interview-stop').disabled = interviewSendet || laeuft !== true;
  // 🔴 Endet das Interview waehrend des Nachlaufs auf einem ANDEREN Weg (der
  // Schalter am Mikrofon, ein Zeitablauf), muss der Timer weg. Sonst schlaegt
  // er sechs Sekunden spaeter zu und beendet das NAECHSTE Interview — das
  // waere derselbe Schaden, gegen den der Nachlauf gebaut ist, nur eine
  // Person weiter.
  if (stopNachlauf !== null && laeuft !== true) {
    abbrechenNachlauf();
    zeigeInterviewMeldung('Interview endete anderweitig — Nachlauf abgebrochen', false);
  }
}

/** Einen der beiden Knöpfe ausführen. `gewuenscht` ist der Wert, den der Knopf
 * fest trägt — er wird hier nie aus dem Anzeigestand errechnet.
 *
 * Bewusst DERSELBE Endpunkt wie der Schalter am Mikrofon, mit demselben Grund
 * „mic_switch": ein zweiter Weg zum selben Ziel, kein zweiter Mechanismus. Ein
 * eigener Endpunkt hätte einen eigenen Grund erzeugt und damit zwei Arten von
 * beendeten Interviews, die im Nachhinein auseinanderzuhalten wären, ohne dass
 * jemand etwas davon hat.
 *
 * Kein Bestätigungsdialog: Der passende Knopf ist immer nur der, der zum
 * angezeigten Zustand gehört, und ein versehentlich beendetes Interview ist an
 * dieser Station kein Verlust — der nächste Schalterdruck oder das nächste
 * Foto beginnt das nächste. Ein Dialog vor einem harmlosen Knopf kostet in dem
 * Moment Zeit, in dem jemand ihn eilig braucht. */
function schalteInterview(gewuenscht) {
  interviewSendet = true;
  zeigeInterviewMeldung(gewuenscht ? 'Interview wird gestartet …' : 'Interview wird beendet …', false);
  zeigeInterviewSchalter(lastState);

  post('/api/interview_switch', { on: gewuenscht }).then((ergebnis) => {
    interviewSendet = false;
    if (ergebnis.ok) {
      // 🔴 Die Lehre aus der App (`MainActivity.schalteInterview`): sofort
      // übernehmen, nicht auf die nächste Meldung warten. „Bis zu drei
      // Sekunden Verzögerung nach einem Druck fühlen sich nach einem nicht
      // angekommenen Knopf an, und dann drückt man noch einmal." Hier ist die
      // Verzögerung eine andere und der Schluss derselbe: Der Server legt den
      // Wechsel nur in die Warteschlange (`Core.on_mic_switch`), geöffnet oder
      // geschlossen wird er im Worker, und erst danach kommt die
      // Zustandsmeldung über /events.
      interviewErwartet = gewuenscht;
      interviewErwartetSeit = Date.now();
      zeigeInterviewMeldung(gewuenscht ? 'Interview gestartet' : 'Interview beendet', false);
    } else {
      // Nichts übernehmen: Die Anfrage kann die Station erreicht haben und nur
      // die Antwort verloren gegangen sein — was hier steht, bleibt deshalb
      // das, was zuletzt vom Server kam, und der Knopf wird wieder bedienbar.
      // Ein Fehlschlag darf das Bedienpult nicht totstellen, gerade weil beide
      // Knöpfe absolute Werte senden und ein zweiter Druck damit höchstens
      // wirkungslos sein kann.
      interviewErwartet = null;
      zeigeInterviewMeldung(`Nicht angekommen (${ergebnis.fehler}) — bitte erneut drücken`, true);
    }
    zeigeInterviewSchalter(lastState);
  });
}

/** „Interview beenden" mit Nachlauf — und ein zweiter Druck bricht ihn ab.
 *
 * Warum abbrechen und nicht sofort beenden: Ein versehentlicher Druck ist der
 * haeufigere Fall, und der Abbruch ist die Richtung, in der nichts kaputtgeht.
 * Wer wirklich sofort beenden will, wartet sechs Sekunden — wer versehentlich
 * gedrueckt hat, haette ein Interview verloren.
 *
 * Der Nachlauf ueberlebt kein Neuladen der Seite. Das ist Absicht: Ein Timer,
 * der einen Reload uebersteht, beendete ein Interview, von dem der Mensch vor
 * dem Schirm nichts mehr weiss. Nach einem Reload laeuft das Interview weiter
 * — sichtbar, und der Knopf ist wieder da. */
function beendeMitNachlauf() {
  if (stopNachlauf !== null) {
    abbrechenNachlauf();
    zeigeInterviewMeldung('Beenden abgebrochen — das Interview laeuft weiter', false);
    return;
  }
  const dauer = window.kgOperator.stopNachlaufMs;
  if (!(dauer > 0)) {
    schalteInterview(false);
    return;
  }
  // 🔴 ZUERST das Satzende ausloesen, dann erst warten (Birk, 2026-09-02):
  // „Das Problem ist der VAD. Wenn keine Stille kommt, weil weiter geredet
  // wird, wird das Letztgesagte trotzdem nicht genommen." Der VAD schliesst
  // einen Chunk erst nach 700 ms Stille ab — wird durchgeredet, kommt dieser
  // Moment nie, und blosses Warten half deshalb gar nichts.
  //
  // Ohne `await`: Der Nachlauf laeuft ab dem Druck, nicht ab der Antwort.
  // Scheitert der Aufruf, sagt der Kern es im Log und der Nachlauf endet
  // trotzdem — ein Interview, das wegen eines toten Endpunkts NICHT endet,
  // waere schlimmer als ein verlorener letzter Satz.
  post('/api/stt/satzende', {}).catch(() => {});
  stopNachlaufBis = Date.now() + dauer;
  const knopf = document.getElementById('interview-stop');
  const anzeigen = () => {
    const rest = Math.max(0, Math.ceil((stopNachlaufBis - Date.now()) / 1000));
    knopf.textContent = `Beenden in ${rest} s — klicken zum Abbrechen`;
  };
  anzeigen();
  stopNachlaufTakt = window.setInterval(anzeigen, 250);
  stopNachlauf = window.setTimeout(() => {
    abbrechenNachlauf();
    schalteInterview(false);
  }, dauer);
  zeigeInterviewMeldung('Das Mikrofon laeuft noch — der letzte Satz kommt mit', false);
}

function abbrechenNachlauf() {
  if (stopNachlauf !== null) window.clearTimeout(stopNachlauf);
  if (stopNachlaufTakt !== null) window.clearInterval(stopNachlaufTakt);
  stopNachlauf = null;
  stopNachlaufTakt = null;
  document.getElementById('interview-stop').textContent = 'Interview beenden';
}

document.getElementById('interview-start').addEventListener('click', () => {
  // Ein Start waehrend des Nachlaufs hebt ihn auf: Wer startet, will kein
  // Beenden mehr, und ein Timer, der danach zuschlaegt, beendete das gerade
  // begonnene Interview.
  abbrechenNachlauf();
  schalteInterview(true);
});
document.getElementById('interview-stop').addEventListener('click', beendeMitNachlauf);

function render(graph, state) {
  lastGraph = graph;
  lastState = state;

  document.getElementById('max-terms').value = String(state.max_terms);
  showDensityCounts(graph);
  document.getElementById('camera').value = state.camera_mode;
  document.getElementById('camera-min-label').value = String(state.camera_min_label ?? 40);
  showMinLabelValue(state.camera_min_label ?? 40);
  document.getElementById('camera-speed').value = String(state.camera_speed ?? 1);
  showSpeedValue(state.camera_speed ?? 1);
  document.getElementById('portrait-size').value = String(state.portrait_size ?? 120);
  showPortraitSizeValue(state.portrait_size ?? 120);
  document.getElementById('stt').classList.toggle('ok', Boolean(state.stt_connected));
  // Bewusst ein eigenes Abzeichen neben STT und nicht dasselbe: das eine
  // sagt, ob der Erkennungsserver erreichbar ist, das andere, ob das
  // Mikrofon im Raum eingeschaltet ist. Genau die beiden auseinanderzuhalten
  // ist der Moment, in dem jemand auf diese Leiste schaut.
  document.getElementById('mic').classList.toggle('ok', state.mic_on !== false);
  zeigeInterviewSchalter(state);

  const list = document.getElementById('entries');
  const draft = editingDraft(list);
  list.replaceChildren();

  // How many terms each person carries, for their row's meta text. One pass
  // over the edges; every edge in this graph runs person -> term.
  const termCounts = new Map();
  for (const edge of graph.edges || []) {
    termCounts.set(edge.source, (termCounts.get(edge.source) || 0) + 1);
  }

  // Persons first, newest recording first. Two reasons for the order, both
  // about reaching a row without hunting for it: the cap below never applies
  // to persons (every person is on the wall, always — so filtering them by
  // `max_terms` would hide a row for a node that is demonstrably visible), and
  // the reason to open this list is nearly always the portrait that just
  // appeared. A day's persons are one per interview, so the block stays short
  // enough that the setup's test portrait is still findable at its foot.
  // Terms keep their own A-Z order below, unchanged.
  const persons = graph.nodes
    .filter((node) => node.type === 'person')
    .sort((a, b) => (b.created_at || 0) - (a.created_at || 0));

  // Same cap the wall applies, so the list offers an action only where that
  // action has a visible effect. Deliberately NOT visibleGraph(): that one
  // also drops hidden nodes, which is right for the wall and fatal here — the
  // hidden entry IS the way back, and a list that dropped it would make
  // "ausblenden" a one-way door with no matching "einblenden". That holds for
  // a hidden person just as much as for a hidden term. Also deliberately
  // without the wall's own hysteresis grace list: this list answers "what
  // would the cap alone show", not "what does the wall happen to still be
  // holding onto right now".
  const terms = graph.nodes.filter((node) => node.type === 'term');
  const visibleTermIds = selectVisibleTermIds(terms, state.max_terms);
  const visibleTerms = terms
    .filter((node) => node.hidden || visibleTermIds.has(node.id))
    .sort((a, b) => a.label.localeCompare(b.label, 'de'));

  for (const node of [...persons, ...visibleTerms]) {
    list.appendChild(entryRow(node, termCounts, draft));
  }
  restoreDraft(list, draft);
}

function showTranscript(text) {
  document.getElementById('transcript').textContent = text;
}

/** Print the slider's value the way an operator reads it, not the way JS
 * stringifies a float: "1,45×", never "1.4500000000000002×".
 *
 * Am unteren Anschlag steht das ganze Netz ohnehin lesbar im Bild, also fährt
 * die Kamera gar nicht — sie hat nichts zu suchen, was nicht schon zu sehen
 * wäre. Das ist seit dem 2026-09-02 gewollt und kein Defekt (Birk: „solange
 * das ganze Netz darstellbar ist […] brauchen wir gar keine Kamerafahrt"),
 * aber es sieht aus wie eine kaputte Kamera, wenn niemand es sagt — genau die
 * Rückmeldung, die am 2026-08-26 zum alten Zoomregler kam („keine
 * automatische Bewegung" am unteren Anschlag). Also sagt es der Regler, statt
 * es auf der Ausstellungsfläche wiederentdecken zu lassen. */
function showMinLabelValue(px) {
  const value = Number(px);
  const hint = value <= 12 ? ' — vermutlich immer das ganze Netz, ohne Fahrt' : '';
  document.getElementById('camera-min-label-value').textContent =
    `mindestens ${Math.round(value)} px${hint}`;
}

document.getElementById('max-terms').addEventListener('change', (event) =>
  post('/api/max_terms', { value: Number(event.target.value) }),
);
document.getElementById('camera').addEventListener('change', (event) =>
  post('/api/camera', { mode: event.target.value }),
);
// Two listeners, deliberately: `input` fires continuously while the operator
// drags and only updates the local read-out, so the number under the thumb
// tracks the hand. `change` fires once on release and is the only one that
// posts — a POST per pixel would push a state broadcast to every SSE client
// (wall, plenary mirror) dozens of times per second.
document.getElementById('camera-min-label').addEventListener('input', (event) =>
  showMinLabelValue(event.target.value),
);
document.getElementById('camera-min-label').addEventListener('change', (event) =>
  post('/api/camera_min_label', { pixels: Number(event.target.value) }),
);

/** The largest a portrait may get on the wall, in the unit the operator is
 * choosing in: pixels of the projected image, whole ones.
 *
 * No fraction and no multiplier, because this control is not relative to
 * anything — unlike the zoom, which multiplies a fit, this is a size in
 * pixels. "höchstens" and not a bare number because it is a CEILING since
 * 2026-08-30: on a busy wall the portraits stay under it by themselves and
 * the slider does nothing at all, and in manual mode it does not apply. An
 * operator who reads it as "so groß sind die Porträts" would go looking for a
 * fault when nothing moves. */
function showPortraitSizeValue(pixels) {
  const value = Math.round(Number(pixels) || 120);
  document.getElementById('portrait-size-value').textContent = `höchstens ${value} px`;
}

document.getElementById('portrait-size').addEventListener('input', (event) =>
  showPortraitSizeValue(event.target.value),
);
document.getElementById('portrait-size').addEventListener('change', (event) =>
  post('/api/portrait_size', { pixels: Number(event.target.value) }),
);

/** The tour's pace as a plain fraction — "1/1", "1/2", "1/4".
 *
 * Not a percentage and not seconds: the operator is choosing "half as fast",
 * and 0.5 or "50 %" or "10,4 s pro Etappe" all take a moment of arithmetic to
 * turn back into that. The slider is continuous, so anything between the neat
 * fractions is shown as a decimal divisor ("1/1,4"). */
function showSpeedValue(factor) {
  const value = Math.min(1, Math.max(0.25, Number(factor) || 1));
  const divisor = 1 / value;
  const rounded = Math.round(divisor * 10) / 10;
  const text = Number.isInteger(rounded) ? String(rounded) : String(rounded).replace('.', ',');
  document.getElementById('camera-speed-value').textContent = `1/${text}`;
}

document.getElementById('camera-speed').addEventListener('input', (event) =>
  showSpeedValue(event.target.value),
);
document.getElementById('camera-speed').addEventListener('change', (event) =>
  post('/api/camera_speed', { factor: Number(event.target.value) }),
);

window.kgOperator = { render, showTranscript, stopNachlaufMs: STOP_NACHLAUF_MS };

let graph = { nodes: [], edges: [], quotes: [] };
let state = {
  max_terms: 32,
  camera_mode: 'fit',
  camera_min_label: 40,
  camera_speed: 1,
  portrait_size: 120,
  stt_connected: false,
  // Der physische Schalter am Mikrofon (STT-Server, --mic-gate). Default an:
  // eine Station ohne Schalter meldet nie etwas und hat ein offenes Mikrofon.
  mic_on: true,
  // `interview` fehlt hier ABSICHTLICH, und das ist kein vergessenes Feld:
  // Solange der Server nichts gemeldet hat, ist der Zustand unbekannt.
  // `interview: null` hiesse „kein Interview" — eine Behauptung, die den
  // Startknopf scharf stellt, waehrend im Raum vielleicht laengst jemand
  // spricht. Der Server schickt das Feld in JEDER Zustandsmeldung
  // (`current_state`), sein Fehlen heisst also verlaesslich „noch keine
  // Meldung gesehen".
};
const events = new EventSource('/events');
events.onmessage = (message) => {
  const payload = JSON.parse(message.data);
  if (payload.type === 'graph') graph = payload.graph;
  else if (payload.type === 'state') state = payload.state;
  else if (payload.type === 'transcript') return showTranscript(payload.text);
  render(graph, state);
};

// --- Aufsicht über die Spracherkennung ---------------------------------------
// 🔴 Zwei getrennte Fragen, zwei getrennte Anzeigen (2026-09-02):
//   „STT" oben  = steht die Verbindung zum Dienst auf 5051?
//   „Whisper"   = kommt beim Anbieter tatsächlich Text heraus?
// Beim Ausfall an diesem Tag war das erste grün und das zweite tot. Wer beides
// in ein Abzeichen legt, baut genau die Falle nach, die eine Viertelstunde
// gekostet hat.
//
// Eigener Abrufstrom statt SSE: Der Befund ändert sich im Minutentakt, nicht
// im Sekundentakt, und er hängt an einem fremden Anbieter — er gehört nicht in
// den Zustand, den der Kern über seine eigene Welt schickt.
const STT_TAKT_MS = 15000;
let sttStand = null;
let sttWechselLaeuft = false;

function sttMeldung(text, fehler) {
  const feld = document.getElementById('stt-meldung');
  if (!feld) return;
  feld.textContent = text;
  feld.classList.toggle('fehler', Boolean(fehler));
}

/** Malt den Befund. Drei Lagen, absichtlich drei Farben.
 *
 * `gesund === null` heißt „noch nicht geprüft" und bekommt Grau. Grün wäre
 * eine Behauptung, Rot ein Fehlalarm beim Aufschlagen der Seite — dieselbe
 * Regel wie beim „Zustand unbekannt" der Interviewknöpfe. */
function zeigeSttAufsicht(stand) {
  const lampe = document.getElementById('stt-gesund');
  const anbieterFeld = document.getElementById('stt-anbieter');
  const knopf = document.getElementById('stt-wechsel');
  if (!lampe || !anbieterFeld || !knopf) return;

  const befund = (stand && stand.infomaniak) || {};
  const gesund = befund.gesund;
  const anbieter = stand && stand.anbieter;

  // 🔴 Ein rotes Lämpchen über einer tadellos laufenden Erkennung ist ein
  // Fehlalarm (2026-09-02: nach dem Wechsel auf ElevenLabs stand „Whisper ✗"
  // da, während alles verstanden wurde). Solange ein ANDERER Anbieter
  // erkennt, ist Whispers Zustand keine Störung, sondern die Auskunft, ob der
  // Rückweg nach Genf schon offen ist. Gedämpft statt rot — rote Lampen, die
  // nichts bedeuten, entwerten die, die etwas bedeuten.
  const nebensache = anbieter && anbieter !== 'infomaniak';
  lampe.classList.toggle('ok', gesund === true);
  lampe.classList.toggle('unbekannt', gesund !== true && (nebensache || gesund == null));
  lampe.textContent = gesund === true
    ? (nebensache ? 'Whisper wieder da' : 'Whisper ok')
    : gesund === false ? 'Whisper ✗' : 'Whisper ?';

  // 🔴 Der fremde Anbieter wird BENANNT und hervorgehoben. Ein Wechsel in die
  // USA, den man der Seite nicht ansieht, ist derselbe stille Zustand, den
  // diese ganze Anzeige verhindern soll.
  anbieterFeld.textContent = anbieter === 'elevenlabs'
    ? 'läuft über ElevenLabs (USA)'
    : anbieter === 'infomaniak'
      ? 'läuft über Infomaniak (Genf)'
      : 'Anbieter unbekannt';
  anbieterFeld.classList.toggle('fremd', anbieter === 'elevenlabs');

  const ziel = anbieter === 'elevenlabs' ? 'infomaniak' : 'elevenlabs';
  knopf.textContent = ziel === 'elevenlabs'
    ? 'auf ElevenLabs wechseln (USA)'
    : 'zurück auf Infomaniak';
  knopf.dataset.ziel = ziel;
  // Gesperrt, solange niemand weiß, was läuft: Ein Wechsel „weg von unbekannt"
  // wäre ein Neustart auf Verdacht, mitten in einem laufenden Interview.
  knopf.disabled = sttWechselLaeuft || !anbieter;

  if (!stand || stand.aufsicht === false) {
    sttMeldung('keine Aufsicht (kein API-Schlüssel)', false);
  } else if (nebensache) {
    // Hier ist Whispers Zustand eine Auskunft über den Rückweg, keine Störung.
    sttMeldung(gesund === true
      ? 'Infomaniak antwortet wieder — Rückweg offen'
      : 'Infomaniak noch nicht zurück', false);
  } else if (gesund === false) {
    sttMeldung(befund.meldung || 'antwortet nicht', true);
  } else if (befund.geprueft_vor_s != null) {
    sttMeldung(`geprüft vor ${Math.round(befund.geprueft_vor_s)} s`, false);
  } else {
    sttMeldung('', false);
  }
}

function holeSttStand() {
  return fetch('/api/stt')
    .then((antwort) => (antwort.ok ? antwort.json() : null))
    .then((stand) => {
      sttStand = stand;
      zeigeSttAufsicht(stand);
    })
    .catch((fehler) => {
      // Der Kern selbst ist weg. Das sagt das STT-Abzeichen oben schon; hier
      // nur nicht so tun, als sei der letzte Befund noch gültig.
      console.warn('/api/stt nicht erreichbar', fehler);
      zeigeSttAufsicht(null);
    });
}

const sttWechselKnopf = document.getElementById('stt-wechsel');
if (sttWechselKnopf) {
  sttWechselKnopf.addEventListener('click', () => {
    const ziel = sttWechselKnopf.dataset.ziel;
    if (!ziel) return;
    // 🔴 Rückfrage nur beim Weg NACH DRAUSSEN. Der Weg zurück nach Genf ist
    // die Rückkehr zur Vorgabe und braucht keine Hürde.
    if (ziel === 'elevenlabs'
        && !window.confirm('Auf ElevenLabs (USA) wechseln?\n\n'
          + 'Die Stimmen der Besucher verlassen damit den EU-Raum.\n'
          + 'Die Spracherkennung startet dabei neu — etwa 10 Sekunden ohne Erkennung.')) {
      return;
    }
    sttWechselLaeuft = true;
    zeigeSttAufsicht(sttStand);
    sttMeldung('starte neu …', false);
    post('/api/stt/anbieter', { anbieter: ziel }).then((ergebnis) => {
      sttWechselLaeuft = false;
      if (ergebnis && ergebnis.ok === false) {
        sttMeldung(`Wechsel fehlgeschlagen: ${ergebnis.fehler || ''}`, true);
      }
      // Nicht sofort nachfragen: Der neue Dienst braucht ein paar Sekunden,
      // bis er den Port hält. Eine Antwort davor hiesse „Anbieter unbekannt"
      // und sähe aus wie ein gescheiterter Wechsel.
      window.setTimeout(holeSttStand, 6000);
    });
  });
}

holeSttStand();
window.setInterval(holeSttStand, STT_TAKT_MS);
