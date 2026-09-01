"""Liest aus dem APK, wie das Vorschau-ImageView WIRKLICH konfiguriert ist.

Anlass (Birk, 2026-09-01): „die mobile app zeigt das gemachte foto nur klein
und nicht wie gewuenscht im vollbild an." Der Quellcode sagt seit 15:48
Vollbild. Diese Datei beantwortet die andere Frage: was steht im ausgelieferten
Binaerlayout?

Android-Binaerlayout (AXML): Header, StringPool, ResourceMap, dann START_TAG-
Chunks. Jedes Attribut traegt (ns, name, rawValue, typedValue) -- typedValue
enthaelt Typ und Rohwert. Groessen sind TYPE_DIMENSION (0x05), dabei stecken
Einheit und Zahl im selben 32-Bit-Wort.
"""
import struct
import sys
import zipfile

TYP_REFERENZ = 0x01
TYP_STRING = 0x03
TYP_DIMENSION = 0x05
TYP_INT_DEC = 0x10
TYP_INT_HEX = 0x11
TYP_BOOL = 0x12

EINHEIT = {0: "px", 1: "dip", 2: "sp", 3: "pt", 4: "in", 5: "mm"}


def string_pool(d):
    off = 8
    while off + 8 <= len(d):
        typ, _hsize, size = struct.unpack_from("<HHI", d, off)
        if typ == 0x0001:
            cnt, _sc, flags, sstart, _ = struct.unpack_from("<IIIII", d, off + 8)
            utf8 = bool(flags & (1 << 8))
            offs = struct.unpack_from("<%dI" % cnt, d, off + 28)
            base = off + sstart
            out = []
            for o in offs:
                p = base + o
                if utf8:
                    n = d[p + 1]
                    out.append(d[p + 2:p + 2 + n].decode("utf-8", "replace"))
                else:
                    n = struct.unpack_from("<H", d, p)[0]
                    out.append(d[p + 2:p + 2 + 2 * n].decode("utf-16-le", "replace"))
            return out, off + size
        if size == 0:
            break
        off += size
    return [], len(d)


def wert(typ, roh, pool):
    if typ == TYP_STRING:
        return pool[roh] if roh < len(pool) else f"<str {roh}>"
    if typ == TYP_DIMENSION:
        zahl = (roh >> 8) / 1.0
        einheit = EINHEIT.get(roh & 0xF, "?")
        return f"{zahl:g}{einheit}"
    if typ == TYP_BOOL:
        return "true" if roh else "false"
    if typ == TYP_REFERENZ:
        return f"@0x{roh:08x}"
    if typ in (TYP_INT_DEC, TYP_INT_HEX):
        # 0 = match_parent(-1)? Nein: -1/-2 kommen als INT_DEC mit 0xffffffff.
        if roh == 0xFFFFFFFF:
            return "match_parent(-1)"
        if roh == 0xFFFFFFFE:
            return "wrap_content(-2)"
        return str(roh)
    return f"typ0x{typ:02x}:{roh}"


def tags(d, pool, start):
    off = start
    while off + 8 <= len(d):
        typ, hsize, size = struct.unpack_from("<HHI", d, off)
        if size == 0:
            break
        if typ == 0x0102:  # START_TAG
            name_i = struct.unpack_from("<I", d, off + 8 + 8 + 4)[0]
            attr_start, _attr_size, attr_cnt = struct.unpack_from("<HHH", d, off + 8 + 16)
            name = pool[name_i] if name_i < len(pool) else "?"
            attrs = {}
            p = off + 8 + 8 + attr_start
            for _ in range(attr_cnt):
                _ns, an, _raw, tv = struct.unpack_from("<IIII", d, p)
                atyp = (tv >> 24) & 0xFF
                aroh = struct.unpack_from("<I", d, p + 16)[0]
                attrs[pool[an] if an < len(pool) else "?"] = wert(atyp, aroh, pool)
                p += 20
            yield name, attrs
        off += size


def layout_datei(z):
    """Findet das Hauptlayout, auch wenn der Build die Namen verkuerzt hat.

    Ohne Minifizierung heisst es `res/layout/activity_main.xml`. Mit
    aktivierter Ressourcen-Verkuerzung (so gebaut bei v6) heisst dieselbe
    Datei `res/v9.xml` -- der Name ist dann kein Hinweis mehr. Deshalb wird
    nach dem INHALT gesucht: nur unser Layout nennt `SucherRahmen`.
    """
    for name in z.namelist():
        if not (name.startswith("res/") and name.endswith(".xml")):
            continue
        d = z.read(name)
        if b"S\x00u\x00c\x00h\x00e\x00r" in d or b"SucherRahmen" in d:
            return name, d
    return None, None


def bewerte(attrs):
    """Uebersetzt die Rohwerte in die Frage, die tatsaechlich interessiert."""
    breite = attrs.get("layout_width", "")
    if breite == "140dip":
        return "KACHEL in der Ecke (v6 und aelter)"
    if breite == "0dip":
        return "VOLLBILD (ab v7)"
    return f"unbekannt ({breite})"


for pfad in sys.argv[1:]:
    z = zipfile.ZipFile(pfad)
    name, d = layout_datei(z)
    if d is None:
        print(f"{pfad}: kein Layout mit SucherRahmen gefunden")
        continue
    pool, nach = string_pool(d)
    print(f"=== {pfad}  (Layout: {name})")
    for tagname, attrs in tags(d, pool, nach):
        knapp = {k: a for k, a in attrs.items()
                 if k in ("id", "layout_width", "layout_height", "scaleType",
                          "visibility")}
        print(f"  <{tagname}> {knapp}")
        # Das Vorschau-ImageView ist das einzige mit `visibility=gone` (2).
        if tagname == "ImageView" and attrs.get("visibility") == "2":
            print(f"  -> Vorschau: {bewerte(attrs)}")
