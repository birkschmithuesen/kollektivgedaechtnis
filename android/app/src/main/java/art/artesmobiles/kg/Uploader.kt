package art.artesmobiles.kg

import java.net.HttpURLConnection
import java.net.URL

/**
 * Der Weg vom Auslöser zur Station: ein POST mit rohen JPEG-Bytes.
 *
 * Bewusst `HttpURLConnection` und keine HTTP-Bibliothek. Es geht um genau
 * einen Aufruf ohne Auth, ohne Wiederholungslogik und ohne JSON; OkHttp o.ä.
 * wären 1,5 MB APK für nichts. Weniger Abhängigkeiten heißt hier auch: kein
 * Bibliotheks-Update, das eine zweitägige Ausstellung überraschen kann.
 */
object Uploader {

    /** Was der Auslöser danach anzeigt. Kein Werfen: die Station steht im Flur. */
    sealed class Ergebnis {
        /**
         * `portrait` ist der Dateiname des fertigen Portraits, wenn die
         * Station einen genannt hat — nur der direkte Weg tut das. Über den
         * Spiegel ist er `null`: dort wird das Foto erst später abgeholt, das
         * Portrait entsteht also noch gar nicht.
         */
        data class Erfolg(val portrait: String? = null) : Ergebnis()
        data class Fehler(val text: String) : Ergebnis()
    }

    /**
     * Baut die Ziel-URL aus dem, was in den Einstellungen steht.
     *
     * Menschen tippen „100.75.24.33“, „100.75.24.33:8800“ oder
     * „http://station:8800/“ — alle drei müssen funktionieren, sonst
     * scheitert die Einrichtung im Flur an einem fehlenden Schrägstrich.
     *
     * Der Pfad wird IMMER hier angehängt und nie eingegeben: ein
     * halb-eingetippter Pfad ist die häufigste Fehlerquelle bei so einem
     * Feld, und der Endpunkt ist nichts, was der Betreiber wissen muss.
     *
     * `pfad` unterscheidet die beiden Wege: `/api/photo` direkt an die
     * Station, `/ingest/photo` an den öffentlichen Spiegel.
     *
     * **Kein Standardport bei https.** Der Spiegel läuft auf 443 hinter
     * nginx; würde hier 8800 angehängt, liefe die Anfrage ins Leere — und
     * zwar mit einer Zeitüberschreitung, die wie „Station aus“ aussieht.
     */
    fun endpunkt(basis: String, pfad: String = "/api/photo", standardPort: Int = 8800): URL {
        var s = basis.trim()
        require(s.isNotEmpty()) { "Adresse ist leer" }

        if (!s.startsWith("http://") && !s.startsWith("https://")) {
            s = "http://$s"
        }
        // Ein eingetippter Pfad wird verworfen, nicht angehängt: „…:8800/api“
        // plus „/api/photo“ ergäbe sonst „/api/api/photo“.
        val url = URL(s)
        val port = when {
            url.port != -1 -> url.port
            url.protocol == "https" -> -1  // 443, vom Protokoll
            else -> standardPort
        }
        return URL(url.protocol, url.host, port, pfad)
    }

