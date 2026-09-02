package art.artesmobiles.kg

import android.os.Build
import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * Die Aufnahme-Leuchte (Birk, 2026-09-02: „eine rot blinkende 'interview
 * running' LED ganz oben").
 *
 * Geprüft wird das, was falsch sein KANN und teuer wäre:
 *
 * * dass „weiß ich nicht" nicht wie „aus" aussieht — die eine Verwechslung,
 *   bei der sich jemand darauf verlässt, nicht aufgezeichnet zu werden;
 * * dass der Blinker nur im Aufnahmezustand läuft und in der Tasche aufhört
 *   (sonst weckt er stundenlang den Compositor).
 *
 * Nicht geprüft: wie das Rot aussieht. Das ist Birks Urteil am Gerät.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [Build.VERSION_CODES.P])
class AufnahmeLeuchteTest {

    private fun leuchte() =
        AufnahmeLeuchte(ApplicationProvider.getApplicationContext())

    @Test
    fun `unbekannt ist der Anfangszustand, nicht aus`() {
        // Bis die erste Antwort der Station da ist, weiß die App nichts.
        // Stünde hier AUS, behauptete die Leuchte im ersten Moment nach dem
        // Start etwas, das sie nicht wissen kann.
        assertEquals(AufnahmeLeuchte.Zustand.UNBEKANNT, leuchte().aktuellerZustand)
    }

    @Test
    fun `nur im Aufnahmezustand wird geblinkt`() {
        val l = leuchte()
        l.setZustand(AufnahmeLeuchte.Zustand.AUS)
        assertFalse("blinkt, obwohl nichts laeuft", l.blinktGerade)
        l.setZustand(AufnahmeLeuchte.Zustand.UNBEKANNT)
        assertFalse("blinkt bei unbekanntem Zustand", l.blinktGerade)
    }

    @Test
    fun `der Blinker haelt an, wenn die View vom Fenster geht`() {
        // 🔴 Sonst läuft der ValueAnimator in der Tasche weiter und weckt den
        // Schirm-Compositor -- über einen Ausstellungstag hinweg ist das
        // Batterie für eine Anzeige, die niemand sieht.
        val l = leuchte()
        l.onAttachedToWindowFuerTest()
        l.setZustand(AufnahmeLeuchte.Zustand.LAEUFT)
        assertTrue("blinkt nicht, obwohl aufgezeichnet wird", l.blinktGerade)

        l.onDetachedFromWindowFuerTest()
        assertFalse("der Blinker laeuft nach dem Wegschalten weiter", l.blinktGerade)
    }

    @Test
    fun `nach dem Zurueckkommen blinkt es wieder`() {
        val l = leuchte()
        l.onAttachedToWindowFuerTest()
        l.setZustand(AufnahmeLeuchte.Zustand.LAEUFT)
        l.onDetachedFromWindowFuerTest()

        l.onAttachedToWindowFuerTest()
        assertTrue("nach dem Zurueckkommen bleibt die Leuchte still", l.blinktGerade)
    }
}
