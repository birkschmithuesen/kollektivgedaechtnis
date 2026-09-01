#!/usr/bin/env bash
# Misst die zwei Zustaende des Mikrofonschalters ein und setzt die Schwellen.
#
# 🔴 WARUM ES DIESE DATEI GIBT (Birk, 2026-09-01: „mikrofon aus wird nicht
# richtig detektiert"):
#
# Der Gate kennt zwei Schwellen (vad.py:196-203):
#     level_rms > threshold          -> an
#     level_rms < threshold * ratio  -> aus
#     dazwischen                     -> es BLEIBT, wie es ist
#
# Liegt die Aus-Schwelle unter der Rauschgrenze des Interfaces, ist der
# Aus-Zweig unerreichbar: jeder Messwert faellt ins Hystereseband, der Gate
# haelt seinen Zustand, und das Mikrofon kann nie mehr ausgehen. Genau das war
# am 2026-09-01 der Fall -- Aus-Schwelle 0,0002 gegen eine gemessene
# Rauschgrenze von 0,00020 bis 0,00029 (74 Messwerte in 30 s am ZOOM AMS-24).
# Es sah aus wie ein haengender Dienst und war eine Zahl.
#
# Raten hilft hier nicht: der Abstand zwischen „aus" (Rauschen des Wandlers)
# und „an, aber niemand spricht" (Raumton ueber ein offenes Mikrofon) haengt an
# Geraet, Gain und Raum. Deshalb wird er GEMESSEN, in beiden Zustaenden.
#
# Aufruf (der STT-Dienst MUSS laufen -- gemessen wird ueber /levels):
#     ./scripts/einmessen-mikrofon.sh
#
# Setzt die Werte am Ende ueber POST /mic_gate; der Dienst schreibt sie selbst
# nach settings/stt_runtime.json und ueberlebt damit den naechsten Start.

set -u
STT="http://127.0.0.1:5051"
DAUER="${KG_MESSDAUER:-12}"

if ! curl -fsS -o /dev/null --max-time 3 "$STT/status" 2>/dev/null; then
  echo "FEHLER: Auf $STT antwortet nichts. Erst die Station starten:" >&2
  echo "        ./scripts/start-station.sh" >&2
  exit 1
fi

echo ""
echo "Mikrofonschalter einmessen — zwei Messungen, je ${DAUER} s"
echo ""
echo "  1) Mikrofon AUS schalten (oder Kabel raus)."
read -r -p "     Wenn es aus ist: Enter … "
AUS=$(python3 - "$STT" "$DAUER" <<'PY'
import json, sys, time, urllib.request
stt, dauer = sys.argv[1], float(sys.argv[2])
v = []
t0 = time.time()
while time.time() - t0 < dauer:
    d = json.load(urllib.request.urlopen(stt + "/levels", timeout=3))
    v.append(d["sources"][0]["level_rms"])
    time.sleep(0.3)
v.sort()
# Der MAXIMALWERT zaehlt, nicht der Mittelwert: die Aus-Schwelle muss ueber
# JEDEM Ausschlag liegen, den der ruhende Eingang produziert. Ein Mittelwert
# laesst den Gate bei jeder Spitze wieder anspringen.
print(f"{v[-1]:.6f} {v[len(v)//2]:.6f} {len(v)}")
PY
)
read -r AUS_MAX AUS_MED AUS_N <<< "$AUS"
printf "     aus:  max %.6f   median %.6f   (%s Werte)\n\n" "$AUS_MAX" "$AUS_MED" "$AUS_N"

echo "  2) Mikrofon AN schalten — aber NICHT sprechen."
echo "     (Das ist der schwierige Zustand: ein offenes Mikrofon im stillen"
echo "      Raum. Wer hier spricht, misst zu hoch und der Gate faellt spaeter"
echo "      in jeder Sprechpause auf 'aus'.)"
read -r -p "     Wenn es an ist: Enter … "
AN=$(python3 - "$STT" "$DAUER" <<'PY'
import json, sys, time, urllib.request
stt, dauer = sys.argv[1], float(sys.argv[2])
v = []
t0 = time.time()
while time.time() - t0 < dauer:
    d = json.load(urllib.request.urlopen(stt + "/levels", timeout=3))
    v.append(d["sources"][0]["level_rms"])
    time.sleep(0.3)
v.sort()
# Hier zaehlt das MINIMUM: die An-Schwelle muss unter dem leisesten Moment
# liegen, den ein eingeschaltetes Mikrofon zeigt.
print(f"{v[0]:.6f} {v[len(v)//2]:.6f} {len(v)}")
PY
)
read -r AN_MIN AN_MED AN_N <<< "$AN"
printf "     an:   min %.6f   median %.6f   (%s Werte)\n\n" "$AN_MIN" "$AN_MED" "$AN_N"

python3 - "$STT" "$AUS_MAX" "$AN_MIN" <<'PY'
import json, sys, urllib.request

stt, aus_max, an_min = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])

print(f"  Trennschaerfe: an/aus = {an_min / max(aus_max, 1e-9):.1f}x")
if an_min <= aus_max * 1.6:
    print()
    print("🔴 ZU WENIG ABSTAND. Aus und An sind am Pegel nicht sicher zu")
    print("   unterscheiden — jede Schwelle dazwischen flattert.")
    print("   Erst am Geraet den Gain hochdrehen, dann erneut messen.")
    print("   (Ein hoeherer Gain hebt den Raumton des offenen Mikrofons an,")
    print("    das Rauschen des stummen Eingangs aber nicht.)")
    raise SystemExit(1)

# Aus-Schwelle mit 50 % Luft ueber das lauteste Rauschen; An-Schwelle mit 20 %
# Luft unter den leisesten Moment eines offenen Mikrofons. Beide Reserven
# zeigen in die sichere Richtung: lieber einmal zu spaet aus als mitten im
# Interview, und lieber einmal zu frueh an als gar nicht.
aus_schwelle = aus_max * 1.5
an_schwelle = an_min * 0.8
ratio = aus_schwelle / an_schwelle

print(f"  -> an ab      {an_schwelle:.6f}")
print(f"  -> aus unter  {aus_schwelle:.6f}   (ratio {ratio:.3f})")
print()

antwort = json.load(urllib.request.urlopen(urllib.request.Request(
    stt + "/mic_gate",
    data=json.dumps({"value": round(an_schwelle, 6),
                     "release_ratio": round(ratio, 3)}).encode(),
    headers={"Content-Type": "application/json"})))
g = antwort["mic_gate"]
print(f"  gesetzt: threshold={g['threshold']}  release={g['release_threshold']}  "
      f"debounce={g['debounce_ms']} ms")
print(f"  gespeichert: {antwort.get('persisted')}")
print()
print("  Jetzt gegenprobieren: Schalter aus und an, und dabei zusehen:")
print("    curl -s http://127.0.0.1:5051/levels | python3 -m json.tool | grep -E 'mic_on|level_rms'")
PY
