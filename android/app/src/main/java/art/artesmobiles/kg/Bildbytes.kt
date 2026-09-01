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
 * 1024 px lange Kante, nicht 512: die Station schneidet quadratisch und
 * sucht darin ein Gesicht (`kg/photos.py`). Wer hier schon auf die
 * Zielgröße geht, nimmt ihr den Spielraum für den Schnitt und liefert ein
 * weicheres Portrait. 1024 ist der doppelte Zielwert — genug Reserve für
 * jeden Ausschnitt, und trotzdem rund ein Zwanzigstel der Datenmenge.
 *
 * Die zweite Falle ist die Drehung: JPEG aus der Kamera trägt die Lage im
 * EXIF, das Bitmap nach dem Dekodieren nicht mehr. Wer sie nicht selbst
 * anwendet, schickt liegende Portraits — und die Station dreht nichts
 * zurück, weil ihr `ImageOps.exif_transpose` dann nichts mehr vorfindet.
 */
object Bildbytes {

    /** Lange Kante nach dem Verkleinern. Doppelte Portraitgröße der Station. */
    const val MAX_KANTE = 1024

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
