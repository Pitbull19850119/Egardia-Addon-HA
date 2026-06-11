# Egardia Alarm – Home Assistant Add-on Repository

[![Open your Home Assistant instance and show the add add-on repository dialog with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FPitbull19850119%2FEgardia-Addon-HA)

Steuere deine **Egardia / GATE Alarmanlage** direkt aus Home Assistant –  
**ohne lokale IP**, ausschließlich über das Egardia Cloud-Webinterface.

---

## 📦 Repository hinzufügen

### Option A – Ein-Klick (Badge oben)
Auf den Badge oben klicken → HA öffnet sich automatisch mit der Repository-URL.

### Option B – Manuell
1. HA → **Einstellungen → Add-ons → Add-on Store**
2. Oben rechts **⋮ → Benutzerdefinierte Repositories**
3. URL einfügen:
   ```
   https://github.com/Pitbull19850119/Egardia-Addon-HA
   ```
4. **Hinzufügen** → Add-on erscheint im Store → **Installieren**

---

## ⚙️ Konfiguration

| Option | Beschreibung | Standard |
|---|---|---|
| `egardia_username` | Egardia Login-E-Mail | – |
| `egardia_password` | Egardia Passwort | – |
| `egardia_server` | Server-URL | `https://www.egardia.com` |
| `poll_interval` | Abfrageintervall (Sek.) | `30` |
| `ha_long_lived_token` | HA Long-Lived Token (optional) | – |
| `log_level` | Log-Detail | `info` |

---

## 🔌 REST Commands für `configuration.yaml`

```yaml
rest_command:
  egardia_arm_away:
    url: "http://localhost:8765/api/alarm"
    method: POST
    content_type: "application/json"
    payload: '{"action": "arm_away"}'

  egardia_arm_home:
    url: "http://localhost:8765/api/alarm"
    method: POST
    content_type: "application/json"
    payload: '{"action": "arm_home"}'

  egardia_arm_night:
    url: "http://localhost:8765/api/alarm"
    method: POST
    content_type: "application/json"
    payload: '{"action": "arm_night"}'

  egardia_disarm:
    url: "http://localhost:8765/api/alarm"
    method: POST
    content_type: "application/json"
    payload: '{"action": "disarm"}'
```

## 🏠 Lovelace Karte

```yaml
type: alarm-panel
entity: alarm_control_panel.egardia
name: Egardia Alarmanlage
```

---

## 📁 Repo-Struktur

```
/                          ← GitHub Repo Root
├── repository.json        ← PFLICHT: Repository-Metadaten
├── README.md
└── egardia_alarm/         ← Add-on Ordner (slug = Ordnername)
    ├── config.yaml
    ├── Dockerfile
    ├── build.yaml
    ├── requirements.txt
    ├── egardia_addon.py
    └── rootfs/
        └── etc/services.d/egardia/
            ├── run
            └── finish
```

> ⚠️ **Wichtig:** `repository.json` **muss** im Root des Repos liegen,  
> und der Add-on-Ordner (`egardia_alarm/`) **muss** direkt im Root sein – nicht in Unterordnern!
