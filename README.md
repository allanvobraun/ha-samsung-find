# Samsung Find for Home Assistant

`samsung_find` is a HACS custom integration that triggers Samsung Find to ring a Samsung phone from Home Assistant, including the same "ring while silent" behavior exposed by Samsung Find's web UI when Samsung allows it for the device.

This integration is unofficial. It relies on reverse-engineered Samsung web flows and may break whenever Samsung changes the SmartThings Find / Samsung Find service.

## Features

- QR-based Samsung sign-in inside the Home Assistant config flow
- One selected Samsung phone per config entry
- Button entity to ring the phone
- `samsung_find.ring_device` service for automations
- Battery sensor when Samsung returns battery information for the selected device
- Reauth flow when the Samsung session expires

## Installation

### HACS

1. Add this repository to HACS as a custom repository with category `Integration`.
2. Install `Samsung Find`.
3. Restart Home Assistant.
4. Add the integration from `Settings -> Devices & Services`.

### Manual

Copy `custom_components/samsung_find` into your Home Assistant configuration directory and restart Home Assistant.

## Setup

1. Start the `Samsung Find` config flow.
2. Scan the QR code with your Samsung account.
3. Wait for authentication to complete.
4. Choose the phone to manage.

## Notes

- The integration uses Samsung cloud services. It does not provide a local-only path.
- Ringing works only if Samsung Find itself can ring the same device from the web.
- The integration stores the minimum session material needed to call Samsung Find later. If Samsung invalidates it, Home Assistant will require reauthentication.

## Service

`samsung_find.ring_device`

Targets:

- device
- entity

If only one `samsung_find` config entry exists, the service can be called without an explicit target.

## Development

- Runtime validation is implemented with Pydantic DTOs.
- The repository includes pytest-based unit tests and CI for `hassfest` plus HACS validation.

## Disclaimer

This project is not affiliated with or endorsed by Samsung, SmartThings, or Home Assistant.
