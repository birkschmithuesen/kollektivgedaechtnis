# Foto-App für Android (`android/`)

Eine App mit genau einer Aufgabe: **ein Foto machen und es an die Station
schicken.** Kein Store, kein Konto, keine Anmeldung — APK aufs Handy, fertig.

Sie ersetzt am Booth den Weg über Telegram. **Telegram bleibt daneben
bestehen** (`kg/telegram_bot.py`): zwei Einwürfe, damit der Ausfall des einen
die Station nicht stilllegt.

## Warum nicht einfach weiter Telegram

| | Telegram | App (Weg A) |
|---|---|---|
| Weg des Fotos | Handy → Telegram-Server → Poller → Station | Handy → Station |
| Braucht Internet | ja | **nein**, nur das Tailnet |
| Verzögerung | Poll-Intervall (Sekunden) | direkt |
| Fremdinfrastruktur | ja | **keine** |

Der letzte Punkt ist der inhaltliche: die Station handelt von
Datensouveränität und verlinkt eine Transparenzseite. Ein Portraitfoto über
einen US-Messenger zu schicken, um es an eine EU-souveräne Pipeline zu
übergeben, wäre der Widerspruch im eigenen Aufbau.

## Interview starten und beenden (seit 2026-09-01)

Unter dem Auslöser sitzt ein zweiter, flacherer Knopf: **Interview starten**
bzw. **Interview beenden**. Er tut genau dasselbe wie der Schalter am Mikrofon
(`POST /api/interview_switch`) — bewusst derselbe Endpunkt und kein eigener,
damit sich die beiden Wege nicht auseinanderentwickeln.

**Der Knopf rät nicht.** Die App fragt alle drei Sekunden `GET /api/state` und
richtet Beschriftung und Freigabe danach. Das ist nötig, weil ein Interview
auch anders enden kann — am Mikrofonschalter, durch die gesprochene
Schlussphrase, durch den Timeout. Ohne Nachfrage stünde das Handy dann auf
„läuft" und der nächste Druck beendete etwas längst Beendetes.

Ist die Station nicht erreichbar, wird der Knopf **gesperrt** statt geraten.
Ein Umschalter, der den Stand nicht kennt, macht im Zweifel das Gegenteil.

**Nur über den direkten Weg.** Der öffentliche Spiegel nimmt Fotos entgegen
und sonst nichts — er ist die Fassade nach draußen und darf die Station nicht
steuern. Im Spiegel-Modus ist der Knopf deshalb aus.

### 🔴 Ein Foto eröffnet kein Interview mehr

Bis zum 2026-09-01 war das Foto der Anfang eines Besuchs. Heute ist der Anfang
eine bewusste Handlung am Schalter. Ein Foto kann nur noch drei Dinge tun:

| Lage | Was passiert |
|---|---|
| Interview läuft, ohne Portrait | Bild wird nachgereicht (`late_photo`) |
| Interview läuft, mit Portrait | Bild **ersetzt** das bisherige (`replaced_photo`) |
| Interview **beendet** | Bild geht an die **zuletzt begonnene** Person — auch wenn sie schon mit Begriffen an der Wand hängt |
| noch **nie** ein Interview | **abgewiesen** (HTTP 409), keine Datei entsteht |

Der Grund ist der Betrieb am Booth: Dort wird probiert und nachjustiert.
Solange jedes Foto ein Interview eröffnete, erzeugte jeder Probeauslöser eine
Person an der Wand, die nie etwas gesagt hat — und ein zweites Foto während
eines Gesprächs zerschnitt dieses in zwei Personen.

**Letzte Aufnahme gewinnt — aber immer nur beim letzten Interview.** Ein Bild
lässt sich auch nach dem Gespräch noch tauschen (der häufige Fall: erst an der
Wand sieht man, dass es nichts taugt). Es trifft dabei **nie** eine ältere
Person: `Store.latest_person()` hält diese Regel, es gibt am Booth also keinen
Weg, einem längst gegangenen Gast ein fremdes Gesicht zu geben. Das ersetzte
Bild bleibt als Datei liegen — es ist der Vorrat, aus dem der noch ungebaute
Auswahl-Cache einmal wählen wird (`docs/HANDOFF-alternativ-foto-cache.md`).

Was dabei **nicht** passiert: Das Interview wird nicht wiedereröffnet, seine
Begriffe werden nicht neu berechnet, `stopped_at` bleibt stehen. Und die App
schließt aus einer angenommenen 200 **nicht** mehr, dass ein Interview läuft —
sie fragt nach.

Die App zeigt bei 409 „Noch kein Interview — zuerst unten Interview starten".

