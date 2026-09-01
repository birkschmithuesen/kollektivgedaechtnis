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

## Sucherrahmen und Vorschau (für Testreihen)

Die App zeigt **im Sucher** einen goldenen Kreis: so beschneidet die Station
am Ende. Außen abgedunkelt ist, was wegfällt; der dünne Ring markiert die
Kopfhöhe. Der Rahmen bildet den **mittigen Rückfallweg** ab — findet die
Station ein Gesicht, wird der Ausschnitt enger, der Kreis ist dann die
sichere Untergrenze.

**Nach dem Auslösen** erscheint unten links das fertige Portrait, wie es die
Station zugeschnitten hat (antippen blendet es weg). Das ist das **echte**
Bild von der Station, keine Nachbildung — die Station nennt in ihrer Antwort
den Dateinamen, die App holt es über `/media/portraits/<name>`.

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
