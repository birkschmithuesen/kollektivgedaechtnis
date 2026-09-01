package art.artesmobiles.kg

import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.RadioGroup
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity

/**
 * Zwei Wege zur Auswahl, dazu die passenden Felder.
 *
 * Absichtlich keine PreferenceFragment-Maschinerie: es sind vier Werte, und
 * die Person, die sie im Flur ändert, soll sie sehen, nicht suchen.
 */
class SettingsActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_settings)

        val einstellungen = Einstellungen(this)
        val wahl = findViewById<RadioGroup>(R.id.wegwahl)
        val stationsFeld = findViewById<EditText>(R.id.adresse)
        val spiegelBlock = findViewById<View>(R.id.spiegel_block)
        val spiegelFeld = findViewById<EditText>(R.id.spiegel_adresse)
        val tokenFeld = findViewById<EditText>(R.id.foto_token)

        stationsFeld.setText(einstellungen.stationsAdresse)
        spiegelFeld.setText(einstellungen.spiegelAdresse)
        tokenFeld.setText(einstellungen.fotoToken)
        wahl.check(
            if (einstellungen.ziel == Einstellungen.Ziel.SPIEGEL) R.id.weg_spiegel else R.id.weg_station
        )

        fun zeigePassendeFelder() {
            val spiegel = wahl.checkedRadioButtonId == R.id.weg_spiegel
            spiegelBlock.visibility = if (spiegel) View.VISIBLE else View.GONE
            stationsFeld.visibility = if (spiegel) View.GONE else View.VISIBLE
        }
        zeigePassendeFelder()
        wahl.setOnCheckedChangeListener { _, _ -> zeigePassendeFelder() }

        findViewById<Button>(R.id.speichern).setOnClickListener {
            val spiegel = wahl.checkedRadioButtonId == R.id.weg_spiegel
            val adresse = (if (spiegel) spiegelFeld else stationsFeld).text.toString().trim()
            val pfad = if (spiegel) "/ingest/photo" else "/api/photo"

            // Vor dem Speichern prüfen, nicht erst beim ersten Foto: eine
            // unbrauchbare Adresse soll hier auffallen, wo jemand hinschaut,
            // und nicht mitten im Interview.
            val ziel = try {
                Uploader.endpunkt(adresse, pfad)
            } catch (e: Exception) {
                Toast.makeText(this, getString(R.string.adresse_ungueltig), Toast.LENGTH_LONG).show()
                return@setOnClickListener
            }

            // Der Spiegel-Weg ohne Token ergibt nur 401 — das hier zu sagen
            // ist billiger als ein rätselhafter Fehlschlag am Booth.
            if (spiegel && tokenFeld.text.toString().isBlank()) {
                Toast.makeText(this, getString(R.string.token_fehlt), Toast.LENGTH_LONG).show()
                return@setOnClickListener
            }

            einstellungen.ziel =
                if (spiegel) Einstellungen.Ziel.SPIEGEL else Einstellungen.Ziel.STATION
            if (spiegel) {
                einstellungen.spiegelAdresse = adresse
                einstellungen.fotoToken = tokenFeld.text.toString()
            } else {
                einstellungen.stationsAdresse = adresse
            }

            Toast.makeText(
                this, getString(R.string.gespeichert, ziel.toString()), Toast.LENGTH_LONG
            ).show()
            finish()
        }
    }
}
