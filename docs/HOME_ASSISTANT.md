# Home Assistant

KP Lager liefert unter `GET /api/v1/ha` einen fertigen Sensor-Datensatz:
`state` = Anzahl Teile unter Mindestbestand, dazu Attribute (Nachkaufliste, Ablauf, Inventur fällig,
Zu sortieren, Etiketten wartend, offene Entnahmen und Projekte, Lagerwert, Backup-Status, Version).
Einzelne Teile (z. B. Filament-Spulen) gibt es unter `GET /api/v1/ha/item/<CODE>`.

## Schlüssel
Lesen ist im LAN ohne Schlüssel möglich. Ist „API: auch Lesen nur mit Schlüssel“ an (Einstellungen › Betrieb),
unter Einstellungen › Admin einen **Lesen**-Schlüssel anlegen und in Home Assistant als Secret hinterlegen:
```yaml
# secrets.yaml
kp_lager_key: kpl_…
```

## configuration.yaml
```yaml
rest:
  - resource: https://lager.home.lan/api/v1/ha
    scan_interval: 300
    verify_ssl: false            # eigene CA; besser: CA in HA hinterlegen und true lassen
    headers:
      X-API-Key: !secret kp_lager_key
    sensor:
      - name: "Lager nachkaufen"
        unique_id: kp_lager_nachkaufen
        value_template: "{{ value_json.state }}"
        unit_of_measurement: "Teile"
        icon: mdi:cart-arrow-down
        json_attributes_path: "$.attributes"
        json_attributes: [to_buy_items, to_buy_eur, expired, expiring, expiring_items,
                          unsorted, inventory_due, labels_waiting, open_withdrawals,
                          open_projects, items, value_eur, last_backup, backup_ok, version]
      - name: "Lager läuft ab"
        unique_id: kp_lager_ablauf
        value_template: "{{ value_json.attributes.expired + value_json.attributes.expiring }}"
        icon: mdi:timer-sand-alert
      - name: "Lagerwert"
        unique_id: kp_lager_wert
        value_template: "{{ value_json.attributes.value_eur }}"
        unit_of_measurement: "€"
        device_class: monetary
    binary_sensor:
      - name: "Lager Backup ok"
        unique_id: kp_lager_backup
        value_template: "{{ not value_json.attributes.backup_ok }}"
        device_class: problem

  - resource: https://lager.home.lan/api/v1/ha/item/FIL-001
    scan_interval: 900
    verify_ssl: false
    sensor:
      - name: "PLA schwarz Spulen"
        value_template: "{{ value_json.state }}"
        json_attributes_path: "$.attributes"
        json_attributes: [name, min, low, path]
```

## Benachrichtigung (Automation)
```yaml
automation:
  - alias: "Lager: Nachkauf-Hinweis"
    trigger:
      - platform: numeric_state
        entity_id: sensor.lager_nachkaufen
        above: 0
    action:
      - service: notify.mobile_app_handy
        data:
          title: "Nachkaufen ({{ states('sensor.lager_nachkaufen') }})"
          message: "{{ state_attr('sensor.lager_nachkaufen', 'to_buy_items') | join(', ') }}"
          data:
            url: https://lager.home.lan/einkauf
```

## Dashboard-Karte
```yaml
type: entities
title: Lager
entities:
  - sensor.lager_nachkaufen
  - sensor.lager_lauft_ab
  - sensor.lagerwert
  - binary_sensor.lager_backup_ok
```
