package art.artesmobiles.kg

import android.content.Context

/**
 * Wo die Station steht. Das Einzige, was diese App sich merken muss.
 *
 * Der Standardwert ist absichtlich die Tailnet-Adresse des vServers und nicht
 * leer: so zeigt die App beim ersten Start auf etwas Erreichbares statt auf
 * ein Feld, das im Flur erst noch ausgefüllt werden will. Am Ausstellungstag
 * steht hier die Adresse des Ausstellungsrechners, eingetragen in den
 * Einstellungen — ein Neubau des APK ist dafür nicht nötig.
 */
class Einstellungen(context: Context) {

    private val store = context.getSharedPreferences("kg", Context.MODE_PRIVATE)

    var stationsAdresse: String
        get() = store.getString(SCHLUESSEL, STANDARD) ?: STANDARD
        set(wert) = store.edit().putString(SCHLUESSEL, wert.trim()).apply()

    companion object {
        private const val SCHLUESSEL = "station"
        const val STANDARD = "100.75.24.33:8800"
    }
}
