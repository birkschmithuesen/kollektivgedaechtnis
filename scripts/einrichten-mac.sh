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

# --- config2.toml: der Traum hat eine EIGENE Konfigurationsdatei ------------
# 🔴 Das hatte ich zuerst falsch: Ich suchte die image_-Zeilen in config.toml
# und meldete sie als fehlend. Sie stehen aber in config2.toml -- kg2 wird mit
# `--config config2.toml` gestartet (so macht es die Windows-Startdatei), und
# dort ist die EU-Kette bereits vollstaendig eingetragen:
#     image_api_mode    = "bfl"
#     image_model       = "flux-2-pro-preview"
#     image_url         = "https://api.eu.bfl.ai/v1"
#     image_api_key_env = "BFL_API_KEY"
if [ ! -f config2.toml ]; then
  if [ -f config2.example.toml ]; then
    cp config2.example.toml config2.toml
    echo "  config2.toml: aus der Vorlage angelegt"
    echo "     🔴 Die Vorlage steht auf OPENROUTER (US-Weg ueber Google)."
    echo "        Fuer die EU-Kette diese vier Zeilen setzen:"
    echo "           image_api_mode    = \"bfl\""
    echo "           image_model       = \"flux-2-pro-preview\""
    echo "           image_url         = \"https://api.eu.bfl.ai/v1\""
    echo "           image_api_key_env = \"BFL_API_KEY\""
    FEHLT=1
  else
    echo "  🔴 config2.toml fehlt und es gibt keine Vorlage."
    FEHLT=1
  fi
else
  if grep -qE '^\s*image_api_mode\s*=\s*"bfl"' config2.toml 2>/dev/null; then
    echo "  config2.toml: da, Bildweg steht auf BFL (EU)"
  elif grep -q 'bfl_proxy' config2.toml 2>/dev/null; then
    echo "  🔴 config2.toml steht auf bfl_proxy -- das laeuft NUR auf dem"
    echo "     vServer. Hier stattdessen \"bfl\" verwenden."
    FEHLT=1
  else
    echo "  🔴 config2.toml: Bildweg NICHT auf bfl -> laeuft ueber OpenRouter"
    echo "     (US-Weg ueber Google), BFL_API_KEY bleibt ungenutzt."
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
