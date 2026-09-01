#!/usr/bin/env bash
# Richtet die Station auf einem frischen Mac ein — von null bis startklar.
#
# 🔴 ÜBERGABEPUNKT. Diese Datei liegt in der RoboCloud
# (`Hermes-Agent/RoboCloud/NewBauhaus-2026-Interviews/`), damit sie auf einem
# Rechner erreichbar ist, der das Repo noch NICHT hat. Alles andere kommt
# danach über git.
#
# Anlass (Birk, 2026-09-01): Die Ausstellung läuft seit dem Vorabend auf dem
# MacBook statt auf dem Windows-Rechner. „Für den Mac brauche ich noch ein
# Skript, das alle Repos klont die benötigt sind und so."
#
# Aufruf — kein Download nötig, ein Befehl im Terminal:
#     bash einrichten-mac.sh
#
# Was es NICHT tut: Schlüssel setzen. Die kommen aus `.env` und gehören nicht
# in ein Skript, das in der Cloud liegt. Am Ende steht, was noch fehlt.

set -euo pipefail

ZIEL="${KG_ZIEL:-$HOME/projekte/kollektivgedaechtnis}"
REPO="https://github.com/birkschmithuesen/kollektivgedaechtnis.git"

# Nicht-ASCII vermeiden: dieses Skript läuft evtl. in einer Konsole ohne UTF-8.
schritt() { echo ""; echo "=== $* ==="; }
fehler()  { echo "FEHLER: $*" >&2; exit 1; }

schritt "1/6  Voraussetzungen prüfen"

# Xcode-Kommandozeilenwerkzeuge bringen git mit. Ohne sie gibt es auf einem
# frischen Mac kein git, und der Klon scheitert mit einer Meldung, die wie ein
# Netzwerkproblem aussieht.
if ! xcode-select -p >/dev/null 2>&1; then
  echo "Xcode-Kommandozeilenwerkzeuge fehlen. Es öffnet sich gleich ein Fenster."
  echo "Nach der Installation dieses Skript ERNEUT starten."
  xcode-select --install || true
  exit 1
fi
echo "  Xcode-Werkzeuge: da"

command -v git >/dev/null 2>&1 || fehler "git fehlt trotz Xcode-Werkzeugen."
echo "  git: $(git --version)"

# Homebrew ist nicht zwingend, aber der einfachste Weg zu uv.
if ! command -v brew >/dev/null 2>&1; then
  echo "  Homebrew: fehlt — wird installiert (fragt nach dem Passwort)"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  # Auf Apple Silicon liegt brew nicht im Standard-PATH einer neuen Shell.
  [ -x /opt/homebrew/bin/brew ] && eval "$(/opt/homebrew/bin/brew shellenv)"
else
  echo "  Homebrew: $(brew --version | head -1)"
fi

schritt "2/6  uv (Python-Werkzeug des Projekts)"
if ! command -v uv >/dev/null 2>&1; then
  brew install uv
else
  echo "  uv: $(uv --version)"
fi

schritt "3/6  Brave"
# Die Station öffnet ihre Fenster mit Brave. Chrome tut es auch (gleicher
# Motor), aber start-mac.sh sucht Brave zuerst.
if [ ! -d "/Applications/Brave Browser.app" ] && [ ! -d "/Applications/Google Chrome.app" ]; then
  echo "  weder Brave noch Chrome gefunden — installiere Brave"
  brew install --cask brave-browser
else
  echo "  Browser: vorhanden"
fi

schritt "4/6  Repo klonen"
# Nur EIN Repo. Es gibt keine Submodule (geprüft 2026-09-01) — wer hier eine
# Liste weiterer Repos erwartet: die Station braucht keine.
if [ -d "$ZIEL/.git" ]; then
  echo "  liegt schon da: $ZIEL"
  git -C "$ZIEL" pull --ff-only || echo "  (pull übersprungen — lokale Änderungen?)"
else
  mkdir -p "$(dirname "$ZIEL")"
  git clone "$REPO" "$ZIEL"
fi
cd "$ZIEL"
echo "  Stand: $(git log --oneline -1)"

schritt "5/6  Python-Umgebung"
# `uv sync` liest pyproject.toml und legt .venv an. Braucht Python >= 3.12;
# uv lädt es bei Bedarf selbst nach.
uv sync
echo "  fertig: $(uv run python --version)"

schritt "6/6  Prüfen, was noch fehlt"
FEHLT=0

