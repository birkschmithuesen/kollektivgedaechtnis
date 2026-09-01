package art.artesmobiles.kg

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.util.AttributeSet
import android.view.View
import kotlin.math.min

/**
 * Der Kreis über dem Sucher: wo der Kopf hingehört.
 *
 * **Der Rahmen bildet die Rechnung der Station nach, er ist keine Deko.**
 * Was er zeigt, muss dem entsprechen, was `kg/photos.py::_square_crop`
 * tatsächlich tut — ein Rahmen, der etwas anderes verspricht, ist schlimmer
 * als keiner, weil man ihm dann folgt und das Portrait trotzdem falsch sitzt.
 *
 * Deshalb bildet er den RÜCKFALLWEG ab (mittiger, größtmöglicher
 * quadratischer Ausschnitt), nicht den Gesichtsweg:
 *
 *  - Der Gesichtsweg (`GESICHTS_ZOOM`, `GESICHTS_BIAS`) hängt davon ab, WO
 *    die Station ein Gesicht findet — das weiß die App nicht, sie erkennt
 *    keine Gesichter.
 *  - Auf dem Ausstellungsrechner ist `cv2` nicht installiert (gemessen
 *    2026-09-01), die Erkennung läuft dort also gar nicht und der mittige
 *    Schnitt IST der reale Weg.
 *
 * Findet die Station doch ein Gesicht, wird der Ausschnitt enger und folgt
 * dem Kopf — dann ist der gezeigte Kreis die sichere Untergrenze: wer darin
 * steht, ist auf beiden Wegen drin.
 */
class SucherRahmen @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : View(context, attrs) {

    private val gold = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#D8B15A")
        style = Paint.Style.STROKE
        strokeWidth = 4f
    }

    private val abdunkeln = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#99000000")
        style = Paint.Style.FILL
    }

    private val hilfslinie = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#66D8B15A")
        style = Paint.Style.STROKE
        strokeWidth = 2f
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)

        // Der Ausschnitt der Station: das größtmögliche Quadrat, mittig.
        val seite = min(width, height).toFloat()
        val links = (width - seite) / 2f
        val oben = (height - seite) / 2f
        val quadrat = RectF(links, oben, links + seite, oben + seite)

        // Alles AUSSERHALB des Quadrats abdunkeln — das ist der Teil, den die
        // Station wegschneidet. Sichtbar machen, was verloren geht, ist
        // aussagekräftiger als nur den Rahmen zu zeigen.
        val aussen = Path().apply {
            addRect(0f, 0f, width.toFloat(), height.toFloat(), Path.Direction.CW)
            addRect(quadrat, Path.Direction.CCW)
        }
        canvas.drawPath(aussen, abdunkeln)

        // Der Kreis: so wird das Portrait an der Wand beschnitten
        // (`soft_disc_mask`). Das Quadrat allein täuscht — die Ecken fallen
        // weg, und genau dort steht sonst eine Schulter, die man drin wähnte.
        canvas.drawOval(quadrat, gold)

        // Die Zone für den Kopf. GESICHTS_BIAS = 0.46 heißt: die Station legt
        // die Gesichtsmitte auf 46 % der Ausschnitthöhe, über dem Kopf bleibt
        // ein knappes Fünftel Luft. Der Ring markiert diese Höhe, damit
        // niemand nach Gefühl schätzen muss.
        val kopfY = oben + seite * 0.38f
        val kopfR = seite * 0.20f
        canvas.drawCircle(links + seite / 2f, kopfY, kopfR, hilfslinie)
    }
}