    /**
     * Schickt die Bytes und übersetzt jeden Ausgang in einen Satz, der im
     * Flur weiterhilft.
     *
     * Die Fehlertexte sind Teil der Funktion, nicht Beiwerk: Wer am Booth
     * steht, muss aus der Meldung ablesen können, ob das Handy im falschen
     * Netz ist oder die Station nicht läuft — sonst wird jeder Ausfall zum
     * Anruf.
     *
     * `token` ist nur für den Spiegel-Weg gesetzt; an die Station im Tailnet
     * geht nie ein Token, weil sie keines kennt.
     */
    fun sende(
        ziel: URL,
        jpeg: ByteArray,
        token: String? = null,
        // 30 s statt 10: gemessen am 2026-09-01 dauerte ein grosses Foto ueber
        // eine Handyverbindung laenger als der alte Wert. Seit Bildbytes
        // verkleinert, sind es typisch unter 200 kB -- aber ein knapper
        // Timeout wuerde genau dann zuschlagen, wenn das Netz im Flur schwach
        // ist, also im ungeeignetsten Moment.
        timeoutMs: Int = 30_000,
        oeffne: (URL) -> HttpURLConnection = { it.openConnection() as HttpURLConnection },
    ): Ergebnis {
        var verbindung: HttpURLConnection? = null
        return try {
            verbindung = oeffne(ziel).apply {
                requestMethod = "POST"
                doOutput = true
                connectTimeout = timeoutMs
                readTimeout = timeoutMs
                setRequestProperty("Content-Type", "image/jpeg")
                if (token != null) setRequestProperty("Authorization", "Bearer $token")
                setFixedLengthStreamingMode(jpeg.size)
            }
            verbindung.outputStream.use { it.write(jpeg) }

            when (val code = verbindung.responseCode) {
                in 200..299 -> {
                    // Der Portraitname aus der Antwort, wenn einer dabei ist.
                    // Von Hand aus dem JSON gelesen statt mit einer Bibliothek:
                    // es ist EIN Feld, und org.json bringt Android ohnehin mit
                    // — eine Abhängigkeit dafür wäre Unsinn. Schlägt es fehl,
                    // ist der Upload trotzdem gelungen; die Vorschau ist eine
                    // Dreingabe, kein Teil des Auftrags.
                    val name = try {
                        val text = verbindung.inputStream.bufferedReader().use { it.readText() }
                        org.json.JSONObject(text).optString("portrait").ifBlank { null }
                    } catch (e: Exception) {
                        null
                    }
                    Ergebnis.Erfolg(name)
                }
                // Seit 2026-09-01: Die Station nimmt ein Foto nur zu einem
                // LAUFENDEN Interview an. Der Satz nennt deshalb die
                // Abhilfe und nicht den Fehler -- am Booth hilft "zuerst
                // starten" weiter, "409 Conflict" nicht.
                409 -> Ergebnis.Fehler("Kein Interview offen — zuerst unten Interview starten")
                401 -> Ergebnis.Fehler("Foto-Token fehlt oder stimmt nicht")
                413 -> Ergebnis.Fehler("Bild zu groß für die Station")
                415 -> Ergebnis.Fehler("Station hat das Bild nicht als Foto erkannt")
                422 -> Ergebnis.Fehler("Station konnte das Bild nicht lesen")
                429 -> Ergebnis.Fehler("Eingang voll — holt die Station gerade nicht ab?")
                404 -> Ergebnis.Fehler("Ziel antwortet, kennt den Weg aber nicht — alte Fassung?")
                else -> Ergebnis.Fehler("Station antwortet mit $code")
            }
        } catch (e: java.net.SocketTimeoutException) {
            Ergebnis.Fehler("Keine Antwort — im Tailnet? (${ziel.host})")
        } catch (e: java.net.ConnectException) {
            // Host UND Port: im Flur ist genau der Port die Sache, die falsch
            // steht (Station auf 8800, Spiegel auf 443), und ohne ihn ist die
            // Meldung nicht zu gebrauchen.
            Ergebnis.Fehler("Keine Verbindung zu ${ziel.host}:${ziel.port} — läuft die Station?")
        } catch (e: java.net.UnknownHostException) {
            Ergebnis.Fehler("Adresse ${ziel.host} nicht auflösbar")
        } catch (e: Exception) {
            Ergebnis.Fehler(e.message ?: e.javaClass.simpleName)
        } finally {
            verbindung?.disconnect()
        }
    }

    /**
     * Startet oder beendet ein Interview — derselbe Weg wie der Schalter am
     * Mikrofon (Birk, 2026-09-01: „analog zu dem Mikrofon an außen").
     *
     * Absichtlich `/api/interview_switch` und kein eigener Endpunkt: die
     * Station hat diesen Weg schon, samt Warteschlange und
     * `SessionTracker.mic_switch`. Ein zweiter Eingang mit derselben Wirkung
     * wäre ein zweiter Ort, an dem sich das Verhalten auseinanderentwickelt —
     * und der Fall „per Handy geöffnet, per Schlusssatz geschlossen" muss
     * genauso sauber laufen wie jede andere Mischung.
     *
     * `source` unterscheidet in den Logs, wer geschaltet hat. Das ist keine
     * Zierde: wenn im Nachhinein ein Interview ohne Portrait dasteht, ist die
     * erste Frage, ob jemand am Mikrofonschalter war oder am Handy.
     *
     * **Nur über den Tailnet-Weg.** Der öffentliche Spiegel kennt diesen
     * Endpunkt nicht (`mirror/receiver.py` nimmt Fotos entgegen und sonst
     * nichts) — er ist die Fassade nach draußen und darf die Station nicht
     * steuern können. Die App fängt das vorher ab.
     */
    fun schalte(
        ziel: URL,
        an: Boolean,
        timeoutMs: Int = 10_000,
        oeffne: (URL) -> HttpURLConnection = { it.openConnection() as HttpURLConnection },
    ): Ergebnis {
        var verbindung: HttpURLConnection? = null
        return try {
            val koerper = """{"on":$an,"source":"handy"}""".toByteArray()
            verbindung = oeffne(ziel).apply {
                requestMethod = "POST"
                doOutput = true
                connectTimeout = timeoutMs
                readTimeout = timeoutMs
                setRequestProperty("Content-Type", "application/json")
                setFixedLengthStreamingMode(koerper.size)
            }
            verbindung.outputStream.use { it.write(koerper) }
            when (val code = verbindung.responseCode) {
                in 200..299 -> Ergebnis.Erfolg()
                404 -> Ergebnis.Fehler("Station kennt den Schalter nicht — alte Fassung?")
                else -> Ergebnis.Fehler("Station antwortet mit $code")
            }
        } catch (e: java.net.SocketTimeoutException) {
            Ergebnis.Fehler("Keine Antwort — im Tailnet? (${'$'}{ziel.host})")
        } catch (e: java.net.ConnectException) {
            Ergebnis.Fehler("Keine Verbindung zu ${'$'}{ziel.host}:${'$'}{ziel.port} — läuft die Station?")
        } catch (e: Exception) {
            Ergebnis.Fehler(e.message ?: e.javaClass.simpleName)
        } finally {
            verbindung?.disconnect()
        }
    }

