# Neil Connect

<p align="center">
  <img src="https://raw.githubusercontent.com/gvillo/ha-neil-connect/main/custom_components/neil_connect/brand/logo.png" alt="Neil" width="320">
</p>

Home Assistant integration for Neil climatizadores that speak the MAXICLIMA BLE GATT protocol from Neil Connect 2.2.0 (`br.com.neil.app`).

This is a [HACS](https://hacs.xyz/) custom repository. It is not part of Home Assistant core and it is not in the default HACS store. The wire format is from static analysis of that app's Hermes bundle and has not been confirmed against a live peripheral.

## Controls

- Fan on/off and speed 0–10, shown as 0–100% in steps of 10
- Evaporative cooling (the pump bit), entity name **Cooling**
- Courtesy light, entity name **Light**. Current hardware ignores this bit. It is still sent so a power write does not clear it
- Water level, a diagnostic sensor of the raw byte. There is no scale
- Timer hours, 0–24. `0` turns the timer off. `24` is a placeholder; the app did not expose a maximum
- Timer remaining hours, a diagnostic sensor of timer byte 3 (`currentHours`)

Turning the fan off sends fan `0` and speed `0` and leaves cooling and light as they are. The integration polls every 30 seconds and holds the GATT connection until the config entry is unloaded. The climatizador accepts one central. Disconnect the official app before setup.

Firmware opcodes exist in the app and are unused here. There is no firmware entity.

## Pairing

On the remote: power off, then hold `+` and `−` for 5 seconds until the Bluetooth icon blinks.

On setup the integration reads the characteristic:

- `P` (`0x50`) is a pairing payload. The first byte is set to `Q` (`0x51`), the buffer is stored, written back, and the follow-up read must be `R` (`0x52`)
- `Q` or `R` is stored as the key
- Anything else aborts. The remote has to be in pair mode, or another phone is still connected

The key is saved in the config entry as a list of integers and written again on later connections when it starts with `0x51`. It is not logged.

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

A write is acknowledged when the follow-up read is 6 bytes and byte 0 is `0`. Status reads are parsed from bytes 1–5 even when byte 0 is not `0`. Enable debug logs for `custom_components.neil_connect` to see the raw frames.

## BLE

GATT, not Bluetooth Classic.

- Advertised local name contains `MAXICLIMA`
- Service `b5180b36-e157-47a9-aeba-48a403cdb78a`
- Characteristic `44df0f65-5724-4b6f-a95b-5e4379ebac2a`
- Write with response, wait 0.6 s, read that characteristic

Home Assistant indexes Bluetooth local names on their first three characters and rejects a leading wildcard, so the manifest matches the service UUID and names that start with `MAXICLIMA`. The manual picker still lists any discovered device whose name contains `MAXICLIMA`, or that advertises the service UUID.

## Installation

Requires Home Assistant 2026.10.0 or newer, with the Bluetooth integration running. This is a custom repository. It is not in the default HACS store, and it is not part of Home Assistant core.

### Using HACS (recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=gvillo&repository=ha-neil-connect&category=integration)

1. Click the badge above. It opens this repository in HACS with category **Integration** already selected. Add it.
2. In HACS, open **Neil Connect** and download it.
3. Restart Home Assistant.

If the badge does not reach your instance: HACS → Integrations → overflow menu → **Custom repositories** → `https://github.com/gvillo/ha-neil-connect` → category **Integration**. Then download **Neil Connect** and restart.

### Manual installation

1. Download this repository.
2. Copy `custom_components/neil_connect` into Home Assistant's `config/custom_components/` directory.
3. Restart Home Assistant.

### Setup

1. Disconnect the official Neil Connect app. The climatizador accepts one BLE central.
2. On the remote, power off, then hold `+` and `−` for 5 seconds until the Bluetooth icon blinks.
3. In Home Assistant, go to **Settings → Devices & services**.
4. Select **Add integration** and choose **Neil Connect**.
