package art.artesmobiles.kg

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.BitmapFactory
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.ImageButton
import android.widget.ImageView
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Die ganze App: Sucher, ein großer Auslöser, eine Statuszeile.
 *
 * Was sie NICHT tut, ist Absicht — kein Galerie-Zugriff, keine
 * Speicherberechtigung, keine Bildbearbeitung, keine Warteschlange. Das Foto
 * entsteht, geht raus, und wird vergessen. Alles Weitere passiert auf der
 * Station (`kg/photos.py` schneidet das Portrait, `Core.on_photo` eröffnet das
 * Interview). Eine App, die nichts speichert, kann auch nichts verlieren und
 * braucht am Ausstellungstag keine Pflege.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var einstellungen: Einstellungen
    private lateinit var status: TextView
    private lateinit var ausloeser: Button
    private lateinit var sucher: PreviewView
    private lateinit var vorschau: ImageView
    private lateinit var interviewKnopf: Button
    private lateinit var leuchte: AufnahmeLeuchte
    private lateinit var leiste: TextView
    private var aufnahme: ImageCapture? = null

    /** Verhindert, dass ein zweiter Druck ein zweites Interview eröffnet. */
    private var sendetGerade = false

    /**
     * Was die Station beim letzten Nachfragen gemeldet hat.
     *
     * `null` heißt „nicht erreichbar" und ist ausdrücklich ein dritter
     * Zustand, nicht ein „läuft nicht": Ein Umschalter, der den Stand nicht
     * kennt, macht im Zweifel das Gegenteil des Gewollten — deshalb wird der
     * Knopf dann gesperrt statt geraten.
     */
    private var interviewLaeuft: Boolean? = null

    /** Läuft, solange die App vorn ist. Siehe `beobachteZustand`. */
    private var beobachter: Job? = null

    private val kameraFreigabe = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { erteilt ->
        if (erteilt) starteKamera()
        else zeige(getString(R.string.keine_kamera_freigabe), fehler = true)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        einstellungen = Einstellungen(this)
        status = findViewById(R.id.status)
        ausloeser = findViewById(R.id.ausloeser)
        sucher = findViewById(R.id.sucher)
        vorschau = findViewById(R.id.vorschau)
        // Bis die erste Antwort der Station da ist, ist der Stand unbekannt —
        // und ein Knopf, dessen Beschriftung gleich umspringt, hat schon
        // jemanden zum Danebendrücken verleitet. Also erst sperren.
        interviewLaeuft = null

        // Antippen blendet die Vorschau weg — sie verdeckt einen Teil des
        // Suchers, und wer das nächste Foto machen will, soll sie loswerden,
        // ohne ein Menü zu suchen.
        vorschau.setOnClickListener {
            vorschau.visibility = View.GONE
            // Zurueck auf die Meldung, die ohne Vorschau gilt -- sonst bleibt
            // "antippen zum Schliessen" stehen, obwohl nichts mehr da ist.
            zeige(getString(R.string.gesendet), fehler = false)
        }

        ausloeser.setOnClickListener { schiesse() }
        interviewKnopf = findViewById(R.id.interview)
        interviewKnopf.setOnClickListener { schalteInterview() }
        leuchte = findViewById(R.id.leuchte)
        leiste = findViewById(R.id.leiste)
        findViewById<ImageButton>(R.id.einstellungen).setOnClickListener {
            startActivity(Intent(this, SettingsActivity::class.java))
        }

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
            == PackageManager.PERMISSION_GRANTED
        ) {
            starteKamera()
        } else {
            kameraFreigabe.launch(Manifest.permission.CAMERA)
        }
    }

    override fun onResume() {
        super.onResume()
        // Nach einer Änderung in den Einstellungen soll sofort sichtbar sein,
        // wohin die App jetzt schickt — die Adresse ist die einzige Sache,
        // die im Flur schiefgeht.
        zeige(getString(R.string.bereit, einstellungen.aktuellesZiel().first), fehler = false)
        beobachteZustand()
    }

    override fun onPause() {
        super.onPause()
        // 🔴 Die Abfrage MUSS hier enden. Ohne das liefe sie weiter, während
        // das Handy in der Tasche steckt — alle drei Sekunden eine Anfrage an
        // die Station, den ganzen Ausstellungstag lang, für eine Anzeige, die
        // niemand sieht. `lifecycleScope` allein rettet das nicht: der räumt
        // erst beim Beenden auf, nicht beim Wegschalten.
        beobachter?.cancel()
        beobachter = null
    }

    /**
     * Fragt die Station regelmäßig, ob ein Interview läuft.
     *
     * Der Grund für das Ganze (Birk, 2026-09-01): Der Knopf soll nicht raten.
     * Ein Interview kann auch am Mikrofonschalter oder durch die gesprochene
     * Schlussphrase enden — ohne Nachfrage stünde das Handy dann auf „läuft"
     * und der nächste Druck beendete etwas, das längst vorbei ist.
     *
     * Drei Sekunden sind ein Kompromiss aus zwei echten Kosten: Häufiger wäre
     * Funkverkehr für nichts (die App liegt am Booth oft nur herum),
     * seltener und der Knopf hinkte spürbar hinterher, wenn jemand nebenan am
     * Mikrofonschalter war.
     *
     * Über den Spiegel-Weg wird gar nicht erst gefragt: Dort gibt es weder
     * `/api/state` noch den Schalter, und eine Abfrage, die garantiert
     * scheitert, sähe drei Sekunden lang wie eine ausgefallene Station aus.
     */
    private fun beobachteZustand() {
        beobachter?.cancel()
        if (einstellungen.ziel != Einstellungen.Ziel.STATION) {
            interviewLaeuft = null
            zeigeZustand()
            return
        }
        beobachter = lifecycleScope.launch {
            while (isActive) {
                val adresse = einstellungen.stationsAdresse
                val zustand = withContext(Dispatchers.IO) { Uploader.holeZustand(adresse) }
                // Während gerade geschaltet oder gesendet wird, NICHT
                // überschreiben: die Station braucht einen Moment, bis sich
                // der neue Stand in `/api/state` zeigt, und eine Antwort von
                // vorher würde den Knopf kurz zurückspringen lassen — genau
                // das Flackern, das Birk nicht will.
                if (!sendetGerade) {
                    interviewLaeuft = zustand?.interviewLaeuft
                    zeigeZustand()
                }
                delay(3_000)
            }
        }
    }

    /** Bringt Leuchte, Knopfbeschriftung und Freigabe auf den zuletzt
     * bekannten Stand.
     *
     * 🔴 Leuchte und Knopf lesen DIESELBE Variable (Birk, 2026-09-02: „so,
     * dass es ganz eindeutig ist"). Zwei Quellen waeren der Weg, auf dem
     * beide irgendwann Verschiedenes behaupten -- und dann glaubt man dem
     * Falschen. Deshalb steht hier eine Funktion und nicht zwei.
     */
    private fun zeigeZustand() {
        val laeuft = interviewLaeuft
        zeigeLeuchte(laeuft)
        when {
            einstellungen.ziel != Einstellungen.Ziel.STATION -> {
                interviewKnopf.isEnabled = false
                interviewKnopf.text = getString(R.string.interview_starten)
            }
            laeuft == null -> {
                // Unbekannt: sperren statt raten.
                interviewKnopf.isEnabled = false
                interviewKnopf.text = getString(R.string.interview_starten)
            }
            else -> {
                interviewKnopf.isEnabled = !sendetGerade
                interviewKnopf.text = getString(
                    if (laeuft) R.string.interview_beenden else R.string.interview_starten
                )
            }
        }
    }

    /**
     * Die Leuchte ganz oben: rot blinkend, wenn aufgezeichnet wird.
     *
     * Dreiwertig und ausdruecklich nicht an/aus. „Station nicht erreichbar"
     * als „aus" darzustellen waere die gefaehrlichste Luege, die diese
     * Anzeige erzaehlen koennte: Jemand verliesse sich darauf, dass nichts
     * aufgezeichnet wird, obwohl die App es schlicht nicht weiss.
     *
     * Der Text steht NEBEN der Leuchte, nicht statt ihrer. Die Leuchte wirkt
     * aus dem Augenwinkel, waehrend man mit einem Gast redet; das Wort ist
     * fuer den Moment, in dem jemand tatsaechlich hinsieht -- und fuer alle,
     * die Rot und Grau nicht sicher unterscheiden.
     */
    private fun zeigeLeuchte(laeuft: Boolean?) {
        // Ueber den Spiegel gibt es keinen Interview-Zustand: Der Spiegel
        // nimmt Fotos an und kennt `/api/state` nicht. „Unbekannt" ist dort
        // also nicht die Ausnahme, sondern die Wahrheit.
        val zustand = when {
            einstellungen.ziel != Einstellungen.Ziel.STATION ->
                AufnahmeLeuchte.Zustand.UNBEKANNT
            laeuft == null -> AufnahmeLeuchte.Zustand.UNBEKANNT
            laeuft -> AufnahmeLeuchte.Zustand.LAEUFT
            else -> AufnahmeLeuchte.Zustand.AUS
        }
        leuchte.setZustand(zustand)
        leiste.text = getString(
            when (zustand) {
                AufnahmeLeuchte.Zustand.LAEUFT -> R.string.led_laeuft
                AufnahmeLeuchte.Zustand.AUS -> R.string.led_aus
                AufnahmeLeuchte.Zustand.UNBEKANNT -> R.string.led_unbekannt
            }
        )
        leiste.setTextColor(
            ContextCompat.getColor(
                this,
                when (zustand) {
                    AufnahmeLeuchte.Zustand.LAEUFT -> R.color.aufnahme_an
                    AufnahmeLeuchte.Zustand.AUS -> R.color.aufnahme_aus
                    AufnahmeLeuchte.Zustand.UNBEKANNT -> R.color.aufnahme_unbekannt
                },
            )
        )
    }

    /**
     * Schaltet das Interview um — dasselbe, was der Schalter am Mikrofon tut.
     *
     * Gesendet wird der GEWÜNSCHTE Zustand (`on: true/false`) und kein
     * „umschalten": Ginge unterwegs eine Anfrage verloren und die App schickte
     * „das Gegenteil von dem, was ich glaube", liefe sie dauerhaft
     * gegenphasig. Ein absoluter Wert kann höchstens wirkungslos sein.
     */
    private fun schalteInterview() {
        val laeuft = interviewLaeuft ?: return  // unbekannt: der Knopf ist ohnehin gesperrt
        if (einstellungen.ziel != Einstellungen.Ziel.STATION) {
            zeige(getString(R.string.nur_im_tailnet), fehler = true)
            return
        }
        val neuerZustand = !laeuft
        interviewKnopf.isEnabled = false
        lifecycleScope.launch {
            val adresse = einstellungen.stationsAdresse
            val ergebnis = withContext(Dispatchers.IO) {
                try {
                    Uploader.schalte(
                        Uploader.endpunkt(adresse, "/api/interview_switch"), neuerZustand
                    )
                } catch (e: Exception) {
                    Uploader.Ergebnis.Fehler(getString(R.string.adresse_ungueltig))
                }
            }
            when (ergebnis) {
                is Uploader.Ergebnis.Erfolg -> {
                    // Sofort übernehmen, nicht auf die nächste Abfrage warten:
                    // bis zu drei Sekunden Verzögerung nach einem Druck fühlen
                    // sich nach einem nicht angekommenen Knopf an, und dann
                    // drückt man noch einmal.
                    interviewLaeuft = neuerZustand
                    zeige(
                        getString(
                            if (neuerZustand) R.string.interview_gestartet
                            else R.string.interview_beendet
                        ),
                        fehler = false,
                    )
                }
                is Uploader.Ergebnis.Fehler -> {
                    // Der Stand ist jetzt unbekannt, nicht etwa der alte: Die
                    // Anfrage kann die Station erreicht haben und nur die
                    // Antwort verloren gegangen sein. Die nächste Abfrage
                    // klärt es; bis dahin bleibt der Knopf gesperrt.
                    interviewLaeuft = null
                    zeige(ergebnis.text, fehler = true)
                }
            }
            zeigeZustand()
        }
    }

    private fun starteKamera() {
        val future = ProcessCameraProvider.getInstance(this)
        future.addListener({
            val provider = future.get()
            val vorschau = Preview.Builder().build().also {
                it.setSurfaceProvider(sucher.surfaceProvider)
            }
            aufnahme = ImageCapture.Builder()
                // Am Booth zählt, dass der Moment sitzt, nicht dass das Bild
                // maximal scharf ist: das Portrait landet als 512px-Scheibe an
                // der Wand (`cfg.portrait_size`), also ist Latenz die
                // wertvollere Größe.
                .setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY)
                .build()

            try {
                provider.unbindAll()
                provider.bindToLifecycle(
                    this, CameraSelector.DEFAULT_BACK_CAMERA, vorschau, aufnahme
                )
            } catch (e: Exception) {
                zeige(getString(R.string.kamera_fehler, e.message ?: ""), fehler = true)
            }
        }, ContextCompat.getMainExecutor(this))
    }

    private fun schiesse() {
        val capture = aufnahme ?: return
        if (sendetGerade) return
        sendetGerade = true
        ausloeser.isEnabled = false
        // Die alte Vorschau MUSS weg, bevor das naechste Foto entsteht: seit
        // sie formatfuellend liegt (2026-09-01), wuerde man sonst blind
        // ausloesen -- der Sucher waere vom vorigen Portrait verdeckt. Als
        // 140dp-Kachel in der Ecke war das egal, deshalb stand es vorher nicht
        // hier.
        vorschau.visibility = View.GONE
        zeige(getString(R.string.sende), fehler = false)

        capture.takePicture(
            ContextCompat.getMainExecutor(this),
            object : ImageCapture.OnImageCapturedCallback() {
                override fun onCaptureSuccess(bild: ImageProxy) {
                    // ImageProxy MUSS geschlossen werden, sonst blockiert der
                    // Puffer nach wenigen Fotos jede weitere Aufnahme — die
                    // App wirkt dann „hängt beim dritten Bild".
                    val bytes = bild.use { Bildbytes.ausProxy(it) }
                    // Die Größe steht in der Statuszeile, und das ist kein
                    // Schmuck: am 2026-09-01 hielt ein 4,4-MB-Foto die App
                    // sichtbar an, und ohne Zahl war „langsam" von „hängt"
                    // nicht zu unterscheiden. Jetzt ist ablesbar, dass etwas
                    // unterwegs ist und wieviel.
                    zeige(getString(R.string.sende_groesse, bytes.size / 1024), fehler = false)
                    sendeHoch(bytes)
                }

                override fun onError(e: ImageCaptureException) {
                    fertig(getString(R.string.aufnahme_fehler, e.message ?: ""), fehler = true)
                }
            }
        )
    }

    private fun sendeHoch(jpeg: ByteArray) {
        lifecycleScope.launch {
            val (adresse, token) = einstellungen.aktuellesZiel()
            val pfad = if (einstellungen.ziel == Einstellungen.Ziel.SPIEGEL)
                "/ingest/photo" else "/api/photo"

            val ergebnis = withContext(Dispatchers.IO) {
                try {
                    Uploader.sende(Uploader.endpunkt(adresse, pfad), jpeg, token)
                } catch (e: Exception) {
                    Uploader.Ergebnis.Fehler(getString(R.string.adresse_ungueltig))
                }
            }
            when (ergebnis) {
                is Uploader.Ergebnis.Erfolg -> {
                    // 🔴 Aus einem angekommenen Foto darf NICHT geschlossen
                    // werden, dass ein Interview laeuft. Seit 2026-09-01 nimmt
                    // die Station ein Bild auch fuer das zuletzt BEENDETE
                    // Gespraech an (Birk: „auch wenn das interview schon
                    // abgeschlossen ist und begriffe an der wand") -- eine 200
                    // heisst also nur „angekommen", nicht „laeuft".
                    //
                    // Hier stand kurzzeitig `interviewLaeuft = true`. Das war
                    // richtig, solange Fotos ausschliesslich zum laufenden
                    // Interview gehoerten, und wurde mit derselben Aenderung
                    // falsch: Der Knopf haette danach „beenden" angeboten fuer
                    // etwas, das schon beendet ist.
                    //
                    // Stattdessen nachfragen. Die naechste Abfrage kommt
                    // ohnehin binnen drei Sekunden; bis dahin bleibt der Knopf
                    // gesperrt, was ehrlicher ist als eine falsche Zusage.
                    interviewLaeuft = null
                    fertig(getString(R.string.gesendet), fehler = false)
                    // Die Vorschau kommt NACH der Erfolgsmeldung und blockiert
                    // den Auslöser nicht: sie ist eine Dreingabe. Über den
                    // Spiegel gibt es sie nicht, dort entsteht das Portrait
                    // erst beim Abholen — dann bleibt `portrait` null.
                    ergebnis.portrait?.let { zeigeVorschau(adresse, it) }
                }
                is Uploader.Ergebnis.Fehler -> {
                    // Ein abgelehntes Foto sagt auch etwas ueber den
                    // Interview-Zustand: Die haeufigste Ablehnung ist seit
                    // 2026-09-01 "kein Interview offen" -- und dann steht der
                    // Knopf womoeglich falsch auf "beenden". Also nachfragen
                    // statt beim eigenen Glauben bleiben.
                    interviewLaeuft = null
                    fertig(ergebnis.text, fehler = true)
                }
            }
        }
    }

    /**
     * Zeigt, wie die Station das Foto zugeschnitten hat.
     *
     * Absichtlich das ECHTE Portrait von der Station und keine Nachbildung
     * hier: eine App-seitige Vorschau würde irgendwann von dem abweichen, was
     * `kg/photos.py` tut, und dann prüft man am Booth eine Attrappe statt des
     * Ergebnisses. Genau dafür gibt die Station den Dateinamen zurück.
     */
    private fun zeigeVorschau(adresse: String, name: String) {
        lifecycleScope.launch {
            val bytes = withContext(Dispatchers.IO) {
                Uploader.holePortrait(adresse, name)
            } ?: return@launch  // kein Bild: still bleiben, das Foto ist trotzdem da

            val bild = BitmapFactory.decodeByteArray(bytes, 0, bytes.size) ?: return@launch
            vorschau.setImageBitmap(bild)
            vorschau.visibility = View.VISIBLE
            // Der Hinweis gehoert an die Vorschau, nicht in den Layout-Text:
            // formatfuellend verdeckt sie den Sucher, und ohne Ansage sieht das
            // aus, als haenge die App (Birk, 2026-09-01, am Booth).
            zeige(getString(R.string.vorschau_offen), fehler = false)
        }
    }

    private fun fertig(text: String, fehler: Boolean) {
        sendetGerade = false
        ausloeser.isEnabled = true
        zeige(text, fehler)
        // Der Interview-Knopf war waehrend des Sendens gesperrt (`sendetGerade`
        // in zeigeZustand) -- hier gibt er sich wieder frei, mit der
        // Beschriftung, die jetzt gilt.
        zeigeZustand()
    }

    private fun zeige(text: String, fehler: Boolean) {
        status.text = text
        status.setTextColor(
            ContextCompat.getColor(this, if (fehler) R.color.fehler else R.color.gut)
        )
        status.visibility = View.VISIBLE
    }
}
