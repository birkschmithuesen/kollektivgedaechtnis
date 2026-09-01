package art.artesmobiles.kg

import android.content.ClipboardManager
import android.content.Context
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

        // Einfuegen per Knopf, nicht per Kontextmenue: auf Birks Geraet bot
        // das Token-Feld beim langen Druecken kein „Einfuegen" an, das
        // Adressfeld darueber schon (2026-09-01). Woran das dort liegt, ist
        // aus der Ferne nicht zu klaeren — also wird die Zwischenablage
        // direkt gelesen. `ClipboardManager` haengt weder an der Tastatur
        // noch am Kontextmenue.
        findViewById<Button>(R.id.token_einfuegen).setOnClickListener {
            val ablage = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            val text = ablage.primaryClip
                ?.takeIf { it.itemCount > 0 }
                ?.getItemAt(0)
                ?.coerceToText(this)
                ?.toString()
                // Derselbe Leerraum-Schnitt wie beim Speichern: was hier
                // sichtbar ankommt, soll schon das sein, was gespeichert wird.
                ?.filterNot { z -> z.isWhitespace() }

            if (text.isNullOrEmpty()) {
                Toast.makeText(this, getString(R.string.ablage_leer), Toast.LENGTH_SHORT).show()
            } else {
                tokenFeld.setText(text)
                tokenFeld.setSelection(text.length)
            }
        }

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