## Sucherrahmen und Vorschau (für Testreihen)

Die App zeigt **im Sucher** einen goldenen Kreis: so beschneidet die Station
am Ende. Außen abgedunkelt ist, was wegfällt; der dünne Ring markiert die
Kopfhöhe. Der Rahmen bildet den **mittigen Rückfallweg** ab — findet die
Station ein Gesicht, wird der Ausschnitt enger, der Kreis ist dann die
sichere Untergrenze.

**Nach dem Auslösen** erscheint das fertige Portrait **formatfüllend** über
dem Sucher, wie es die Station zugeschnitten hat (antippen blendet es weg).
Das ist das **echte** Bild von der Station, keine Nachbildung — die Station
nennt in ihrer Antwort den Dateinamen, die App holt es über
`/media/portraits/<name>`.

> Bis einschließlich **v6** hing die Vorschau als 140dp-Kachel in der Ecke.
> Vollbild gilt ab **v7** (Layout-Änderung vom 2026-09-01, Commit `7fd4425`).
> Wer eine Kachel sieht, hat ein altes APK installiert — nicht im Code suchen,
> sondern die Version prüfen (siehe unten).

## 🔴 Welche Version liegt auf dem Telefon?

Der häufigste Fehlschluss bei dieser App: Der Quellcode ist längst richtig,
das **APK auf dem Gerät** ist alt. Am 2026-09-01 lief so eine Meldung auf
(„zeigt das Foto nur klein"), obwohl die Änderung seit Stunden auf `master`
lag — nur eben nicht auf dem Handy.

Am Gerät: *Einstellungen → Apps → Kollektivgedächtnis Foto*. Die
`versionName` steht bei allen Builds auf `1.0` und **hilft nicht weiter** —
sie unterscheidet die Stände nicht. Verlässlich ist nur das Datum unter
„App-Details" gegen die Bauzeit des APK.

Aus einem vorliegenden APK lässt sich der Stand ohne Android-Werkzeuge
ablesen — das Layout steckt als Binär-XML drin:

```bash
uv run python scripts/apk-layout-lesen.py out/kollektivgedaechtnis-foto-v8.apk
```

`layout_width: 140dip` beim `ImageView` heißt Kachel (v6 und älter),
`0dip` heißt Vollbild (ab v7).

**Drüberinstallieren geht.** Alle Builds tragen dasselbe Debug-Zertifikat
(SHA-256 `b1f145d4…`, nachgemessen 2026-09-01) — Android nimmt das Update an,
ohne dass die alte App deinstalliert werden muss. Wäre es ein anderer
Schlüssel, bräche die Installation mit „App nicht installiert" ab.

**Wo das APK liegt:** in der RoboCloud unter
`Hermes-Agent/RoboCloud/NewBauhaus-2026-Interviews/`. Das ist der einzige
Ort, an den das Telefon herankommt — `out/` liegt bewusst nicht im Git
(Binaries), war deshalb aber auch für niemanden erreichbar. **Wer ein neues
APK baut, lädt es dorthin hoch, sonst ist es gebaut und nicht ausgeliefert.**

Über den **Spiegel-Weg gibt es keine Vorschau**: dort entsteht das Portrait
erst beim Abholen. Kein Fehler.

Details, Messwerkzeug und die offenen Fragen zur Gesichtserkennung:
[`../docs/HANDOFF-fototest-zuschnitt.md`](../docs/HANDOFF-fototest-zuschnitt.md).

## Was am Ausstellungstag einzurichten ist
1. **Handy ins Tailnet.** Tailscale-App installieren, mit demselben Konto
   anmelden wie die Station. Ohne das findet die App nichts.
2. **APK installieren.** Datei aufs Handy kopieren, antippen, „Installation
   aus unbekannter Quelle" bestätigen.
3. **Adresse eintragen.** Zahnrad oben rechts → die Tailnet-Adresse des
   Ausstellungsrechners (`tailscale ip -4` dort ablesen). Port 8800 wird
   angenommen, wenn keiner dabeisteht.
4. **Einmal auslösen und die Wand ansehen.** Erscheint der Portraitknoten,
   steht die Kette.

## Die Station muss von außen erreichbar sein

Standard ist `server_host = "127.0.0.1"` (`kg/config.py`) — dann antwortet
die Station **nur sich selbst** und die App bekommt „keine Verbindung".

In der `config.toml` des Ausstellungsrechners:

```toml
server_host = "0.0.0.0"
```

Das ist vertretbar, weil die Station im Tailnet steht und nicht im offenen
Netz; wer sie zusätzlich ins Venue-WLAN hängt, sollte es wieder zurückdrehen.

## Was die App absichtlich nicht kann

- **Nichts speichern.** Kein Galerie-Zugriff, keine Speicherberechtigung,
  keine Warteschlange. Das Foto entsteht, geht raus, ist weg. Eine App, die
  nichts aufhebt, kann nichts verlieren — und hinterlässt auf einem
  geliehenen Handy keine Portraits.
- **Nicht nachreichen.** Schlägt das Senden fehl, sagt sie das und man löst
  erneut aus. Eine Warteschlange würde Fotos später einspielen, wenn längst
  jemand anderes im Booth sitzt — das falsche Portrait am falschen Interview.
- **Nicht zuschneiden.** Das Portrait entsteht auf der Station
  (`kg/photos.py`, inklusive Gesichtserkennung und Goldring). Zwei Orte für
  dieselbe Entscheidung wären zwei Orte zum Auseinanderlaufen.

## Bauen

Der vServer kommt hinter der Egress-Allowlist **nicht** an Googles und
Gradles Server (gemessen 2026-09-01: `dl.google.com`, `services.gradle.org`,
`repo.maven.apache.org` alle Zeitüberschreitung, während `github.com`
antwortet). Die Allowlist dafür aufzureißen wäre falsch — das sind rotierende
Shared-IPs von Cloudflare und Google. Gebaut wird deshalb auf **herkules**:

```bash
rsync -a --delete android/ fundusbot@91.98.143.165:~/kg-android/
ssh fundusbot@91.98.143.165 '
  export JAVA_HOME=$(ls -d ~/toolchains/jdk-17* | head -1)
  export PATH=$JAVA_HOME/bin:$PATH
  export ANDROID_HOME=$HOME/toolchains/android-sdk
  cd ~/kg-android && echo "sdk.dir=$ANDROID_HOME" > local.properties
  ~/toolchains/gradle-8.9/bin/gradle --no-daemon testDebugUnitTest assembleRelease'
scp fundusbot@91.98.143.165:~/kg-android/app/build/outputs/apk/release/app-release.apk .
```

Das APK ist mit dem **Debug-Schlüssel** signiert. Für eine
Seitenlade-Installation reicht das; ein Release-Keystore müsste verwahrt
werden und kauft für zwei Ausstellungstage nichts.

🔴 **Nach dem Bauen ausliefern, sonst war es umsonst.** Das APK landet in
`out/`, und `out/` ist nicht im Git — es ist damit für kein Telefon
erreichbar. Zwei Schritte gehören zum Bauen dazu:

```bash
cp app-release.apk out/kollektivgedaechtnis-foto-vN.apk
rclone copy out/kollektivgedaechtnis-foto-vN.apk \
  hermes-vault:Hermes-Agent/RoboCloud/NewBauhaus-2026-Interviews/
```

Am 2026-09-01 fehlte genau das: v7 und v8 waren gebaut, lagen aber nur auf
dem vServer. Auf dem Telefon blieb v6, und die Vollbild-Vorschau schien nicht
zu funktionieren — obwohl sie seit Stunden im Code stand.

**Ein Build ist erst fertig, wenn er neuer ist als der letzte Commit.**
Ebenfalls am 2026-09-01: v8 wurde um 16:09 gebaut, `51d615b` änderte
`Bildbytes.kt` um 16:11. v8 trug deshalb noch `MAX_KANTE = 1024` statt 1600 —
ein Build, der bereits beim Entstehen veraltet war. Vor dem Ausliefern:

```bash
git log -1 --format=%ai -- android/     # letzte Quelländerung
ls -l --time-style=full-iso out/*.apk   # Bauzeit
```

## Wenn es im Flur klemmt

Die Statuszeile nennt den Fall beim Namen — sie ist der Diagnoseweg, nicht
Beiwerk:

| Meldung | Ursache |
|---|---|
| „Station antwortet nicht — im Tailnet?" | Handy nicht im Tailnet, oder Tailscale schläft |
| „Keine Verbindung zu …" | Station läuft nicht, oder `server_host` steht auf `127.0.0.1` |
| „…kennt aber /api/photo nicht" | Auf dem Ausstellungsrechner läuft eine ältere Fassung → `git pull` |
| „Station konnte das Bild nicht lesen" | Beschädigte Aufnahme, erneut auslösen |

Der dritte Fall ist der wahrscheinlichste beim ersten Einsatz und der Grund,
warum er einen eigenen Text hat: am 2026-09-01 stand der Ausstellungsrechner
28 Commits hinter `master`, und ein fertiges Feature war dort schlicht nicht
vorhanden. **Bei „tut nichts" immer zuerst `git log --oneline -1` auf dem
Ausstellungsrechner.**
