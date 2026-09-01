package art.artesmobiles.kg

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.nio.ByteBuffer

/**
 * Was am Booth wirklich schiefgehen kann.
 *
 * Keine Kamera-Tests: die Aufnahme selbst gehört CameraX, und eine Attrappe
 * davon würde nur beweisen, dass die Attrappe funktioniert. Getestet wird,
 * was WIR entschieden haben — die Adressauflösung, die Byte-Entnahme und die
 * Übersetzung jeder Antwort in einen Satz, der im Flur weiterhilft.
 */
class UploaderTest {

    // --- endpunkt(): was Menschen in ein Adressfeld tippen -------------------

    @Test
    fun `blosse ip bekommt schema port und pfad`() {
        assertEquals(
            "http://100.75.24.33:8800/api/photo",
            Uploader.endpunkt("100.75.24.33").toString()
        )
    }

    @Test
    fun `angegebener port gewinnt gegen den standard`() {
        assertEquals(
            "http://100.75.24.33:9000/api/photo",
            Uploader.endpunkt("100.75.24.33:9000").toString()
        )
    }

    @Test
    fun `vollstaendige url mit schrägstrich funktioniert ebenso`() {
        assertEquals(
            "http://station:8800/api/photo",
            Uploader.endpunkt("http://station:8800/").toString()
        )
    }

    @Test
    fun `https bleibt https`() {
        assertTrue(Uploader.endpunkt("https://kg.example.org").protocol == "https")
    }

    @Test
    fun `ein eingetippter pfad wird verworfen statt angehaengt`() {
        // Sonst ergäbe „…:8800/api" plus „/api/photo" ein „/api/api/photo",
        // und der Fehler fiele erst am Ausstellungstag auf.
        assertEquals(
            "http://100.75.24.33:8800/api/photo",
            Uploader.endpunkt("http://100.75.24.33:8800/api").toString()
        )
    }

    // --- Die beiden Wege ---------------------------------------------------

    @Test
    fun `der spiegel bekommt seinen eigenen pfad`() {
        assertEquals(
            "https://kollektivgedaechtnis.flashclash.de/ingest/photo",
            Uploader.endpunkt(
                "https://kollektivgedaechtnis.flashclash.de", "/ingest/photo"
            ).toString()
        )
    }

    @Test
    fun `https bekommt keinen stationsport angehaengt`() {
        // Der Spiegel laeuft auf 443 hinter nginx. Ein angehaengtes :8800
        // liefe ins Leere -- mit einer Zeitueberschreitung, die wie
        // „Station aus" aussieht statt wie ein Konfigurationsfehler.
        val url = Uploader.endpunkt("https://kg.example.org", "/ingest/photo")
        assertTrue("Port faelschlich gesetzt: ${url.port}", url.port == -1)
        assertEquals("https://kg.example.org/ingest/photo", url.toString())
    }

    @Test
    fun `ein token wird als bearer mitgeschickt`() {
        var gesehen: String? = "nicht gesetzt"
        Uploader.sende(URL("https://x/ingest/photo"), byteArrayOf(1), token = "geheim") {
            object : HttpURLConnection(it) {
                override fun connect() {}
                override fun disconnect() {}
                override fun usingProxy() = false
                override fun getOutputStream() = ByteArrayOutputStream()
                override fun getResponseCode() = 200
                override fun setRequestProperty(key: String, value: String) {
                    if (key == "Authorization") gesehen = value
                }
            }
        }
        assertEquals("Bearer geheim", gesehen)
    }

    @Test
    fun `ohne token wird kein authorization kopf gesetzt`() {
        // Der Station im Tailnet darf nie ein Token geschickt werden -- sie
        // kennt keines, und ein Kopf, den niemand prueft, verleitet dazu,
        // spaeter einen dort zu erwarten.
        var gesehen: String? = null
        Uploader.sende(URL("http://x:8800/api/photo"), byteArrayOf(1), token = null) {
            object : HttpURLConnection(it) {
                override fun connect() {}
                override fun disconnect() {}
                override fun usingProxy() = false
                override fun getOutputStream() = ByteArrayOutputStream()
                override fun getResponseCode() = 200
                override fun setRequestProperty(key: String, value: String) {
                    if (key == "Authorization") gesehen = value
                }
            }
        }
        assertNull(gesehen)
    }

    @Test
    fun `ein abgelehntes token wird beim namen genannt`() {
        val ergebnis = Uploader.sende(URL("https://x/ingest/photo"), byteArrayOf(1)) {
            attrappe(401)
        }
        val text = (ergebnis as Uploader.Ergebnis.Fehler).text
        assertTrue(text.contains("Token"))
    }

