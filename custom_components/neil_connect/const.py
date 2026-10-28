"""Constants and frame codec for Neil Connect.

Opcodes are the on-wire byte 0. Neil Connect 2.2.0 has two equipment
tables. The one `tryAutoConnect` installs before every saved-key session is
SET_POWER 1, SET_TIMER 2, STATUS_POWER 1, STATUS_TIMER 2. `arrayConsulta`
then adds 2, so status reads go out as 3 and 4. The exported
DEFAULT_EQUIPMENT table (STATUS_POWER 3) is overwritten on that path and is
not what the app polls with. Firmware reads are unused.
"""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "neil_connect"

SERVICE_UUID: Final = "b5180b36-e157-47a9-aeba-48a403cdb78a"
CHAR_UUID: Final = "44df0f65-5724-4b6f-a95b-5e4379ebac2a"

CONF_ACCESS_KEY: Final = "access_key"
CONF_TEMPERATURE_SENSOR: Final = "temperature_sensor"

DEFAULT_TITLE: Final = "Neil climatizador"
LOCAL_NAME_MARK: Final = "MAXICLIMA"

PAIR_MARKER: Final = 0x50
KEY_MARKER: Final = 0x51
ACCEPTED_MARKER: Final = 0x52

OPCODE_WRITE_POWER: Final = 1
OPCODE_WRITE_TIMER: Final = 2
OPCODE_READ_POWER: Final = 3
OPCODE_READ_TIMER: Final = 4

FRAME_LENGTH: Final = 6
SPEED_MAX: Final = 10
TIMER_HOURS_MIN: Final = 0
TIMER_HOURS_MAX: Final = 5

# Camper manual. Preventive service every 300 h. New evaporator filter every 900 h.
SERVICE_INTERVAL_HOURS: Final = 300
FILTER_INTERVAL_HOURS: Final = 900
MANUAL_URL: Final = (
    "https://raw.githubusercontent.com/gvillo/ha-neil-connect/main/manuals/"
    "Manual-de-Uso-e-Instalacion-Linea-Slim-_ARG_V02-Connect.pdf"
)
MAINTENANCE_URL: Final = "https://neil.com.ar/soporte-tecnico/mantenimiento/"

COMMAND_DELAY_SECONDS: Final = 0.6
PAIR_DELAY_SECONDS: Final = 1.0
UPDATE_INTERVAL_SECONDS: Final = 60
POLL_INTERVAL_MIN: Final = 10
POLL_INTERVAL_MAX: Final = 3600

READ_POWER: Final = bytes((OPCODE_READ_POWER, 1, 1, 1, 1, 1))
READ_TIMER: Final = bytes((OPCODE_READ_TIMER, 1, 1, 1, 1, 1))


def power_frame(fan_on: bool, speed: int, pump_on: bool, bulb_on: bool) -> bytes:
    """Build a 6-byte power write. The last byte is always 1."""
    clamped = max(0, min(SPEED_MAX, int(speed)))
    return bytes(
        (
            OPCODE_WRITE_POWER,
            1 if fan_on else 0,
            clamped,
            1 if pump_on else 0,
            1 if bulb_on else 0,
            1,
        )
    )


def timer_frame(timer_on: bool, hours: int) -> bytes:
    """Build a 6-byte timer write."""
    hour_byte = max(0, min(255, int(hours)))
    return bytes(
        (
            OPCODE_WRITE_TIMER,
            1 if timer_on else 0,
            hour_byte,
            1,
            1,
            1,
        )
    )


def parse_power(frame: bytes) -> tuple[bool, int, bool, bool, int] | None:
    """Parse power state from bytes 1-5. Byte 0 is ignored.

    Returns fan_on, speed, pump_on, bulb_on, water_level. Speed above 10 is
    clamped. Flags are on only when the byte is 1. None when the frame is
    shorter than 6 bytes.
    """
    if len(frame) < FRAME_LENGTH:
        return None
    speed = frame[2]
    if speed > SPEED_MAX:
        speed = SPEED_MAX
    return (frame[1] == 1, speed, frame[3] == 1, frame[4] == 1, frame[5])


def parse_timer(frame: bytes) -> tuple[bool, int, int] | None:
    """Parse timer state. Returns timer_on, selected hours, remaining hours."""
    if len(frame) < FRAME_LENGTH:
        return None
    return (frame[1] == 1, frame[2], frame[3])
