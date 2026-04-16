# Cudy Router for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-blue.svg)](https://github.com/usersaynoso/ha-cudy-router)
[![Version](https://img.shields.io/badge/version-1.3.6-blue.svg)](https://github.com/usersaynoso/ha-cudy-router/releases)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-green.svg)](LICENSE.md)

`cudy_router` is a community-built Home Assistant integration for Cudy routers that expose a LuCI-based web interface.

It connects directly to the router over your local network, reads the same status and configuration pages you see in the browser, and turns them into Home Assistant entities, devices, and services.

This project is not endorsed, maintained, or supported by Cudy.


## Highlights

- Local polling integration with config flow and options flow
- Router-wide sensors for modem, WAN, LAN, DHCP, VPN, load balancing, Wi-Fi, SMS, traffic, and system status
- Writable router configuration exposed as Home Assistant `switch` and `select` entities
- Main router reboot button and service calls for advanced actions (SMS, AT commands, band switching)
- Mesh node support with separate Home Assistant devices, per-node LED control, and reboot
- Connected client support with separate Home Assistant devices
- Per-client control switches for internet access, DNS filter, and VPN
- Optional manual client tracking with `device_tracker` entities
- Clean Home Assistant device registry layout with router, mesh, and client devices split apart
- Automatic config entry migration from older versions


## Current Status

Only the **Cudy P5** has been tested on real hardware so far.

The integration includes an explicit model capability map so unsupported module families stay hidden instead of showing dead or non-functional entities. Unknown Cudy models fall back to best-effort dynamic detection.

The following devices are mapped but have **not** been tested on real hardware yet:

- **Routers:** WR11000, WR6500, WR3600H, TR3000, WR3000E, WR3000, WR1500, WR1300V4.0, WR1300E, WR1300EV2, TR1200, WR1200, WR300S, R700
- **4G/5G routers:** P2, LT15E, LT700E, LT500, LT400E, LT300V3, LT700-Outdoor, LT400-Outdoor, IR02
- **Mesh Wi-Fi:** M11000, M3000, M1500, M1200
- **Extenders:** RE3600, RE1500, RE1200, RE1200-Outdoor


## Installation

### HACS (recommended)

1. Open **HACS** in Home Assistant.
2. Open the menu in the top-right corner.
3. Choose **Custom repositories**.
4. Add `https://github.com/usersaynoso/ha-cudy-router` as an **Integration** repository.
5. Search for **Cudy Router** in HACS and install it.
6. Restart Home Assistant.

### Manual

1. Copy `custom_components/cudy_router` into your Home Assistant `custom_components` directory.
2. Restart Home Assistant.


## Setup

1. Go to **Settings > Devices & Services**.
2. Add the **Cudy Router** integration.
3. Enter the router IP address, username, and password.

The integration normalizes the host automatically. If you enter `192.168.10.1`, it will probe the router and store the working scheme as either `http://192.168.10.1` or `https://192.168.10.1`.


## Home Assistant Device Model

The integration is structured around three device classes.

### Main Router

The main router device is the parent device for the integration. Router-wide sensors, configuration entities, reboot actions, and router-level diagnostics live here.

Examples: modem and WAN status, traffic and SMS counters, DHCP and VPN sensors, Wi-Fi status sensors, writable router settings, main router LED control, and the reboot button.

### Mesh Nodes

Each detected mesh satellite is exposed as its own Home Assistant device under the main router.

Mesh node devices can expose: node name, model, MAC, IP, firmware, hardware, status, backhaul, connected-device count, a per-node LED switch, and a per-node reboot button.

### Connected Client Devices

Connected clients can also be exposed as separate Home Assistant devices under the main router.

Client devices can expose: IP address, connection type, signal, online time, internet access switch, DNS filter switch, and VPN switch.


## Entity Categories

The integration uses Home Assistant entity categories intentionally:

- Writable router settings live under **Configuration**.
- Technical read-only values live under **Diagnostic**.
- Operational controls like reboot buttons or per-client access switches remain normal control entities.


## Platforms

The integration creates entities on these Home Assistant platforms: `sensor`, `switch`, `select`, `button`, and `device_tracker`.


## Sensors

Entity availability depends on the router model and firmware. Not every router exposes every page or field.

### Modem / Cellular

Network, Signal strength, SIM slot, Connected time, Cell information, RSRP, RSRQ, SINR, RSSI, Band, Public IP, WAN IP, IMEI, IMSI, ICCID, Mode, Bandwidth, Session upload, Session download.

### WAN

Protocol, Connected time, Public IP, WAN IP, WAN Subnet mask, Gateway, DNS, WAN bytes received, WAN bytes sent, Session upload, Session download.

When both modem and WAN modules are present, duplicate fields (connected time, public IP, WAN IP, session upload/download) are suppressed from the WAN module to avoid redundant entities.

### Data Usage

Current session traffic, Monthly traffic, Total traffic.

### System

Uptime, Local time, Firmware version.

### SMS

SMS inbox, SMS outbox, SMS unread.

### Wi-Fi

WiFi 2.4G SSID, WiFi 2.4G channel, WiFi 5G SSID, WiFi 5G channel.

### LAN

LAN IP, Subnet mask, LAN MAC, Bytes received, Bytes sent.

### DHCP

IP Start, IP End, Preferred DNS, Default Gateway, Leasetime.

### VPN

VPN protocol, VPN clients, VPN tunnel IP.

### Load Balancing

Load balancing WAN1, Load balancing WAN2, Load balancing WAN3, Load balancing WAN4 (only for WANs currently shown by the router).

### Connected Device Summary

Device count, ARP br-lan count, WiFi 2.4G clients, WiFi 5G clients, Wired clients, Total clients, Top downloader speed, Top downloader MAC, Top downloader hostname, Top uploader speed, Top uploader MAC, Top uploader hostname, Total download speed, Total upload speed, Mesh devices connected.

### Connected Client Detail Sensors

When client devices are enabled, each matched connected client can expose: IP address, Connection type, Signal, Online time.

### Mesh Node Sensors

Each mesh node can expose: Name, Model, MAC address, Firmware, Status, IP address, Connected devices, Hardware, Backhaul.


## Switches

### Router Configuration Switches

Cellular enabled, Data roaming, Smart Connect, WiFi 2.4G enabled, WiFi 5G enabled, WiFi 2.4G hidden network, WiFi 5G hidden network, WiFi 2.4G separate clients, WiFi 5G separate clients, VPN enabled, VPN site-to-site, Auto update, LED (on mesh-capable firmware).

### Mesh Node Switches

LED (per node).

### Per-Client Switches

Internet access, DNS filter, VPN.


## Selects

SIM slot, Network mode, Network search, APN profile, PDP type, WiFi 2.4G mode, WiFi 2.4G channel width, WiFi 2.4G channel, WiFi 2.4G transmit power, WiFi 5G mode, WiFi 5G channel width, WiFi 5G channel, WiFi 5G transmit power, VPN protocol, VPN default rule, VPN client access, VPN policy, Auto update time.

Settings like the SIM slot can be changed directly from Home Assistant, for example switching between `Sim 1` and `Sim 2`.


## Buttons

### Main Router

Reboot.

### Mesh Nodes

Reboot (per node).


## Device Trackers

The integration supports `device_tracker` entities for manually selected clients.

Important behavior:

- `device_tracker` entities are opt-in.
- They are created from the **Manually Add Connected Devices** list.
- They are only created when **Automatically Add Connected Devices** is turned off.
- Manual matching supports MAC addresses, hostnames, and IP addresses.


## Integration Options

### Automatically Add Connected Devices

Disabled by default for new integrations.

When enabled, the integration creates client devices and live per-client entities for every currently connected device reported by the router.

### Manually Add Connected Devices

A comma-separated list of MAC addresses, hostnames, or IP addresses.

When **Automatically Add Connected Devices** is turned off, client entities and `device_tracker` entities are only created for devices matching this list. Stale auto-added client entities are removed.

### Update Interval

Controls how often the router is polled for new data. The default is **60 seconds**. Accepted range is 15 to 3600 seconds, in steps of 5.


## Services

### `cudy_router.reboot_router`

Reboots the router.

Optional fields: `entry_id`.

### `cudy_router.restart_5g_connection`

Restarts the router's cellular connection by triggering a modem reset.

Optional fields: `entry_id`.

### `cudy_router.switch_5g_band`

Changes the modem band/network-mode preference.

Fields: `band` (required), `entry_id` (optional).

The `band` field accepts shorthand values that are mapped to the firmware's network-mode selector: `auto`, `5g-only`, `lte-only`, `5g-nsa`. Any other value is passed through directly.

### `cudy_router.send_sms`

Sends an SMS through the router's modem.

Fields: `phone_number` (required), `message` (required), `entry_id` (optional).

### `cudy_router.send_at_command`

Sends a raw AT command to the modem and logs the result.

Fields: `command` (required), `entry_id` (optional).


## Example Service Calls

```yaml
service: cudy_router.reboot_router
data: {}
```

```yaml
service: cudy_router.send_sms
data:
  phone_number: "+441234567890"
  message: "Hello from Home Assistant"
```

```yaml
service: cudy_router.send_at_command
data:
  command: "AT+CSQ"
```

```yaml
service: cudy_router.switch_5g_band
data:
  band: "auto"
```


## What the Integration Reads

Depending on the detected router model and available pages, the integration reads and parses data from: modem/cellular status, connected device lists, system status, data-usage pages, SMS status, Wi-Fi status, LAN status, VPN status, DHCP status, WAN status, cellular configuration, wireless configuration, VPN configuration, auto-update configuration, and mesh status.


## Client Device Behavior

Client device creation is intentionally separate from router-level summary sensors.

Summary sensors like total clients and top uploader/downloader remain on the main router device. Per-client IP, signal, online time, internet access, and DNS filter entities live on client devices. Mesh node entities live on mesh devices. Router settings stay on the main router device.


## Limitations and Notes

- Feature coverage varies by router model and firmware.
- Some mesh values may be unavailable or reported as unknown if the router firmware does not expose them.
- Service calls such as band switching and raw AT commands are advanced operations and should be used carefully.
- The integration polls the router web UI. If the router is busy, rebooting, unreachable, or returns a different page layout, entities may be temporarily unavailable.
- If the router password changes, reauthentication is handled through the config entry.
- SSL certificate verification is disabled because Cudy routers use self-signed certificates.
- The integration supports multiple router instances. Use the optional `entry_id` field on service calls to target a specific one.


## Troubleshooting

### Entities Missing

Check that the router model actually exposes the relevant page or control, that the integration options for automatic or manual client creation are set correctly, and that Home Assistant has been restarted after updating the custom component.

### Too Many Client Devices

Turn off **Automatically Add Connected Devices** and use **Manually Add Connected Devices** instead.

### Client Device Did Not Match

The manual list accepts MAC addresses, hostnames, and IP addresses. Use the same value style the router reports in its connected-device table.

### Router Cannot Connect

Check the router IP address, username, and password, and confirm that Home Assistant can reach the router over the local network.


## Contributing

Issues and pull requests are welcome at [github.com/usersaynoso/ha-cudy-router](https://github.com/usersaynoso/ha-cudy-router).

When changing behavior, update the tests and keep the README in sync with the actual entity surface, options flow, and service list.


## License

This project is licensed under the [GNU General Public License v3.0](LICENSE.md).
