# Neil Connect

<p align="center">
  <img src="https://raw.githubusercontent.com/gvillo/ha-neil-connect/main/custom_components/neil_connect/brand/logo.png" alt="Neil" width="320">
</p>

[![GitHub release](https://img.shields.io/github/v/release/gvillo/ha-neil-connect)](https://github.com/gvillo/ha-neil-connect/releases)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

Home Assistant integration for [Neil](https://neil.com.ar/) evaporative climatizadores that use the Neil Connect app (`br.com.neil.app`, 2.2.0) over BLE. It is a [HACS](https://hacs.xyz/) custom repository. It is not in the default HACS store and it is not part of Home Assistant core.

## Installation

Requires Home Assistant 2026.10.0 or newer, with the Bluetooth integration running.

You can install this integration via [HACS](#hacs) or [manually](#manual). After a restart, pair it from the integrations page or press the button below.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=gvillo&repository=ha-neil-connect&category=integration)

### HACS

1. Click the badge above. It opens this repository in HACS with category **Integration** already selected. Add it.
2. In HACS, open **Neil Connect** and download it.
3. Restart Home Assistant.

If the badge does not reach your instance: HACS → Integrations → overflow menu → **Custom repositories** → `https://github.com/gvillo/ha-neil-connect` → category **Integration**. Then download **Neil Connect** and restart.

### Manual

1. Download this repository.
2. Copy `custom_components/neil_connect` into Home Assistant's `config/custom_components/` directory.
3. Restart Home Assistant.

### Setup

1. Disconnect the official Neil Connect app. The climatizador accepts one BLE central.
2. On the remote, power off, then hold `+` and `−` for 5 seconds until the Bluetooth icon blinks.
3. In Home Assistant, go to **Settings → Devices & services**.
4. Select **Add integration** and choose **Neil Connect**.

## Compatibility

The catalog is [Neil climatizadores](https://neil.com.ar/productos/). The integration speaks the Connect controller, the BLE peripheral that advertises `MAXICLIMA`. [Camper](https://neil.com.ar/productos/camper/) is the unit this was tested on. The other Connect models use that same app.

| Model | Status |
| --- | --- |
| [Maxiclima Essence](https://neil.com.ar/productos/essence/) | Not supported / no BLE module |
| [Neil Master](https://neil.com.ar/productos/master/) | Not supported / no BLE module |
| [Neil Slim Full](https://neil.com.ar/productos/slim-full/) | Expected |
| [Neil Camper](https://neil.com.ar/productos/camper/) | Tested |
| [Neil Camper Patagonia](https://neil.com.ar/productos/camperpatagonia/) | Expected |
| [Neil Camper Solar](https://neil.com.ar/productos/camper-solar/) | Expected |
| [Neil Premium 700](https://neil.com.ar/productos/premium-700/) | Expected |
| Aires acondicionados | Not supported |
| Calderas | Not supported |

Essence and Master have no BLE module. Aires acondicionados and calderas do not include the Neil Connect controller. Neil's page for Slim Full 24 V lists a Premium controller instead of Connect. Slim Full 12 V, Camper, Camper Patagonia, Camper Solar, and Premium 700 are listed with Connect.

## Controls

- Climate: **Off**, **Fan only**, or **Cool**. Cool is the fan plus the evaporative pump. Fan speeds on that entity are 1–10. Off stops the fan and the pump and leaves the light alone. There is no temperature setpoint in the protocol. Configure the integration to show any temperature sensor as the room temperature. That value is display-only.
- Fan on/off and speed 0–10, shown as 0–100% in steps of 10. Turning this fan off does not clear the pump.
- Evaporative cooling (the pump bit), entity name **Cooling**
- Courtesy light, entity name **Light**. Current hardware ignores this bit. It is still sent so a power write does not clear it
- Water level. Power-frame byte 5 is `0` for an empty tank and `1` when it has water. Those are the only values seen on the Camper. Neil Connect 2.2.0 stores the byte as `waterLevel` and no screen reads it. The pump row caption **DEPÓSITO VACÍO** is fixed text. A power write puts a constant `1` in that byte, so an echoed command is not a tank reading. Any other value shows as unknown.
- Timer hours, a slider from 0 to 5. The app calls this sleep mode (**MODO ESPERA**) and labels `1h` through `5h`. `0` turns the timer off. `1`–`5` send `setTimer(on, hours)`. Byte 2 of the timer frame is `sleepSelectedHour`, and the app copies that byte back onto the slider. The app itself turns sleep mode off with a separate standby control.
- Timer remaining hours, a diagnostic sensor of timer byte 3. The app names that byte `sleepCurrentHour`, stores it, and does not show it. It is not confirmed to be hours remaining.

Turning the fan off sends fan `0` and speed `0` and leaves cooling and light as they are. The integration polls every 30 seconds and holds the GATT connection until the config entry is unloaded.

Firmware opcodes exist in the app and are unused here. There is no firmware entity.

## Pairing

On the remote: power off, then hold `+` and `−` for 5 seconds until the Bluetooth icon blinks.

On setup the integration reads the characteristic:

- `P` (`0x50`) is a pairing payload. The first byte is set to `Q` (`0x51`), that buffer is stored, written back, and the follow-up read must be `R` (`0x52`)
- `Q` is stored as the key. `R` is only the reply to writing `Q`, not a key
- Anything else aborts. The remote has to be in pair mode, or another phone is still connected

The key is saved in the config entry as a list of integers. A stored `R` whose other bytes are zero is ignored, and that connection reads the characteristic again. A saved `Q` buffer with key bytes after the marker is written on later connections. Commands are sent only after the reply is `R`. The key is not logged.

## Example power frame

Fan on, speed 4, cooling on, light off:

```text
[1, 1, 4, 1, 0, 1]
```

| Byte | Value | Meaning |
| --- | --- | --- |
| 0 | 1 | write power |
| 1 | 1 | fan on |
| 2 | 4 | speed |
| 3 | 1 | pump / cooling on |
| 4 | 0 | light off |
| 5 | 1 | fixed |

The app rejects a command reply whose first byte is `0` or whose length is not 6. A 6-byte reply with any other first byte is success, and bytes 1–5 are the state. Status polls use opcodes 3 and 4 (`arrayConsulta` adds 2 to internal ids 1 and 2). Enable debug logs for `custom_components.neil_connect` to see the raw frames. The log line is the marker and the length, not the key.

## BLE

GATT, not Bluetooth Classic.

- Advertised local name contains `MAXICLIMA`
- Service `b5180b36-e157-47a9-aeba-48a403cdb78a`
- Characteristic `44df0f65-5724-4b6f-a95b-5e4379ebac2a`
- Write with response, wait 0.6 s, read that characteristic

Home Assistant indexes Bluetooth local names on their first three characters and rejects a leading wildcard, so the manifest matches the service UUID and names that start with `MAXICLIMA`. The manual picker still lists any discovered device whose name contains `MAXICLIMA`, or that advertises the service UUID.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Issues and ideas go to the [issue tracker](https://github.com/gvillo/ha-neil-connect/issues).