if [ ! -f .env ]; then
  echo ""
  echo "  🔴 .env FEHLT. Vorlage: docs/env-vorlage-eu.txt"
  echo ""
  echo "     Von der laufenden Station abgelesen -- genau DREI Variablen:"
  echo "        HERMES_CUSTOM_API_INFOMANIAK_COM_API_KEY=   (Pflicht: Analyse,"
  echo "                                    Weckwort und Embeddings, EU/Schweiz)"
  echo "        BFL_API_KEY=                (Pflicht fuer den Traum, EU/DE)"
  echo "        KG_TELEGRAM_TOKEN=          (nur alter Foto-Weg, meist leer)"
  echo ""
  echo "     ANTHROPIC_API_KEY und OPENROUTER_API_KEY werden NICHT gebraucht."
  echo "     Sie stehen zwar in config.example.toml, die Station setzt aber"
  echo "     keinen von beiden -- die Installation laeuft ueber EU-Anbieter."
  echo ""
  echo "     Anlegen als $ZIEL/.env"
  FEHLT=1
else
  echo "  .env: da"
  for k in HERMES_CUSTOM_API_INFOMANIAK_COM_API_KEY BFL_API_KEY; do
    if grep -qE "^${k}=." .env 2>/dev/null; then
      echo "     $k: gesetzt"
    else
      echo "     🔴 $k: FEHLT"
      FEHLT=1
    fi
  done
fi

# 🔴 Der Traum lief auf der Station ueber OPENROUTER, obwohl der BFL-Schluessel
# danebenlag: in ihrer config.toml stand keine einzige image_-Zeile, also galt
# die Vorgabe aus kg2/config.py (openrouter + google/gemini-3-pro-image). Das
# ist ein US-Weg. Wer die EU-Kette will, braucht die vier Zeilen aus
# docs/env-vorlage-eu.txt in der config.toml.
if [ -f config.toml ]; then
  if ! grep -qE '^\s*image_api_mode' config.toml 2>/dev/null; then
    echo ""
    echo "  🔴 config.toml setzt image_api_mode NICHT -> es gilt die Vorgabe"
    echo "     'openrouter' (US-Weg ueber Google), und BFL bleibt ungenutzt."
    echo "     Fuer die EU-Kette eintragen:"
    echo "        image_api_mode    = \"bfl\""
    echo "        image_url         = \"https://api.eu.bfl.ai/v1\""
    echo "        image_model       = \"flux-pro-1.1\""
    echo "        image_api_key_env = \"BFL_API_KEY\""
    FEHLT=1
  elif grep -q 'image_api_mode.*bfl_proxy' config.toml 2>/dev/null; then
    echo ""
    echo "  🔴 image_api_mode = bfl_proxy laeuft NUR auf dem vServer."
    echo "     Auf diesem Rechner stattdessen \"bfl\" verwenden."
    FEHLT=1
  fi
fi

if [ ! -f config.toml ]; then
  # config.toml steht in .gitignore (geprueft 2026-09-01), kommt also nie ueber
  # git mit. Die Vorlage liegt aber im Repo -- also einfach kopieren.
  if [ -f config.example.toml ]; then
    cp config.example.toml config.toml
    echo "  config.toml: aus config.example.toml angelegt (Werte pruefen!)"
  else
    echo "  🔴 config.toml UND config.example.toml fehlen."
    FEHLT=1
  fi
else
  echo "  config.toml: da"
fi

# Die Datenbank kommt NICHT über git (sie enthält echte Interviews).
if [ ! -f data/kg.db ]; then
  echo "  Hinweis: data/kg.db fehlt. Für einen leeren Start ist das richtig —"
  echo "  der Kern legt sie beim ersten Lauf an. Für die Demodaten:"
  echo "     uv run python -m sim.seed_graph --out data --persons 60 --gesichter"
fi

cat <<HINWEIS

=========================================================
  Starten:
      cd $ZIEL
      ./scripts/start-mac.sh

  Beim ERSTEN Start von Hand nötig: das Wandfenster auf den richtigen
  Schirm schieben und dort auf Vollbild setzen. macOS lässt das nicht
  per Startschalter erzwingen; dank getrennter Browserprofile merkt es
  sich die Platzierung danach.

  Adressen:
      Touchfläche   http://127.0.0.1:8800/projection?touch=1
      Bedienpult    http://127.0.0.1:8800/operator
      Plenarsaal    http://127.0.0.1:8800/plenum
      Saal-Pult     http://127.0.0.1:8800/operator-plenum
      Touch-Test    http://127.0.0.1:8800/touchtest

  Vor dem Publikum: docs/CHECKLISTE-ausstellungstag.md
=========================================================
HINWEIS

exit $FEHLT
