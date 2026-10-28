# Contributing

Issues and pull requests are welcome on [gvillo/ha-neil-connect](https://github.com/gvillo/ha-neil-connect).

## What lives where

The integration is `custom_components/neil_connect`. Home Assistant loads that directory. `hacs.json` is the HACS custom-repository manifest. The protocol notes in the README match Neil Connect 2.2.0 (`br.com.neil.app`).

## Local check

```bash
python3 -m compileall custom_components/neil_connect
```

There is no device simulator in this repo. A change to the BLE session needs a climatizador in pair mode, with the official app disconnected. One central at a time.

Debug logging:

```yaml
logger:
  logs:
    custom_components.neil_connect: debug
```

Logs may include the pairing marker and the frame length. Do not add logs of the access key, and do not commit a real BLE address from a house or a vehicle.

## Protocol changes

Byte layout, opcodes, and the `P` / `Q` / `R` handshake are documented in the README. A command reply of 6 bytes whose first byte is not `0` is success. A status read that comes back equal to the query is not device state. If a frame from the app disagrees with this repo, prefer a capture from the climatizador over a guess.

## Compatibility

The climatizador list is [neil.com.ar/productos](https://neil.com.ar/productos/). [Camper](https://neil.com.ar/productos/camper/) is the tested unit. Essence and Master have no BLE module. A report for another model should name the product page and whether the panel is the Connect controller (the peripheral advertises `MAXICLIMA`). Aires acondicionados and calderas do not use that controller.
