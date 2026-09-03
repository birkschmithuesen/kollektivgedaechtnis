// Die Tafel: der eigene Bereich neben dem Netz.
//
// 🔴 WARUM (Birk, 2026-09-02, abends): „Bei Einblendung von Zitaten soll dafür
// ein eigener Bereich auf dem Monitor sein, wo das Netz nicht angezeigt wird,
// da aktuell gehighlightete Knoten von dem Zitatfenster überdeckt werden. Also
// sowas wie ein vertikaler Split Screen."
//
// Der Fehler, den das behebt, entstand am selben Tag: Seit die Nachbarschaft
// beim Antippen hervorgehoben wird (`nachbarschaft.js`), liegt das Zitat
// ausgerechnet über dem, was es erklärt. Zwei Dinge wollen dieselbe Fläche.
//
// Also weicht das Netz aus, statt überdeckt zu werden: `--tafel-breite` macht
// `#cy` schmaler, Cytoscape bekommt ein `resize()`, und die Kamera fasst neu.
// Solange nichts ausgewählt ist, steht die Variable auf 0 — dann ist die Wand
// exakt so breit wie zuvor und niemand sieht, dass es die Tafel gibt.
//
// 🔴 Sie ERSETZT das Zitat-Overlay nicht, sie steht daneben: Das Overlay
// gehört zur Touchfläche und zum Handy, wo eine Karte über dem Bild richtig
// ist. Die Tafel gehört zur Wand, wo Platz daneben ist. Welche von beiden
// gilt, entscheidet `projection.html` beim Aufbau.

/** Wie breit die Tafel aufgeht, in Prozent der Fensterbreite.
 *
 * Ein Drittel: Bei 1920 px sind das 640 px — genug für eine Zeile von etwa
 * 40 Zeichen bei der Schriftgröße der Wand, und das Netz behält 1280 px,
 * also mehr als die Hälfte. Weniger, und der Text bricht in Stummel; mehr,
 * und das Netz wird zur Beigabe. */
const BREITE_PROZENT = 33;

