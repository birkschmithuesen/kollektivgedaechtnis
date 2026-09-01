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
        object Erfolg : Ergebnis()
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
                in 200..299 -> Ergebnis.Erfolg
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
            Ergebnis.Fehler("Keine Verbindung zu ${ziel.host} — läuft die Station?")
        } catch (e: java.net.UnknownHostException) {
            Ergebnis.Fehler("Adresse ${ziel.host} nicht auflösbar")
        } catch (e: Exception) {
            Ergebnis.Fehler(e.message ?: e.javaClass.simpleName)
        } finally {
            verbindung?.disconnect()
        }
    }
}
