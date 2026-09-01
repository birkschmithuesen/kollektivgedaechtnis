package art.artesmobiles.kg

import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity

/**
 * Ein Feld, ein Knopf: wo steht die Station.
 *
 * Absichtlich keine PreferenceFragment-Maschinerie — es ist eine einzige
 * Einstellung, und die Person, die sie im Flur ändert, soll sie sehen, nicht
 * suchen.
 */
class SettingsActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_settings)

        val einstellungen = Einstellungen(this)
        val feld = findViewById<EditText>(R.id.adresse)
        feld.setText(einstellungen.stationsAdresse)

        findViewById<Button>(R.id.speichern).setOnClickListener {
            val eingabe = feld.text.toString().trim()
            // Vor dem Speichern prüfen, nicht erst beim ersten Foto: eine
            // unbrauchbare Adresse soll hier auffallen, wo jemand hinschaut,
            // und nicht mitten im Interview.
            try {
                val ziel = Uploader.endpunkt(eingabe)
                einstellungen.stationsAdresse = eingabe
                Toast.makeText(this, getString(R.string.gespeichert, ziel.toString()), Toast.LENGTH_LONG).show()
                finish()
            } catch (e: Exception) {
                Toast.makeText(this, getString(R.string.adresse_ungueltig), Toast.LENGTH_LONG).show()
            }
        }
    }
}
