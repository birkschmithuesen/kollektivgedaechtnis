package art.artesmobiles.kg

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.ImageButton
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
    private var aufnahme: ImageCapture? = null

    /** Verhindert, dass ein zweiter Druck ein zweites Interview eröffnet. */
    private var sendetGerade = false

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

        ausloeser.setOnClickListener { schiesse() }
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
        zeige(getString(R.string.bereit, einstellungen.stationsAdresse), fehler = false)
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
            val ergebnis = withContext(Dispatchers.IO) {
                try {
                    Uploader.sende(Uploader.endpunkt(einstellungen.stationsAdresse), jpeg)
                } catch (e: Exception) {
                    Uploader.Ergebnis.Fehler(getString(R.string.adresse_ungueltig))
                }
            }
            when (ergebnis) {
                is Uploader.Ergebnis.Erfolg ->
                    fertig(getString(R.string.gesendet), fehler = false)
                is Uploader.Ergebnis.Fehler ->
                    fertig(ergebnis.text, fehler = true)
            }
        }
    }

    private fun fertig(text: String, fehler: Boolean) {
        sendetGerade = false
        ausloeser.isEnabled = true
        zeige(text, fehler)
    }

    private fun zeige(text: String, fehler: Boolean) {
        status.text = text
        status.setTextColor(
            ContextCompat.getColor(this, if (fehler) R.color.fehler else R.color.gut)
        )
        status.visibility = View.VISIBLE
    }
}