    @Test
    fun `ein voller eingang wird beim namen genannt`() {
        val ergebnis = Uploader.sende(URL("https://x/ingest/photo"), byteArrayOf(1)) {
            attrappe(429)
        }
        val text = (ergebnis as Uploader.Ergebnis.Fehler).text
        assertTrue(text.contains("voll"))
    }

    // --- Das Token, wie es wirklich aufs Geraet kommt ----------------------

    @Test
    fun `ein kopiertes token verliert seinen leerraum`() {
        // Aus einer Terminalausgabe kopiert haengt regelmaessig ein
        // Zeilenumbruch dran. Ohne Bereinigung ergibt das 401 -- und das
        // sieht wie ein Serverfehler aus, nicht wie ein Kopierfehler.
        // Niemand sieht einem Eingabefeld an, dass hinten ein \n steht.
        val roh = " abc-def_123\n"
        assertEquals("abc-def_123", roh.filterNot { it.isWhitespace() })
    }

    @Test
    fun `leerraum mitten im token faellt ebenfalls weg`() {
        // `trim()` allein wuerde das nicht fangen -- deshalb filterNot.
        assertEquals("abcdef", "ab c\tdef".filterNot { it.isWhitespace() })
    }

    @Test
    fun `leerzeichen ringsum stoeren nicht`() {
        assertEquals(
            "http://100.75.24.33:8800/api/photo",
            Uploader.endpunkt("  100.75.24.33  ").toString()
        )
    }

    @Test(expected = IllegalArgumentException::class)
    fun `eine leere adresse wird abgewiesen`() {
        Uploader.endpunkt("   ")
    }

    // --- Bildbytes: der stille Datenfehler ---------------------------------
    //
    // Nur `ausBuffer` wird hier geprueft. `verkleinere` braucht Androids
    // Bitmap/BitmapFactory und liefert auf der blanken JVM nur Attrappenwerte
    // -- ein Test dagegen wuerde die Attrappe pruefen, nicht das Verkleinern.
    // Diese Luecke ist bewusst und benannt: belegt ist sie am Geraet (Groesse
    // in der Statuszeile) und an der Station (Byteszahl im Log).

    @Test
    fun `nur die belegten bytes werden gelesen, nicht der ganze puffer`() {
        // Der eigentliche Grund für Bildbytes: ein ByteBuffer mit Kapazität 64
        // und 3 belegten Bytes darf 3 Bytes liefern, nicht 64.
        val puffer = ByteBuffer.allocate(64)
        puffer.put(byteArrayOf(0xFF.toByte(), 0xD8.toByte(), 0xFF.toByte()))
        puffer.flip()

        val bytes = Bildbytes.ausBuffer(puffer)

        assertEquals(3, bytes.size)
        assertEquals(0xFF.toByte(), bytes[0])
    }

    @Test
    fun `ein bereits gelesener puffer liefert trotzdem das ganze bild`() {
        // Ohne rewind() käme hier ein leeres Array zurück — ein abgeschnittenes
        // Foto ohne jede Fehlermeldung.
        val puffer = ByteBuffer.wrap(byteArrayOf(1, 2, 3, 4))
        puffer.get()  // Position steht jetzt auf 1

        assertEquals(4, Bildbytes.ausBuffer(puffer).size)
    }

    // --- sende(): jede Antwort wird zu einem brauchbaren Satz ---------------

    private fun attrappe(code: Int, gesendet: ByteArrayOutputStream = ByteArrayOutputStream()) =
        object : HttpURLConnection(URL("http://x:8800/api/photo")) {
            override fun connect() {}
            override fun disconnect() {}
            override fun usingProxy() = false
            override fun getOutputStream() = gesendet
            override fun getResponseCode() = code
        }

    @Test
    fun `zweihundert ist erfolg`() {
        val ergebnis = Uploader.sende(URL("http://x:8800/api/photo"), byteArrayOf(1, 2)) {
            attrappe(200)
        }
        assertTrue(ergebnis is Uploader.Ergebnis.Erfolg)
    }

    @Test
    fun `die bytes kommen unveraendert an`() {
        val gesendet = ByteArrayOutputStream()
        val jpeg = byteArrayOf(0xFF.toByte(), 0xD8.toByte(), 7, 9)

        Uploader.sende(URL("http://x:8800/api/photo"), jpeg) { attrappe(200, gesendet) }

        assertTrue(jpeg.contentEquals(gesendet.toByteArray()))
    }

