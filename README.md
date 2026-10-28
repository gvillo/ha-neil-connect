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
| [Maxiclima Essence](https://neil.com.ar/productos/essence/) | ❌ Not supported |
| [Neil Master](https://neil.com.ar/productos/master/) | ❌ Not supported |
| [Neil Slim Full](https://neil.com.ar/productos/slim-full/) | 🟡 Expected |
| [Neil Camper](https://neil.com.ar/productos/camper/) | ✅ Tested |
| [Neil Camper Patagonia](https://neil.com.ar/productos/camperpatagonia/) | 🟡 Expected |
| [Neil Camper Solar](https://neil.com.ar/productos/camper-solar/) | 🟡 Expected |
| [Neil Premium 700](https://neil.com.ar/productos/premium-700/) | 🟡 Expected |
| [Aires acondicionados](https://neil.com.ar/aa/) | ❌ Not supported |
| [Calderas](https://neil.com.ar/caldera/) | ❌ Not supported |

Essence and Master climatizadores, [Aires acondicionados](https://neil.com.ar/aa/) and [calderas](https://neil.com.ar/caldera/) do not include the Neil Connect controller. Neil's page for Slim Full 24 V lists a Premium controller instead of Connect. Slim Full 12 V, Camper, Camper Patagonia, Camper Solar, and Premium 700 are listed with Connect.

## Climate card

The entity to put on a dashboard is the climate entity, named **Climatizador**. Add a **Thermostat** card and select it. An Entities card only shows on and off. Fan speed and the target live on the Thermostat card and in the entity dialog you get by tapping the card.

There is no separate fan entity. Speed is the fan mode on this climate entity, **1** through **10**.

The unit has no temperature probe and the protocol has no setpoint. Modes are **Off**, **Fan only**, and **Cool**. **Off** stops the fan and the pump and leaves the light alone. **Fan only** runs the fan with the pump off. **Cool** runs the fan with the pump on. The pump is the evaporative cooling.

### No room sensor

The card has the three modes and the fan speeds. It has no current temperature and no target dial.

Choosing a speed while the unit is **Off** starts **Fan only**.

### With a room sensor

On the integration, open **Configure** and set **Room temperature** to any temperature sensor. That reading is shown on the card. It is not sent to the climatizador. Clear it to remove the target.

The card then shows the sensor in the middle and a target dial. The dial starts at 24 °C (75 °F) and runs from 16–35 °C (61–95 °F), in steps of 0.5 °C (1 °F). The target is stored in Home Assistant.

**Cool** is the only mode that uses the target. This is an evaporative climatizador, not an air conditioner, and it cools slowly. The pump starts while the room is still under the target, instead of waiting until the room is warmer than the target:

- The fan starts and stays on.
- The pump turns on when the room rises to 0.5 °C below the target (1 °F).
- The pump turns off when the room falls to 1 °C below the target (2 °F).
- Between those two points the pump does not change. A noisy sensor will not chatter it.
- With the pump off, the card says **Idle**. With the pump on, it says **Cooling**.
- **Fan only** and **Off** do not cycle the pump.
- At the minimum target, 16 °C (61 °F), the pump is not cycled. **Cool** turns the fan and the pump on and leaves them. The **Cooling** switch then holds, on or off, until the target is raised.

If that sensor is unavailable, the card behaves as if no sensor were selected: no current temperature, no target, and **Cool** just turns the fan and the pump on. The saved target comes back when the sensor reports again. If the room never falls to 1 °C below the target, which is normal for evaporative cooling, the pump stays on.

Selecting **Cool** does not resume by itself. A restart reads the fan and the pump from the unit and keeps the target. If the fan is off, the mode is **Off**. Select **Cool** again to run.

The **Cooling** switch still writes the pump directly. Outside that span, the next sensor update in **Cool** puts the pump back. Between 1 °C and 0.5 °C below the target, that switch holds. At the minimum target it holds either way.

## Other entities

- **Cooling**. The pump. On the climate card, **Cool** and **Fan only** already set this. With a room sensor, **Cool** keeps writing it to hold the target, except at the minimum target.
- **Light**. The courtesy light. Current hardware ignores this bit. It is still sent so a power write does not clear it.
- **Water level**. Power-frame byte 5 is `0` for an empty tank and `1` when it has water. Those are the only values seen on the Camper. Neil Connect 2.2.0 stores the byte as `waterLevel` and no screen reads it. The pump row caption **DEPÓSITO VACÍO** is fixed text. A power write puts a constant `1` in that byte, so an echoed command is not a tank reading. Any other value shows as unknown.
- **Timer hours**, a slider from 0 to 5. The app calls this sleep mode (**MODO ESPERA**) and labels `1h` through `5h`. `0` turns the timer off. `1`–`5` send `setTimer(on, hours)`. Byte 2 of the timer frame is `sleepSelectedHour`, and the app copies that byte back onto the slider. The app itself turns sleep mode off with a separate standby control.
- **Timer remaining hours**, a sensor of timer byte 3. The app names that byte `sleepCurrentHour`, stores it, and does not show it. It is not confirmed to be hours remaining.
- **Signal strength**, a diagnostic sensor, disabled by default. Enable it from the device page. It is the Bluetooth scanner's last advertisement RSSI in dBm. The climatizador does not send it. A held connection can stop advertisements, so the value may sit still until the next one.

The integration polls every 60 seconds and holds the GATT connection until the config entry is unloaded. **Poll interval**, on the device page under configuration, changes that in seconds from 10 to 3600. A read that echoes the query or hangs drops the connection and tries once more in that same poll.

Firmware opcodes exist in the app and are unused here. There is no firmware entity.

## Maintenance

The Camper manual calls for preventive maintenance every 300 hours of use, and a new evaporator filter every 900 hours. The climatizador does not count those hours. This integration does, while the fan is on.

The procedure is in the [manual](https://neil.com.ar/wp-content/uploads/2023/05/Manual-de-Uso-e-Instalacion-Linea-Slim-_ARG_V02-Connect.pdf) and on [Neil's maintenance page](https://neil.com.ar/soporte-tecnico/mantenimiento/). Both links are included in the repair.

- **Operating hours**. Total fan runtime since counting started.
- **Service**, a sensor. Counts down from 300 h. At 0 the service repair opens.
- **Hours until filter replacement**. Counts down from 900 h. At 0 the filter repair opens.
- **Service**, a binary sensor. On when the 300 h service is due. Home Assistant raises a repair with the steps.
- **Evaporator filter**. On when the filter replacement is due. Home Assistant raises a repair.
- **Reset service**. Sets Service back to 300 h.
- **Reset filter and service**. Sets Hours until filter replacement back to 900 h and Service back to 300 h. Replacing the filter is part of that same service.

A poll gap longer than 5 minutes is not counted. Time while Home Assistant is stopped is not counted. The courtesy light does not count. The pump does not count unless the fan is on.

Before leaving the unit unused for a long time, the manual says to run it for 3 hours with pre-cooling off so the evaporator filter dries. There is no entity for that. Turn the pump off and leave the fan on.

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