export function attachTafel(view, { holeText } = {}) {
  const cy = view.cy;
  const tafel = document.createElement('aside');
  tafel.id = 'tafel';
  tafel.hidden = true;
  // Für Vorlesewerkzeuge unsichtbar wie der Rest der Wand: Die Projektion ist
  // eine Fläche ohne Bedienung.
  tafel.setAttribute('aria-hidden', 'true');
  const inhalt = document.createElement('div');
  inhalt.id = 'tafel-inhalt';
  tafel.appendChild(inhalt);
  document.body.appendChild(tafel);

  let offen = false;
  // Der Knoten, dessen Tafel gerade steht — oder null im Ruhezustand.
  // 🔴 WOZU (gemessen 2026-09-02 am echten Netz, 76 Knoten): Ohne ihn fasste
  // `neuFassen()` auf `uebersicht()`, also auf das GANZE Netz. Bei fünf
  // Testknoten ist das dasselbe Bild; bei 76 passt das Netz nicht mehr
  // lesbar ins Feld, die Wand zeigt einen Ausschnitt — und der angetippte
  // Knoten lag darin gemessen bei x=1615 auf einer 1286 px breiten Fläche,
  // also ausserhalb. Die Tafel erklärte einen Knoten, der nicht zu sehen war.
  let gewaehlt = null;
  // Was gerade auf der Tafel steht: {art: 'person'|'begriff', id}.
  // 🔴 WOZU (gemessen 2026-09-03): `gewaehlt` traegt den Cytoscape-Knoten fuer
  // die Kamera; fuer ein Nachziehen des TEXTES braucht es die Art dazu. Ohne
  // das blieb die offene Tafel stehen, waehrend der Graph weiterwuchs — bei
  // einem Netz, das alle paar Minuten ein Interview dazubekommt, zeigt sie
  // dann veraltete Begriffe, solange jemand liest.
  let gezeigt = null;

  function breiteSetzen(px) {
    document.documentElement.style.setProperty('--tafel-breite', `${px}px`);
    // 🔴 ZWEI Schritte, und der zweite war zuerst vergessen (gemessen
    // 2026-09-02: 229 px des Netzes lagen danach unter der Tafel).
    //
    // 1. `cy.resize()` — Cytoscape muss die neue Größe des Containers sehen.
    // 2. `onGraphChanged()` — die Kamera hält ihr Fit-Niveau in einem Cache
    //    (`_fitLevelCache`, camera.js), der sonst nur bei einer Änderung am
    //    GRAPHEN fällt. Eine Änderung an der FLÄCHE ist für sie dasselbe
    //    Problem: Der gemerkte Zoom passt auf einen Rahmen, den es nicht mehr
    //    gibt. Ohne das fährt `uebersicht()` auf die alte Breite.
    // 🔴 NACH der Übergangszeit, nicht sofort (gemessen 2026-09-02: sonst
    // ragten 229 px des Netzes unter die Tafel, und die Kamera stand schon
    // still — sie hatte auf den ALTEN Rahmen gefasst).
    //
    // Die Breite ändert sich über 420 ms (`transition` in base.css). Ein
    // `cy.resize()` in derselben Zeile misst den Container, bevor er schmaler
    // geworden ist; Cytoscape merkt sich diese Größe und fasst danach auf
    // eine Fläche, die es nicht mehr gibt.
    //
    // 460 statt 420: ein Frame Luft, damit der Browser den letzten Schritt
    // der Übergangszeit wirklich gezeichnet hat.
    window.setTimeout(() => neuFassen(), 460);
  }

  /** Die Fläche hat sich geändert — Cytoscape und Kamera nachziehen.
   *
   * 🔴 ERST WENN DAS LAYOUT RUHT (gemessen 2026-09-02): Läuft gerade eine
   * Migration — ein neues Interview kommt an, während jemand tippt —, dann
   * fasst die Kamera mitten in der Bewegung und behält den Pan der ALTEN
   * Breite (gemessen: 960 statt 643, und 229 px des Netzes lagen danach unter
   * der Tafel). Eine Migration dauert 2,5 s; in der Zeit ist ein Tipp an einer
   * Ausstellungswand nicht unwahrscheinlich, sondern normal.
   *
   * Gewartet wird auf das echte Signal (`layoutPending`), nicht auf eine
   * feste Zeit: Ein Zeitwert wäre bei einem grossen Graphen zu kurz und bei
   * einem kleinen Verschwendung. Der Deckel bricht ab, falls das Signal nie
   * kommt — dann ist ein schlecht gefasstes Bild besser als eine Tafel, die
   * nie zu Ende aufgeht.
   *
   * 🔴 EHRLICH VERMERKT: Die Mutationsprobe konnte dieses Warten nicht
   * bestätigen — mit `if (false)` blieb der Test grün. Der Grund ist der
   * kleine Testgraph: Fünf Knoten sind in weniger als 460 ms migriert, das
   * Layout ruht also ohnehin, wenn hier gefasst wird. Wirksam war allein die
   * `requestAnimationFrame`-Pause unten.
   *
   * Es bleibt trotzdem stehen, weil die Wand keine fünf Knoten hat, sondern
   * gemessene 76, und eine Migration dort 2,5 s dauert. Wer das belegen will,
   * braucht einen Test mit einem Graphen dieser Grösse — bis dahin ist diese
   * Zeile eine begründete Vorsichtsmassnahme und kein bewiesenes Verhalten. */
  function neuFassen(versuche = 25) {
    if (view.layoutPending && versuche > 0) {
      window.setTimeout(() => neuFassen(versuche - 1), 200);
      return;
    }
    cy.resize();
    // Ein Frame Pause: `resize()` schreibt die neue Grösse, und die Kamera
    // soll sie GELESEN haben, bevor sie rahmt. Ohne das rechnet
    // `_automaticView()` im selben Durchlauf noch mit dem alten Rahmen.
    requestAnimationFrame(() => {
      // Der Fit-Cache der Kamera (`_fitLevelCache`) fällt sonst nur bei einer
      // Änderung am GRAPHEN. Eine Änderung an der FLÄCHE ist für sie dasselbe
      // Problem: Der gemerkte Zoom passt auf einen Rahmen, den es nicht mehr
      // gibt.
      view.camera.onGraphChanged();
      // 🔴 Auf die AUSWAHL fassen, nicht auf das ganze Netz. `focus()` ändert
      // den Modus nicht — die Wand bleibt so bedienbar, wie der Operator sie
      // gestellt hat — und nimmt die geschlossene Nachbarschaft, also genau
      // das, was `nachbarschaft.js` daneben hervorhebt. Beides zeigt dann
      // dieselbe Menge: was leuchtet, ist auch im Bild.
      if (gewaehlt && gewaehlt.inside && gewaehlt.inside()) {
        view.camera.focus(gewaehlt.closedNeighborhood());
      } else {
        view.camera.uebersicht();
      }
    });
  }

  function oeffne(bausteine, ziel = null, { nachziehen = false } = {}) {
    // 🔴 BEIM NACHZIEHEN NUR DER TEXT (Birk, 2026-09-03: „hast du geprueft,
    // dass es mit neu hinzukommenden interviews auch alles richtig einsortiert
    // und auch die zusatzinfo pro knoten in der seitenleiste aktualisiert?").
    //
    // Wer gerade liest, soll die neue Zeile bekommen — aber nicht an den
    // Anfang zurueckgeworfen werden und keine Kamerafahrt untergeschoben
    // kriegen. Beides waere schlimmer als eine veraltete Zeile.
    if (nachziehen) {
      const stand = inhalt.scrollTop;
      inhalt.replaceChildren(...bausteine);
      gewaehlt = ziel;
      // Nach dem Neuaufbau ist der Inhalt womoeglich kuerzer als die alte
      // Rollposition — der Browser klemmt selbst auf das Moegliche.
      inhalt.scrollTop = stand;
      return;
    }
    inhalt.replaceChildren(...bausteine);
    gewaehlt = ziel;
    if (!offen) {
      offen = true;
      tafel.hidden = false;
      // `breiteSetzen` fasst selbst neu, sobald die Fläche wirklich schmaler
      // ist — hier also nichts weiter.
      breiteSetzen(Math.round((window.innerWidth * BREITE_PROZENT) / 100));
    } else {
      // 🔴 Schon offen: Die Breite ändert sich NICHT, also läuft auch keine
      // Übergangszeit und `breiteSetzen` würde nie gerufen. Trotzdem zeigt die
      // Tafel jetzt auf einen anderen Knoten — ohne dieses Nachfassen bliebe
      // die Kamera beim vorigen stehen. Das ist der Normalfall an der Wand:
      // Wer einmal getippt hat, tippt weiter.
      neuFassen();
    }
    inhalt.scrollTop = 0;
  }

  function schliesse() {
    if (!offen) return;
    offen = false;
    gewaehlt = null;
    gezeigt = null;
    breiteSetzen(0);
    window.setTimeout(() => {
      tafel.hidden = true;
    }, 460);
  }

  // --- Was auf der Tafel steht ---------------------------------------------

  function el(tag, text, klasse) {
    const e = document.createElement(tag);
    if (text) e.textContent = text;
    if (klasse) e.className = klasse;
    return e;
  }

  function liste(titel, eintraege) {
    const teile = [el('p', titel, 'tafel-abschnitt')];
    const ul = document.createElement('ul');
    for (const { kopf, unter } of eintraege) {
      const li = document.createElement('li');
      li.appendChild(el('b', kopf));
      // Die Belegstelle gehört zum Eintrag darüber und ist nicht selbst einer.
      if (unter) li.appendChild(el('span', unter));
      ul.appendChild(li);
    }
    teile.push(ul);
    return teile;
  }

  /** Ein rundes Portrait, wie es auch im Netz haengt. Ohne Bild bleibt die
   *  Flaeche leer statt einen Platzhalter zu zeigen: Wer sich gegen ein Foto
   *  entschieden hat, ist kein fehlendes Foto (dieselbe Regel wie in
   *  projection.js). */
  function portrait(pfad, klasse) {
    const d = el('div', '', klasse);
    if (pfad) d.style.backgroundImage = `url("${pfad}")`;
    else d.classList.add('ohne-bild');
    return d;
  }

  function zeigePerson(id, { nachziehen = false } = {}) {
    const daten = holeText ? holeText.person(id) : null;
    // 🔴 Beim Nachziehen ist „nicht mehr da" ein echter Fall: Begriffe werden
    // automatisch zusammengelegt (`fold_term`, kg/store.py), eine Person kann
    // ausgeblendet werden. Dann ist Zugehen richtig — eine Tafel, die einen
    // verschwundenen Knoten weiter erklaert, zeigt etwas, das es nicht gibt.
    if (!daten) {
      if (nachziehen) schliesse();
      return;
    }
    gezeigt = { art: 'person', id };
    const teile = [];

    const kopf = el('div', '', 'tafel-kopf');
    kopf.appendChild(portrait(daten.portrait, 'tafel-portrait'));
    kopf.appendChild(el('h2', daten.name || 'Ohne Namen'));
    teile.push(kopf);

    if (daten.zitat) teile.push(el('p', daten.zitat, 'tafel-zitat'));

    if (daten.begriffe?.length) {
      teile.push(...liste('Wovon die Rede war', daten.begriffe));
    }

    // 🔴 „Teilt Themen mit": Die soziale Naehe, die das Layout nur andeutet,
    // hier als Satz. Wer im Netz nebeneinander steht, tut das genau deswegen —
    // aber niemand sieht, mit WEM und WORUEBER.
    if (daten.nahe?.length) {
      teile.push(el('p', 'Teilt Themen mit', 'tafel-abschnitt'));
      const reihe = el('div', '', 'tafel-nahe');
      for (const anderer of daten.nahe) {
        const kachel = el('div', '', 'tafel-nahe-eintrag');
        kachel.appendChild(portrait(anderer.portrait, 'tafel-portrait-klein'));
        const text = el('div', '', 'tafel-nahe-text');
        text.appendChild(el('b', anderer.name));
        text.appendChild(el('span', anderer.themen.join(' · ')));
        kachel.appendChild(text);
        reihe.appendChild(kachel);
      }
      teile.push(reihe);
    }
    oeffne(teile, cy.getElementById(id), { nachziehen });
  }

  function zeigeBegriff(id, { nachziehen = false } = {}) {
    const daten = holeText ? holeText.begriff(id) : null;
    if (!daten) {
      if (nachziehen) schliesse();
      return;
    }
    gezeigt = { art: 'begriff', id };
    const teile = [el('h2', daten.label)];
    const wie =
      daten.stimmen?.length === 1 ? 'Einmal gesagt' : `Von ${daten.stimmen.length} Menschen gesagt`;
    teile.push(el('p', wie, 'tafel-abschnitt'));

    if (daten.stimmen?.length) {
      // 🔴 Der eigentliche Gewinn dieser Flaeche: dieselbe Sache in
      // verschiedenen Worten, untereinander. „Entruempeln statt Neubau" heisst
      // bei Steffen „lieber im Keller aufraeumen", bei Marlen „die Systeme
      // nutzen, die wir schon haben". Das stand bisher nirgends.
      const ul = document.createElement('ul');
      ul.className = 'tafel-stimmen';
      for (const stimme of daten.stimmen) {
        const li = document.createElement('li');
        li.appendChild(portrait(stimme.portrait, 'tafel-portrait-klein'));
        const text = el('div', '', 'tafel-stimme-text');
        text.appendChild(el('b', stimme.kopf));
        text.appendChild(el('span', stimme.unter));
        li.appendChild(text);
        ul.appendChild(li);
      }
      teile.push(ul);
    }

    // Was inhaltlich danebenliegt — auch wenn es niemand zusammen gesagt hat.
    // Das ist genau die Verbindung, die der Graph nicht ziehen kann.
    if (daten.verwandt?.length) {
      teile.push(el('p', 'Liegt inhaltlich daneben', 'tafel-abschnitt'));
      const reihe = el('div', '', 'tafel-verwandt');
      for (const label of daten.verwandt) reihe.appendChild(el('span', label, 'tafel-chip'));
      teile.push(reihe);
    }
    oeffne(teile, cy.getElementById(id), { nachziehen });
  }

  /** Die Widersprueche des Tages.

   * 🔴 SEIT DEM 2026-09-03 RUFT NICHTS DAS MEHR VON SELBST (Birk: „nimm den
   * part 'woran sich der tag reibt' wieder raus. in der idle ansicht soll
   * keine seitenleiste da sein"). Ohne Auswahl gehoert die Flaeche dem Netz.
   *
   * Der Block bleibt stehen, weil die Daten weiter entstehen — `widerspruch.py`
   * rechnet sie nach jedem Interview und `graph.json` traegt sie — und weil
   * ein Aufruf ueber die zurueckgegebene API genuegt, um sie wieder zu zeigen.
   * Wer sie gar nicht mehr will, faengt beim LLM-Aufruf in `kg/pipeline.py` an.
   *
   * 🔴 Zwei Seiten NEBENEINANDER und nicht untereinander: Ein Widerspruch ist
   * eine Gegenueberstellung, und die Form soll das sagen, bevor jemand liest.
   * Die beiden Bauhaus-Farben rot und blau tragen die Seiten — dieselben, die
   * im Netz den Traumanker und seine Nachbarn faerben, hier aber ohne
   * Bedeutungskonflikt, weil auf der Tafel kein Netz liegt. */
  function zeigeWidersprueche() {
    const paare = holeText ? holeText.widersprueche() : [];
    if (!paare.length) return false;
    // Die Ueberschrift benennt die Ausstellung, nicht den Tag (Birk,
    // 2026-09-03). Sie steht auch dann noch richtig da, wenn das Bild spaeter
    // ausserhalb des Festivals gezeigt wird.
    const teile = [el('h2', 'Konträre Positionen NewBauhaus 2026')];
    for (const paar of paare) {
      const block = el('div', '', 'tafel-widerspruch');
      block.appendChild(el('p', paar.titel, 'tafel-widerspruch-titel'));
      const gegen = el('div', '', 'tafel-gegen');
      for (const [seite, klasse] of [[paar.eine, 'eine'], [paar.andere, 'andere']]) {
        const sp = el('div', '', `tafel-seite tafel-seite-${klasse}`);
        sp.appendChild(el('b', seite.begriff));
        sp.appendChild(el('span', seite.beleg));
        gegen.appendChild(sp);
      }
      block.appendChild(gegen);
      teile.push(block);
    }
    oeffne(teile, null);
    return true;
  }

  cy.on('tap', 'node.person', (e) => zeigePerson(e.target.id()));
  cy.on('tap', 'node.term', (e) => zeigeBegriff(e.target.id()));
  cy.on('tap', (e) => {
    // 🔴 Ins Leere tippen heisst „fertig gelesen" — dann tritt der Ruhezustand
    // an die Stelle der Auswahl. Gibt es keine Widersprueche (frueh am Tag,
    // Anbieter weg), geht die Tafel ganz zu.
    //
    // Am 2026-09-03 mittags war das entfernt („in der idle ansicht soll keine
    // seitenleiste da sein") und am selben Nachmittag zurueckgeholt („ich will
    // das zurueckgestellte Widerspruch im Idle-Mode wieder hochholen").
    // Deaktiviert war nur die Anzeige — `kg/widerspruch.py` hat die ganze Zeit
    // weitergerechnet, deshalb stand der Block sofort wieder mit dem Stand des
    // Tages da.
    if (e.target === cy && !zeigeWidersprueche()) schliesse();
  });

  /** Ein neuer Graph ist angekommen — den Text nachziehen, falls die Tafel
   * offen steht.
   *
   * Gerufen von projection.html bei jedem Graph-Push, direkt nach
   * `tafelDaten.setGraph()`. Steht nichts offen, kostet es einen Vergleich.
   */
  function aktualisiere() {
    if (!offen || !gezeigt) return;
    if (gezeigt.art === 'person') zeigePerson(gezeigt.id, { nachziehen: true });
    else zeigeBegriff(gezeigt.id, { nachziehen: true });
  }

  return {
    element: tafel,
    aktualisiere,
    schliesse,
    zeigeWidersprueche,
    istOffen: () => offen,
  };
}
