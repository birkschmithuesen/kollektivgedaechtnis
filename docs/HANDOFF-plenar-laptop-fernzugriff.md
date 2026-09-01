# Zweiter Rechner (Plenarsaal) — Fernzugriff einrichten + Brave auf die NVIDIA zwingen

Stand 2026-09-01, vor Ort während des Aufbaus.

## Was gerade ist

`yoga-260-conference` (Tailscale `100.104.169.106`) ist **online und sichtbar**,
aber **nicht fernsteuerbar**: SSH-Port 22 antwortet nicht, ebensowenig 5985
(WinRM). Auf dem Tracking-Laptop ist SSH eingerichtet, auf diesem Rechner nicht
— das ist der ganze Unterschied.

🔴 **Nicht verifizierbar von hier aus:** ob `yoga-260-conference` tatsächlich
der Plenarsaal-Rechner ist. Der Name legt es nahe, die Zuordnung ist aber
ungeprüft. Vor dem ersten Eingriff am Gerät gegenprüfen (`hostname` in der
PowerShell).

## Teil 1 — Brave auf die NVIDIA zwingen (2 Minuten, ohne Fernzugriff)

Das ist derselbe Eingriff, der auf dem Tracking-Laptop gewirkt hat: Windows
ordnet einer Anwendung ohne ausdrückliche Vorgabe die **sparsame** Grafikkarte
zu, und bei Brave heißt das: der 4K-Schirm hängt an der starken Karte, gerendert
wird aber auf der schwachen.

**Über die Oberfläche:**

1. `Einstellungen` → `System` → `Anzeige` → `Grafik`
2. `Durchsuchen` → `C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe`
3. Beim Eintrag auf `Optionen` → **Hohe Leistung** → `Speichern`
4. **Brave komplett beenden und neu starten** — sonst wirkt es nicht.

**Oder als eine Zeile in der PowerShell** (dasselbe, nur ohne Klicken):

```powershell
$p='HKCU:\Software\Microsoft\DirectX\UserGpuPreferences'
if (-not (Test-Path $p)) { New-Item -Path $p -Force | Out-Null }
New-ItemProperty -Path $p -Name 'C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe' -Value 'GpuPreference=2;' -PropertyType String -Force
```

**Prüfen, ob es gewirkt hat:** Task-Manager → Reiter `Leistung` → die beiden
GPUs vergleichen. Vorher lag die interne bei ~72 %, die dedizierte bei ~30 %.
Nach dem Neustart von Brave sollte sich das umkehren.

## Teil 2 — Fernzugriff einrichten (einmalig, ~5 Minuten)

Danach kann der Agent den Rechner genauso bedienen wie den Tracking-Laptop.

**In einer PowerShell als Administrator:**

```powershell
# 1. OpenSSH-Server installieren (ist in Windows enthalten, nur nicht aktiv)
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0

# 2. Dienst starten und dauerhaft aktivieren
Start-Service sshd
Set-Service -Name sshd -StartupType Automatic

# 3. Firewall (die Regel fehlt manchmal)
New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH Server (sshd)' `
  -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22
```

**Dann den Schlüssel des vServers eintragen** — das ist der Teil, der ohne
Passwort funktioniert und keine Zugangsdaten in einen Chat legt. Auf dem
Zielrechner, in derselben PowerShell:

```powershell
$k = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGINQlJupdTpILZ8vNAvtvKLKeM1tuIwQOxfINL+lcZj birk-vserver'
$d = "$env:USERPROFILE\.ssh"
New-Item -ItemType Directory -Force -Path $d | Out-Null
Add-Content -Path "$d\authorized_keys" -Value $k
```

🔴 Für **Administrator-Konten** gilt unter Windows eine Sonderregel: der
Schlüssel muss zusätzlich nach
`C:\ProgramData\ssh\administrators_authorized_keys`, sonst wird er ignoriert.
Für ein normales Benutzerkonto reicht `authorized_keys` im Profil.

**Gegenprobe vom vServer aus** (macht der Agent):

```
ssh <benutzer>@100.104.169.106 'hostname'
```

## Warum das die Mühe wert ist

Auf dem Tracking-Laptop hat der Fernzugriff heute mehrfach den Unterschied
gemacht: Auflösungen messen, GPU-Auslastung je Prozess aufschlüsseln, Dateien
einspielen, Dienste prüfen — alles ohne dass jemand vom Aufbau weg musste. Für
den zweiten Rechner gilt dasselbe, und der Aufwand fällt genau einmal an.
