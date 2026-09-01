package art.artesmobiles.kg

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import androidx.camera.core.ImageProxy
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer

/**
 * Die Bytes aus dem, was CameraX zurückgibt — verkleinert auf ein Maß, das
 * die Station tatsächlich braucht.
 *
 * **Warum überhaupt verkleinert wird:** Die Kamera liefert 12 MP (4032×3024,
 * ~4,4 MB). Auf der Station wird daraus eine Scheibe von 512×512
 * (`cfg.portrait_size`). Die übrigen 11,7 Megapixel werden also erzeugt,
 * durchs Netz geschoben und dann weggeworfen. Gemessen am 2026-09-01: ein
 * solches Bild brauchte am Handy so lange, dass die App wie eingefroren
 * wirkte — die Kette war in Ordnung, nur die Datenmenge war absurd.
 *
 * 1600 px lange Kante (bis 2026-09-01: 1024). Die Station schneidet
 * quadratisch und sucht darin ein Gesicht (`kg/photos.py`); der Ausschnitt
 * wird am GESICHT bemessen (`GESICHTS_ZOOM = 2.0`), nicht am Bildrand. Ein
 * Gesicht muss deshalb mindestens 256 px haben, damit der Ausschnitt die
 * Portraitgröße 512 erreicht und NICHT hochgerechnet werden muss.
 *
 * Gemessen an Birks Booth-Fotos vom 2026-09-01 (bei 1024 px geliefert):
 * die erkannten Gesichter waren 61, 71, 201 und 218 px groß — **alle vier
 * unter 256**, also wurde jedes Portrait hochgerechnet (Faktor 1,17 bis 4,2).
 * Bei 1600 px sind dieselben Gesichter 1,56× größer (201 → 314 px), der
 * Ausschnitt kommt über 512, und das Portrait besteht aus ECHTEN Pixeln.
 *
 * 🔴 Das ist kein Widerspruch zur Messung von 15:10, die ergab „mehr
 * Auflösung = unschärfer". Die galt für Fotos mit KLEINEN, weit entfernten
 * Gesichtern: dort greift die Erkennung bei höherer Auflösung öfter, und ein
 * enger Gesichtsausschnitt hat weniger Pixel als der weite mittige Schnitt.
 * Birk, 2026-09-01: „in der Installation wird es gar nicht so weit weg sein" —
 * bei nahen Personen dreht sich der Effekt um.
 *
 * Der Preis ist Sendezeit: 1600 px sind grob 2,4× die Datenmenge von 1024.
 * Am Booth zählt, dass der Auslöser schnell wieder frei ist — sollte das
 * spürbar werden, ist dieser Wert die erste Stellschraube.
 *
 * Die zweite Falle ist die Drehung: JPEG aus der Kamera trägt die Lage im
 * EXIF, das Bitmap nach dem Dekodieren nicht mehr. Wer sie nicht selbst
 * anwendet, schickt liegende Portraits — und die Station dreht nichts
 * zurück, weil ihr `ImageOps.exif_transpose` dann nichts mehr vorfindet.
 */
object Bildbytes {

    /** Lange Kante nach dem Verkleinern. Begründung im Klassenkommentar. */
    const val MAX_KANTE = 1600

    /** Reicht für ein Portrait; darunter werden Hauttöne fleckig. */
    const val QUALITAET = 85

    fun ausProxy(bild: ImageProxy): ByteArray =
        verkleinere(ausBuffer(bild.planes[0].buffer), bild.imageInfo.rotationDegrees)

    fun ausBuffer(puffer: ByteBuffer): ByteArray {
        // rewind(), nicht darauf vertrauen, dass die Position auf 0 steht:
        // ein bereits angelesener Puffer liefert sonst ein abgeschnittenes
        // Bild, und zwar ohne jede Fehlermeldung.
        puffer.rewind()
        val bytes = ByteArray(puffer.remaining())
        puffer.get(bytes)
        return bytes
    }

    /**
     * Skaliert auf [MAX_KANTE] und dreht ins Hochformat.
     *
     * Schlägt irgendetwas fehl, kommen die Originalbytes zurück statt einer
     * Ausnahme: ein großes Foto ist langsam, aber brauchbar — gar keins ist
     * ein verlorener Interviewmoment.
     */
    fun verkleinere(jpeg: ByteArray, drehung: Int): ByteArray = try {
        val original = BitmapFactory.decodeByteArray(jpeg, 0, jpeg.size)
        if (original == null) {
            jpeg
        } else {
            val faktor = MAX_KANTE.toFloat() / maxOf(original.width, original.height)
            val skaliert = if (faktor >= 1f) {
                original  // schon klein genug -- nicht künstlich hochrechnen
            } else {
                Bitmap.createScaledBitmap(
                    original,
                    (original.width * faktor).toInt().coerceAtLeast(1),
                    (original.height * faktor).toInt().coerceAtLeast(1),
                    true,
                )
            }
            val gedreht = if (drehung == 0) skaliert else Bitmap.createBitmap(
                skaliert, 0, 0, skaliert.width, skaliert.height,
                Matrix().apply { postRotate(drehung.toFloat()) }, true,
            )
            ByteArrayOutputStream().use { aus ->
                gedreht.compress(Bitmap.CompressFormat.JPEG, QUALITAET, aus)
                aus.toByteArray()
            }
        }
    } catch (e: OutOfMemoryError) {
        jpeg
    } catch (e: Exception) {
        jpeg
    }
}
