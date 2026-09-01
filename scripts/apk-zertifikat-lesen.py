"""Holt das echte Signaturzertifikat aus dem APK-Signaturschema v2.

Warum das zaehlt (Birk, 2026-09-01): Auf dem Telefon liegt v6, gebraucht wird
v8. Android laesst ein Update NUR zu, wenn beide mit demselben Schluessel
signiert sind -- sonst bricht die Installation mit einem nichtssagenden
"App nicht installiert" ab und man sucht den Fehler in der falschen Ecke.

Aufbau (developer.android.com/about/versions/nougat/android-7.0#apk_signature_v2):
  ...ZIP-Eintraege...
  APK Signing Block:
      uint64 groesse (wiederholt am Anfang und Ende)
      Paare: uint64 laenge | uint32 id | wert
      id 0x7109871a = Signaturschema v2
      magic "APK Sig Block 42"
  Central Directory ...

Im v2-Wert: sequence of signer, jeder signer hat
  signed data | signatures | public key
und in signed data: digests | CERTIFICATES | additional attributes.
Das Zertifikat ist ein DER-kodiertes X.509 -- sein SHA-256 ist der
Fingerabdruck, den auch `apksigner verify --print-certs` ausgibt.
"""
import hashlib
import struct
import sys

MAGIC = b"APK Sig Block 42"
ID_V2 = 0x7109871A


def laenge_praefix(daten, pos):
    """Liest ein uint32-laengenpraefixtes Feld. Gibt (inhalt, neue_pos)."""
    (n,) = struct.unpack_from("<I", daten, pos)
    return daten[pos + 4:pos + 4 + n], pos + 4 + n


def zertifikate(pfad):
    d = open(pfad, "rb").read()
    i = d.rfind(MAGIC)
    if i < 0:
        return []
    (groesse,) = struct.unpack_from("<Q", d, i - 8)
    block_start = i + len(MAGIC) - groesse - 8
    # 🔴 Die Paare beginnen NACH dem fuehrenden uint64 (Groesse) und enden VOR
    # dem abschliessenden uint64 + Magic. Ohne die +8/-8 liest man mitten in
    # eine Laengenangabe hinein und findet nie ein gueltiges Paar --
    # nachgemessen 2026-09-01: id 0x7109871a taucht erst mit dem Versatz auf.
    block = d[block_start + 8:i - 8]

    # Paare durchgehen und den v2-Wert finden
    p = 0
    v2 = None
    while p + 12 <= len(block):
        (paarlen,) = struct.unpack_from("<Q", block, p)
        if paarlen == 0 or p + 8 + paarlen > len(block) + 8:
            break
        (kennung,) = struct.unpack_from("<I", block, p + 8)
        if kennung == ID_V2:
            v2 = block[p + 12:p + 8 + paarlen]
            break
        p += 8 + paarlen
    if v2 is None:
        return []

    gefunden = []
    signer_liste, _ = laenge_praefix(v2, 0)
    q = 0
    while q + 4 <= len(signer_liste):
        signer, q = laenge_praefix(signer_liste, q)
        if not signer:
            break
        signed_data, _ = laenge_praefix(signer, 0)
        # in signed_data: digests (laengenpraefix), dann certificates
        _digests, r = laenge_praefix(signed_data, 0)
        certs, _ = laenge_praefix(signed_data, r)
        s = 0
        while s + 4 <= len(certs):
            cert, s = laenge_praefix(certs, s)
            if cert:
                gefunden.append(cert)
    return gefunden


gesehen = {}
for pfad in sys.argv[1:]:
    certs = zertifikate(pfad)
    if not certs:
        print(f"{pfad}: kein v2-Zertifikat gefunden")
        continue
    for c in certs:
        fp = hashlib.sha256(c).hexdigest()
        print(f"{pfad}: SHA-256 {fp}")
        gesehen.setdefault(fp, []).append(pfad)

if len(gesehen) > 1:
    print()
    print("🔴 VERSCHIEDENE Schluessel — Android verweigert das Update zwischen")
    print("   diesen Dateien mit 'App nicht installiert'. Die alte App muss")
    print("   erst deinstalliert werden (dabei gehen die Einstellungen in der")
    print("   App verloren: Adresse und Token neu eintragen).")
elif len(gesehen) == 1 and len(sys.argv) > 2:
    print()
    print("Gleicher Schluessel — Drueberinstallieren geht, ohne deinstallieren.")
