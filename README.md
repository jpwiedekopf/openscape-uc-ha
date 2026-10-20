# OpenScape UC for Home Assistant

Custom integration that connects Home Assistant to an OpenScape UC web client.

## Features

- **Preferred device** select entity: shows and switches the device calls are
  routed to (e.g. office phone, home desk phone, mobile).

## Installation (HACS)

1. In HACS, add this repository as a custom repository (type: Integration).
2. Install **OpenScape UC** and restart Home Assistant.
3. Go to *Settings → Devices & services → Add integration* and search for
   **OpenScape UC**.

## Configuration

| Field                       | Description                                                  |
| --------------------------- | ------------------------------------------------------------ |
| Web client URL              | Base URL of the OpenScape UC web client                      |
| Username / Password         | Your OpenScape UC credentials                                |
| Trust internal certificates | Skip TLS verification for servers using an internal CA       |
