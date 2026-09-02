package art.artesmobiles.kg

import android.animation.ValueAnimator
import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.util.AttributeSet
import android.view.View
import androidx.core.content.ContextCompat

/**
 * Die Aufnahme-Leuchte am oberen Rand.
 *
 * Birk, 2026-09-02: „so, dass es ganz eindeutig ist, ob gerade eine Aufnahme
 * läuft oder nicht ... eine rot blinkende 'interview running' LED ganz oben."
 *
 * ## Warum eine eigene View und kein blinkender TextView
 *
 * Der Punkt der Leuchte ist, dass sie aus dem Augenwinkel wirkt — jemand hält
 * das Handy, redet mit einem Gast und schaut nicht hin. Ein Punkt, der pulsiert,
 * leistet das; ein Wort, das die Farbe wechselt, nicht.
 *
 * Der Zustand ist ausdrücklich **dreiwertig** und nicht an/aus: „läuft",
 * „läuft nicht" und „weiß ich nicht" (Station nicht erreichbar). Das dritte
 * als „aus" darzustellen wäre die gefährlichste Lüge, die diese Anzeige
 * erzählen könnte — jemand verlässt sich darauf, dass nichts aufgezeichnet
 * wird, obwohl die App es schlicht nicht weiß.
 *
 * ## Das Blinken hält an, wenn die App weggeschaltet wird
 *
 * `ValueAnimator` läuft sonst in der Tasche weiter und weckt den Schirm-
 * Compositor. `onDetachedFromWindow` beendet ihn; `setZustand` startet ihn nur,
 * wenn die View am Fenster hängt.
 */
class AufnahmeLeuchte @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0,
) : View(context, attrs, defStyleAttr) {

    /** Was die Leuchte zeigt. `UNBEKANNT` ist ein eigener Zustand, kein „aus". */
    enum class Zustand { LAEUFT, AUS, UNBEKANNT }

    private val farbe = Paint(Paint.ANTI_ALIAS_FLAG)
    private val hof = Paint(Paint.ANTI_ALIAS_FLAG)

    private var zustand = Zustand.UNBEKANNT

    /** 0..1, wandert beim Blinken hin und her. Bei Ruhe konstant 1. */
    private var helligkeit = 1f

    private var blinken: ValueAnimator? = null

    /** Ob die View am Fenster haengt.
     *
     * Eigener Merker statt `isAttachedToWindow`: Der Systemwert wird von der
     * View-Hierarchie gesetzt, und in einem Robolectric-Test ohne echtes
     * Fenster bleibt er `false` -- der Blinker liesse sich dort nie starten
     * und der Test pruefte, dass nichts passiert. Der Merker folgt denselben
     * beiden Rueckrufen und ist damit im Betrieb dasselbe, im Test aber
     * ansteuerbar. */
    private var amFenster = false

    init {
        // Nicht anklickbar: Die Leuchte ist eine Anzeige. Ein Zustand, den man
        // antippen kann, verleitet dazu, ihn für den Schalter zu halten -- und
        // der sitzt bewusst unten, wo der Daumen ohnehin liegt.
        isClickable = false
        isFocusable = false
    }

    fun setZustand(neu: Zustand) {
        if (neu == zustand) return
        zustand = neu
        if (neu == Zustand.LAEUFT) starteBlinken() else stoppeBlinken()
        invalidate()
    }

    private fun starteBlinken() {
        if (blinken != null || !amFenster) return
        // 1,1 s je Richtung. Langsamer als ein Warnblinker (der wirkt hektisch
        // und wird nach zehn Minuten ignoriert), deutlich schneller als ein
        // Atmen -- es soll auffallen, ohne zu nerven, und es läuft potenziell
        // stundenlang.
        blinken = ValueAnimator.ofFloat(1f, 0.25f).apply {
            duration = 1100
            repeatMode = ValueAnimator.REVERSE
            repeatCount = ValueAnimator.INFINITE
            addUpdateListener {
                helligkeit = it.animatedValue as Float
                invalidate()
            }
            start()
        }
    }

    private fun stoppeBlinken() {
        blinken?.cancel()
        blinken = null
        helligkeit = 1f
    }

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        amFenster = true
        if (zustand == Zustand.LAEUFT) starteBlinken()
    }

    override fun onDetachedFromWindow() {
        amFenster = false
        stoppeBlinken()
        super.onDetachedFromWindow()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val r = (minOf(width, height) / 2f) - 2f
        if (r <= 0f) return
        val cx = width / 2f
        val cy = height / 2f

        val grund = when (zustand) {
            Zustand.LAEUFT -> ContextCompat.getColor(context, R.color.aufnahme_an)
            Zustand.AUS -> ContextCompat.getColor(context, R.color.aufnahme_aus)
            Zustand.UNBEKANNT -> ContextCompat.getColor(context, R.color.aufnahme_unbekannt)
        }

        // Der Hof macht aus dem Punkt eine Leuchte statt eines Aufklebers.
        //
        // Auch im Ruhezustand (Birk, 2026-09-02: die LED soll gruen UND rot
        // koennen). Haette nur Rot einen Hof, waere Gruen sichtbar schwaecher
        // -- und der Ruhezustand ist keine halbe Anzeige, sondern die
        // Aussage „es wird nichts aufgezeichnet". Die soll genauso deutlich
        // dastehen wie ihr Gegenteil.
        //
        // Der Unterschied bleibt die BEWEGUNG, nicht die Helligkeit: Rot
        // pulsiert, Gruen und Amber stehen still. Das ist das Zeichen, das
        // ohne Farbwahrnehmung funktioniert -- und damit auch fuer die rund
        // acht Prozent Maenner mit Rot-Gruen-Schwaeche lesbar, fuer die die
        // beiden Farben allein nichts unterscheiden.
        hof.color = grund
        hof.alpha = if (zustand == Zustand.LAEUFT) {
            (70 * helligkeit).toInt().coerceIn(0, 255)
        } else {
            55
        }
        canvas.drawCircle(cx, cy, r, hof)

        farbe.color = grund
        farbe.alpha = if (zustand == Zustand.LAEUFT) {
            (255 * helligkeit).toInt().coerceIn(40, 255)
        } else {
            255
        }
        canvas.drawCircle(cx, cy, r * 0.62f, farbe)
    }

    /** Nur für Tests: der Zustand, den die Leuchte gerade zeigt. */
    val aktuellerZustand: Zustand
        get() = zustand

    /** Nur für Tests: ob der Blinker läuft. */
    val blinktGerade: Boolean
        get() = blinken?.isRunning == true

    // `onAttachedToWindow` und `onDetachedFromWindow` sind `protected` und
    // ausserhalb der Klasse nicht aufrufbar. Ein Test muss aber genau diesen
    // Uebergang pruefen koennen -- er ist der Grund, warum der Blinker nicht
    // in der Tasche weiterlaeuft. Eine ganze Activity dafuer hochzufahren
    // waere der Umweg, der den Test langsam und die Aussage unschaerfer
    // macht.
    internal fun onAttachedToWindowFuerTest() = onAttachedToWindow()

    internal fun onDetachedFromWindowFuerTest() = onDetachedFromWindow()
}