    /** Was die Station gerade tut. `null`-Felder heißen „nicht erreichbar". */
    data class Zustand(val interviewLaeuft: Boolean, val mikrofonAn: Boolean)

    /**
     * Fragt die Station, ob gerade ein Interview läuft.
     *
     * 🔴 Der Grund, warum es das gibt: Ohne Rückmeldung wäre der Knopf am
     * Handy ein Umschalter, der RÄT. Ein Interview kann auch per
     * Mikrofonschalter oder per gesprochener Schlussphrase enden — dann zeigte
     * das Handy weiter „läuft", und der nächste Druck würde beenden wollen,
     * was längst beendet ist. Birk: „damit der Stand von Interview läuft nicht
     * springt."
     *
     * Abgefragt statt zugeschickt: Die Station kann per SSE senden
     * (`/events`), aber eine offene Verbindung über ein Handy-WLAN, das beim
     * Sperren des Schirms wegbricht, ist der unzuverlässigere Weg — sie
     * stirbt still, und das Handy zeigt dann einen eingefrorenen Stand, ohne
     * es zu merken. Eine Abfrage alle paar Sekunden kann nicht still sterben:
     * bleibt sie aus, ist das sofort sichtbar.
     */
    fun holeZustand(basis: String, timeoutMs: Int = 5_000): Zustand? = try {
        val verbindung = endpunkt(basis, "/api/state").openConnection() as HttpURLConnection
        verbindung.connectTimeout = timeoutMs
        verbindung.readTimeout = timeoutMs
        try {
            if (verbindung.responseCode in 200..299) {
                val text = verbindung.inputStream.bufferedReader().use { it.readText() }
                val json = org.json.JSONObject(text)
                // `interview` ist ein Objekt, solange eins laeuft, und JSON-null
                // sonst. `isNull` statt `has`: der Schluessel ist IMMER da.
                Zustand(
                    interviewLaeuft = !json.isNull("interview"),
                    mikrofonAn = json.optBoolean("mic_on", true),
                )
            } else {
                null
            }
        } finally {
            verbindung.disconnect()
        }
    } catch (e: Exception) {
        null
    }

    /**
     * Holt ein fertiges Portrait zur Ansicht.
     *
     * Nur für die Vorschau nach dem Auslösen — der Rückgabewert ist absichtlich
     * `ByteArray?` und keine Ausnahme: bleibt das Bild aus, fehlt eine
     * Dreingabe, das Foto ist trotzdem angekommen. Ein Fehlschlag hier darf
     * nie wie ein fehlgeschlagener Upload aussehen.
     */
    fun holePortrait(basis: String, name: String, timeoutMs: Int = 15_000): ByteArray? = try {
        val verbindung = endpunkt(basis, "/media/portraits/$name")
            .openConnection() as HttpURLConnection
        verbindung.connectTimeout = timeoutMs
        verbindung.readTimeout = timeoutMs
        try {
            if (verbindung.responseCode in 200..299) {
                verbindung.inputStream.use { it.readBytes() }
            } else {
                null
            }
        } finally {
            verbindung.disconnect()
        }
    } catch (e: Exception) {
        null
    }
}