    @Test
    fun `vierhundertvier nennt die alte fassung beim namen`() {
        // Der wahrscheinlichste Fehler beim ersten Einsatz: das Ziel läuft,
        // hat den Endpunkt aber noch nicht (siehe „git log auf dem
        // Ausstellungsrechner" im Handoff). Der Text nennt seit dem
        // Spiegel-Weg keinen festen Pfad mehr — es gibt zwei —, muss aber
        // weiterhin auf die veraltete Fassung zeigen.
        val ergebnis = Uploader.sende(URL("http://x:8800/api/photo"), byteArrayOf(1)) {
            attrappe(404)
        }
        val text = (ergebnis as Uploader.Ergebnis.Fehler).text
        assertTrue(text, text.contains("Fassung"))
    }

    @Test
    fun `jeder fehlercode ergibt einen text und wirft nie`() {
        for (code in listOf(400, 413, 415, 422, 500, 503)) {
            val ergebnis = Uploader.sende(URL("http://x:8800/api/photo"), byteArrayOf(1)) {
                attrappe(code)
            }
            val fehler = ergebnis as Uploader.Ergebnis.Fehler
            assertTrue("Code $code ohne Text", fehler.text.isNotBlank())
        }
    }

    @Test
    fun `eine unerreichbare station nennt host und port statt einer ausnahme`() {
        // Der häufigste Fall im Flur: Handy nicht im Tailnet. Die App darf
        // dabei nicht abstürzen, sondern muss sagen, wohin sie wollte.
        val ergebnis = Uploader.sende(URL("http://x:8800/api/photo"), byteArrayOf(1)) {
            throw java.net.ConnectException("refused")
        }
        val text = (ergebnis as Uploader.Ergebnis.Fehler).text
        assertTrue(text.contains("x"))
        assertTrue(text.contains("8800"))
    }

    @Test
    fun `eine zeitueberschreitung weist aufs tailnet hin`() {
        val ergebnis = Uploader.sende(URL("http://station:8800/api/photo"), byteArrayOf(1)) {
            throw java.net.SocketTimeoutException("timeout")
        }
        val text = (ergebnis as Uploader.Ergebnis.Fehler).text
        assertTrue(text.contains("Tailnet"))
    }

    // --- schalte(): Interview per Handy starten und beenden ------------------

    @Test
    fun `der schalter schickt den gewuenschten zustand als json`() {
        // 🔴 Absolut ("on": true/false) und nicht "umschalten": ginge eine
        // Anfrage verloren, liefe ein Umschalter dauerhaft gegenphasig zur
        // Station. Ein absoluter Wert kann hoechstens wirkungslos sein.
        val gesendet = ByteArrayOutputStream()
        Uploader.schalte(URL("http://x:8800/api/interview_switch"), an = true) {
            attrappe(200, gesendet)
        }
        val koerper = gesendet.toString("UTF-8")
        assertTrue(koerper, koerper.contains("\"on\":true"))
        // `source` unterscheidet in den Logs Handy von Mikrofonschalter --
        // sonst ist im Nachhinein nicht klaerbar, wer geschaltet hat.
        assertTrue(koerper, koerper.contains("handy"))
    }

    @Test
    fun `beenden schickt on false`() {
        val gesendet = ByteArrayOutputStream()
        Uploader.schalte(URL("http://x:8800/api/interview_switch"), an = false) {
            attrappe(200, gesendet)
        }
        assertTrue(gesendet.toString("UTF-8").contains("\"on\":false"))
    }

    @Test
    fun `der schalter meldet sich als json an`() {
        // Ohne diesen Kopf antwortet FastAPI mit 422, und die Meldung im Flur
        // waere "Station antwortet mit 422" -- richtig, aber unbrauchbar.
        var gesehen: String? = null
        Uploader.schalte(URL("http://x:8800/api/interview_switch"), an = true) {
            object : HttpURLConnection(it) {
                override fun connect() {}
                override fun disconnect() {}
                override fun usingProxy() = false
                override fun getOutputStream() = ByteArrayOutputStream()
                override fun getResponseCode() = 200
                override fun setRequestProperty(key: String, value: String) {
                    if (key == "Content-Type") gesehen = value
                }
            }
        }
        assertEquals("application/json", gesehen)
    }

    @Test
    fun `eine station ohne schalter wird als alte fassung benannt`() {
        val ergebnis = Uploader.schalte(URL("http://x:8800/api/interview_switch"), an = true) {
            attrappe(404)
        }
        val text = (ergebnis as Uploader.Ergebnis.Fehler).text
        assertTrue(text, text.contains("alte Fassung"))
    }
}
