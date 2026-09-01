package art.artesmobiles.kg

import androidx.camera.core.ImageProxy
import java.nio.ByteBuffer

/**
 * Die Bytes aus dem, was CameraX zurückgibt.
 *
 * Eigene Datei, weil das die einzige Stelle ist, an der ein subtiler Fehler
 * unbemerkt bliebe: `ImageProxy.planes[0].buffer` ist ein `ByteBuffer`, dessen
 * Position nach dem Lesen am Ende steht, und dessen `array()` (falls
 * überhaupt vorhanden) den GESAMTEN Puffer liefert, nicht nur die belegten
 * Bytes. Wer hier `.array()` nimmt, schickt Müll ans Ende jedes Fotos —
 * gelegentlich noch dekodierbar, gelegentlich nicht. Deshalb `remaining()`
 * plus `get()`.
 *
 * `ImageCapture` liefert bereits fertiges JPEG (`format == JPEG`), es wird
 * hier also nichts kodiert — nur ausgelesen.
 */
object Bildbytes {

    fun ausProxy(bild: ImageProxy): ByteArray = ausBuffer(bild.planes[0].buffer)

    fun ausBuffer(puffer: ByteBuffer): ByteArray {
        // rewind(), nicht darauf vertrauen, dass die Position auf 0 steht:
        // ein bereits angelesener Puffer liefert sonst ein abgeschnittenes
        // Bild, und zwar ohne jede Fehlermeldung.
        puffer.rewind()
        val bytes = ByteArray(puffer.remaining())
        puffer.get(bytes)
        return bytes
    }
}
