package art.artesmobiles.kg

import android.content.Context

/**
 * Wohin die App schickt — und mit welchem Recht.
 *
 * Zwei Betriebsarten, weil es zwei Lagen gibt (Birk, 2026-09-01):
 *
 *  - **Station (Tailnet).** Das Handy ist im Tailnet, das Foto geht direkt
 *    an den Ausstellungsrechner. Kein Token nötig, weil das Tailnet selbst
 *    der Zugang ist. Der schnellste Weg, und der für die eigenen Geräte.
 *
 *  - **Spiegel (öffentlich).** Das Handy ist NICHT im Tailnet — ein
 *    geliehenes Gerät, eine Kollegin. Das Foto geht an den öffentlichen
 *    Spiegel, die Station holt es dort ab. Dafür braucht es das Foto-Token.
 *
 * Der zweite Weg existiert, weil die Alternative schlechter war: jemanden
 * ins Tailnet zu holen gibt ihm Zugriff auf ALLE Maschinen. Das Foto-Token
 * kann dagegen nur eines — ein Foto einwerfen. Es steht in dieser APK und
 * ist damit kein echtes Geheimnis; genau deshalb darf es serverseitig nichts
 * weiter (mirror/receiver.py, `pruefe_foto_token`).
 */
class Einstellungen(context: Context) {

    private val store = context.getSharedPreferences("kg", Context.MODE_PRIVATE)

    enum class Ziel { STATION, SPIEGEL }

    var ziel: Ziel
        get() = if (store.getString(ZIEL, "station") == "spiegel") Ziel.SPIEGEL else Ziel.STATION
        set(wert) = store.edit()
            .putString(ZIEL, if (wert == Ziel.SPIEGEL) "spiegel" else "station").apply()

    /** Adresse der Station im Tailnet. */
    var stationsAdresse: String
        get() = store.getString(STATION, STANDARD_STATION) ?: STANDARD_STATION
        set(wert) = store.edit().putString(STATION, wert.trim()).apply()

    /** Adresse des öffentlichen Spiegels. */
    var spiegelAdresse: String
        get() = store.getString(SPIEGEL, STANDARD_SPIEGEL) ?: STANDARD_SPIEGEL
        set(wert) = store.edit().putString(SPIEGEL, wert.trim()).apply()

    /**
     * Das Foto-Token für den Spiegel-Weg.
     *
     * Leer als Standard, nicht vorbelegt: ein Token gehört nicht in ein
     * öffentliches Repository, auch kein schwaches. Es wird beim Einrichten
     * eingetragen — einmal pro Gerät.
     *
     * Beim Setzen wird ALLER Leerraum entfernt, nicht nur am Rand: ein aus
     * einer Terminalausgabe kopiertes Token schleppt regelmäßig einen
     * Zeilenumbruch oder ein Leerzeichen mit. Das Ergebnis wäre ein 401, das
     * wie ein Serverfehler aussieht statt wie ein Kopierfehler — und niemand
     * sieht einem Feld an, dass hinten ein „\n" steht. Ein echtes Token
     * enthält nie Leerraum (`secrets.token_urlsafe`), es geht also nichts
     * verloren.
     */
    var fotoToken: String
        get() = store.getString(TOKEN, "") ?: ""
        set(wert) = store.edit()
            .putString(TOKEN, wert.filterNot { it.isWhitespace() }).apply()

    /** Was jetzt gilt — Adresse und Token passend zum gewählten Weg. */
    fun aktuellesZiel(): Pair<String, String?> = when (ziel) {
        Ziel.STATION -> stationsAdresse to null
        Ziel.SPIEGEL -> spiegelAdresse to fotoToken.ifBlank { null }
    }

    companion object {
        private const val ZIEL = "ziel"
        private const val STATION = "station"
        private const val SPIEGEL = "spiegel"
        private const val TOKEN = "foto_token"
        const val STANDARD_STATION = "100.75.24.33:8800"
        const val STANDARD_SPIEGEL = "https://kollektivgedaechtnis.flashclash.de"
    }
}
