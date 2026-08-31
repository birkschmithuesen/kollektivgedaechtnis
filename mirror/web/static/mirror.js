// Was beide Mobilseiten teilen: die Verbindung und die Ehrlichkeit über das
// Alter des Standes.
//
// Die Ereignisse tragen den VOLLSTÄNDIGEN Zustand (wie an der Wand: es gibt
// kein Delta). Ein verlorenes Ereignis kostet deshalb nichts und ein
// Wiederverbinden braucht kein Nachholen — das ist der Grund, warum das hier
// so kurz sein darf.

/** Ab wann ein Stand nicht mehr als „live" gilt. Muss zu STALE_AFTER_S in
 *  mirror/receiver.py passen; der Server schickt den Wert in /healthz mit und
 *  überschreibt diesen Startwert. */
const STALE_AFTER_S = 90;

/** Nach einem Abbruch. Der Browser verbindet zwar selbst neu, aber nach einem
 *  Netzwechsel WLAN→Mobilfunk gerade nicht zuverlässig: die alte Verbindung
 *  gilt ihm als offen, während das Betriebssystem sie längst weggeräumt hat. */
const RECONNECT_MS = 4000;

/** Der Sicherheitsnetz-Takt. Puffert eine Zwischenstation den Ereignisstrom
 *  trotz aller Kopfzeilen, bleibt die Seite sonst stumm stehen, ohne dass
 *  irgendetwas nach einem Fehler aussähe. */
const POLL_MS = 25000;

export function verbindeSpiegel({ art, aufDaten, alterEl }) {
  const feldAlter = `${art}_age_s`;
  let stale_after = STALE_AFTER_S;
  // Das Alter wird lokal weitergezählt, statt am Server nachzufragen: die Uhr
  // des Handys ist gegenüber der des Servers verstellt, die VERGANGENE ZEIT
  // seit dem letzten Ereignis ist dagegen auf beiden Seiten dieselbe.
  let alterBeiEmpfang = null;
  let empfangenUm = 0;
  let quelle = null;
  let neuVersuch = null;

  function setzeAlter(sekunden) {
    alterBeiEmpfang = typeof sekunden === 'number' ? sekunden : null;
    empfangenUm = Date.now();
    zeigeAlter();
  }

  function aktuellesAlter() {
    if (alterBeiEmpfang === null) return null;
    return alterBeiEmpfang + (Date.now() - empfangenUm) / 1000;
  }

  function zeigeAlter() {
    if (!alterEl) return;
    const alter = aktuellesAlter();
    if (alter === null || alter <= stale_after) {
      alterEl.hidden = true;
      return;
    }
    alterEl.textContent = `Kein Kontakt zur Station seit ${dauer(alter)} — der Stand unten ist nicht mehr live.`;
    alterEl.hidden = false;
  }

  function nimm(payload) {
    if (!payload || payload.type !== art) return;
    setzeAlter(payload.age_s);
    try {
      aufDaten(payload[art]);
    } catch (fehler) {
      // Ein Fehler im Zeichnen darf die Verbindung nicht mitreissen — sonst
      // steht die Seite nach einem einzigen krummen Datensatz für immer.
      console.warn('konnte den Stand nicht anzeigen', fehler);
    }
  }

  function verbinde() {
    schliesse();
    try {
      quelle = new EventSource('/events');
    } catch (fehler) {
      console.warn('EventSource nicht möglich', fehler);
      planeNeuversuch();
      return;
    }
    quelle.onmessage = (nachricht) => {
      try {
        nimm(JSON.parse(nachricht.data));
      } catch (fehler) {
        console.warn('unlesbares Ereignis', fehler);
      }
    };
    quelle.onerror = () => {
      // Nicht auf die eingebaute Wiederverbindung warten: sie greift nach
      // einem Netzwechsel oft gar nicht mehr.
      planeNeuversuch();
    };
  }

  function schliesse() {
    if (quelle) {
      quelle.close();
      quelle = null;
    }
  }

  function planeNeuversuch() {
    schliesse();
    if (neuVersuch !== null) return;
    neuVersuch = window.setTimeout(() => {
      neuVersuch = null;
      verbinde();
    }, RECONNECT_MS);
  }

  async function hole() {
    // Der zweite Weg zu denselben Daten. Läuft beim Laden (damit die Seite
    // auch bei totem Ereignisstrom etwas zeigt) und alle 25 s als Kontrolle.
    try {
      const [daten, gesundheit] = await Promise.all([
        fetch(`/api/${art}`, { cache: 'no-store' }).then((a) => a.json()),
        fetch('/healthz', { cache: 'no-store' }).then((a) => a.json()),
      ]);
      if (typeof gesundheit.stale_after_s === 'number') stale_after = gesundheit.stale_after_s;
      setzeAlter(gesundheit[feldAlter]);
      aufDaten(daten);
    } catch (fehler) {
      console.warn('konnte den Stand nicht holen', fehler);
    }
  }

  hole();
  verbinde();
  window.setInterval(zeigeAlter, 5000);
  window.setInterval(hole, POLL_MS);
  // Ein Handy, das zwanzig Minuten in der Tasche lag, kommt mit einer toten
  // Verbindung zurück, ohne je ein `error` geliefert zu haben.
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState !== 'visible') return;
    hole();
    verbinde();
  });

  return { aktuellesAlter, verbinde, schliesse };
}

function dauer(sekunden) {
  const minuten = Math.floor(sekunden / 60);
  if (minuten < 1) return `${Math.round(sekunden)} Sekunden`;
  if (minuten === 1) return 'einer Minute';
  if (minuten < 60) return `${minuten} Minuten`;
  const stunden = Math.floor(minuten / 60);
  return stunden === 1 ? 'einer Stunde' : `${stunden} Stunden`;
}
