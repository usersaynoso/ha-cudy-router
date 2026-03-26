# Cudy Router for Home Assistant

`cudy_router` is a community-built Home Assistant integration for Cudy routers that expose a LuCI-based web interface.

It connects directly to the router over your local network, reads the same status and configuration pages you see in the browser, and turns them into Home Assistant entities, devices, and services.

This project is not endorsed, maintained, or supported by Cudy.

## Highlights

- Local polling integration with config flow support
- Router-wide sensors for modem, WAN, LAN, DHCP, VPN, Wi-Fi, SMS, traffic, and system status
- Writable router configuration entities exposed as Home Assistant `switch` and `select` entities
- Main router reboot button and optional service calls for advanced actions
- Mesh node support with separate Home Assistant devices
- Connected client support with separate Home Assistant devices
- Per-client control switches for internet access and DNS filter
- Optional manual client tracking with `device_tracker` entities
- Cleaner Home Assistant device registry layout with router, mesh, and client devices split apart

## Current Status

Only the **Cudy P5** has been tested on real hardware so far.

The integration now also includes an explicit model capability map for the emulator-backed devices below, so unsupported module families stay hidden instead of showing dead or non-functional entities.

These devices should be compatible but have **not** been tested on real hardware yet:

- Routers: `WR11000`, `WR6500`, `WR3600H`, `TR3000`, `WR3000E`, `WR3000`, `WR1500`, `WR1300V4.0`, `WR1300E`, `TR1200`, `WR1200`, `WR300S`
- 4G/5G routers: `P2`, `LT15E`, `LT700E`, `LT500`, `LT400E`, `LT300V3`, `LT700-Outdoor`, `LT400-Outdoor`, `IR02`
- Mesh Wi-Fi: `M11000`, `M3000`, `M1500`, `M1200`
- Extenders: `RE3600`, `RE1500`, `RE1200`, `RE1200-Outdoor`

Unknown Cudy models still fall back to best-effort dynamic detection, but the curated mapping above is what the integration uses to decide which entity families are expected on the listed devices.

## Installation

### HACS

At the time of writing, install it through HACS as a **custom repository**:

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

The integration normalizes the host automatically. If you enter `192.168.10.1`, it will be stored as `https://192.168.10.1`.

## Home Assistant Device Model

The integration is structured around three device classes.

### Main Router

The main router device is the parent device for the integration. Router-wide sensors, configuration entities, reboot actions, and router-level diagnostics live here.

Examples:

- modem and WAN status
- traffic and SMS counters
- DHCP and VPN sensors
- Wi-Fi status sensors
- writable router settings
- main router LED control
- reboot button

### Mesh Nodes

Each detected mesh satellite is exposed as its own Home Assistant device under the main router.

Mesh node devices can expose:

- node name, model, MAC, IP, firmware, hardware, status, and backhaul
- connected-device count when reported by the router
- per-node LED switch
- per-node reboot button

### Connected Client Devices

Connected clients can also be exposed as separate Home Assistant devices under the main router.

Client devices can expose:

- IP address
- connection type
- signal
- online time
- internet access switch
- DNS filter switch

## Entity Categories in Home Assistant

The integration uses Home Assistant entity categories intentionally:

- writable router settings live under **Configuration**
- technical read-only values live under **Diagnostic**
- operational controls like reboot buttons or per-client access switches remain normal control entities

## Platforms

The integration currently creates entities on these Home Assistant platforms:

- `sensor`
- `switch`
- `select`
- `button`
- `device_tracker`

## Sensors

Entity availability depends on the router model and firmware. Not every router exposes every page or field.

### Modem / Cellular

- Network
- Signal strength
- SIM slot
- Connected time
- Cell information
- RSRP
- RSRQ
- SINR
- RSSI
- Band
- Public IP
- WAN IP
- IMEI
- IMSI
- ICCID
- Mode
- Bandwidth
- Session upload
- Session download

### WAN

- Protocol
- Connected time
- Public IP
- WAN IP
- Subnet mask
- Gateway
- DNS
- Session upload
- Session download

### Data Usage

- Current session traffic
- Monthly traffic
- Total traffic

### System

- Uptime
- Local time
- Firmware version

### SMS

- SMS inbox
- SMS outbox
- SMS unread

### Wi-Fi

- WiFi 2.4G SSID
- WiFi 2.4G channel
- WiFi 5G SSID
- WiFi 5G channel

### LAN

- LAN IP
- LAN MAC

### DHCP

- IP Start
- IP End
- Preferred DNS
- Default Gateway
- Leasetime

### VPN

- VPN protocol
- VPN clients

### Connected Device Summary

- Device count
- WiFi 2.4G clients
- WiFi 5G clients
- Wired clients
- Total clients
- Top downloader speed
- Top downloader MAC
- Top downloader hostname
- Top uploader speed
- Top uploader MAC
- Top uploader hostname
- Total download speed
- Total upload speed
- Mesh devices connected

### Connected Client Detail Sensors

When client devices are enabled, each matched connected client can expose:

- IP address
- Connection type
- Signal
- Online time

### Manual Client Diagnostic Sensors

The integration does **not** create router-level MAC or hostname sensors from **Manually Add Connected Devices**.

That option is only used to:

- limit which connected clients become Home Assistant client devices when auto-add is off
- create opt-in `device_tracker` entities for those matched clients

### Mesh Node Sensors

Each mesh node can expose:

- Name
- Model
- MAC address
- Firmware
- Status
- IP address
- Connected devices
- Hardware
- Backhaul

## Switches

### Router Configuration Switches

Writable router switches currently include:

- Cellular enabled
- Data roaming
- Smart Connect
- WiFi 2.4G enabled
- WiFi 5G enabled
- WiFi 2.4G hidden network
- WiFi 5G hidden network
- WiFi 2.4G separate clients
- WiFi 5G separate clients
- VPN enabled
- VPN site-to-site
- Auto update
- LED on mesh-capable firmware

### Mesh Switches

- LED

### Per-Client Switches

Matched client devices can expose:

- Internet access switch
- DNS filter switch

## Selects

Writable router selects currently include:

- SIM slot
- Network mode
- Network search
- APN profile
- PDP type
- WiFi 2.4G mode
- WiFi 2.4G channel width
- WiFi 2.4G channel
- WiFi 2.4G transmit power
- WiFi 5G mode
- WiFi 5G channel width
- WiFi 5G channel
- WiFi 5G transmit power
- VPN protocol
- VPN default rule
- VPN client access
- VPN policy
- Auto update time

That means settings such as the main router SIM slot can be changed directly from Home Assistant, for example switching between `Sim 1` and `Sim 2`.

## Buttons

### Main Router

- Reboot

### Mesh Nodes

- Reboot

## Device Trackers

The integration supports `device_tracker` entities for manually selected clients.

Important behavior:

- `device_tracker` entities are opt-in
- they are created from **Manually Add Connected Devices**
- they are only created when **Automatically Add Connected Devices** is turned off
- manual matching supports MAC addresses and hostnames

## Integration Options

### Automatically Add Connected Devices

When enabled, the integration creates client devices and live per-client entities for every currently connected device reported by the router.

Use this if you want Home Assistant to mirror the router's live client list automatically.

### Manually Add Connected Devices

This is a comma-separated list of MAC addresses or hostnames.

Use this when you only care about a small number of specific clients and do not want every connected device added to Home Assistant.

When **Automatically Add Connected Devices** is turned off:

- client entities are only created for matching devices in this list
- `device_tracker` entities are created for matching devices in this list
- stale auto-added client entities are removed

### Update Interval

Controls how often the router is polled for new data.

## Services

The integration also registers Home Assistant services.

### `cudy_router.reboot_router`

Reboots the router.

Optional fields:

- `entry_id`

### `cudy_router.restart_5g_connection`

Restarts the router's cellular connection.

Optional fields:

- `entry_id`

### `cudy_router.switch_5g_band`

Changes the modem band preference.

Fields:

- `band`
- `entry_id` optional

### `cudy_router.send_sms`

Sends an SMS through the router's modem.

Fields:

- `phone_number`
- `message`
- `entry_id` optional

### `cudy_router.send_at_command`

Sends a raw AT command to the modem and logs the result.

Fields:

- `command`
- `entry_id` optional

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

## What the Integration Reads

Depending on the detected router model and available pages, the integration reads and parses data from areas such as:

- modem / cellular status
- connected device lists
- system status
- data-usage pages
- SMS status
- Wi-Fi status
- LAN status
- VPN status
- DHCP status
- WAN status
- cellular configuration
- wireless configuration
- VPN configuration
- auto-update configuration
- mesh status

## Current Behavior Around Client Devices

Client device creation is intentionally separate from router-level summary sensors.

- summary sensors such as total clients and top uploader/downloader remain on the main router device
- per-client IP, signal, online time, internet access, and DNS filter entities live on client devices
- mesh node entities live on mesh devices
- router settings stay on the main router device

This keeps the Home Assistant device pages cleaner and reduces mixing router controls with client entities.

## Limitations and Notes

- Feature coverage varies by router model and firmware.
- Some mesh values may be unavailable or reported as unknown if the router firmware does not expose them.
- Service calls such as band switching and raw AT commands are advanced operations and should be used carefully.
- The integration polls the router web UI. If the router is busy, rebooting, unreachable, or returns a different page layout, entities may be temporarily unavailable.
- If the router password changes, reauthentication is handled through the config entry.

## Troubleshooting

### Entities Missing

Check:

- the router model actually exposes the relevant page or control
- the integration options for automatic or manual client creation
- that Home Assistant has been restarted after updating the custom component

### Too Many Client Devices

Turn off **Automatically Add Connected Devices** and use **Manually Add Connected Devices** instead.

### Client Device Did Not Match

The manual list accepts:

- MAC addresses
- hostnames

Use the same value style the router reports in its connected-device table.

### Router Cannot Connect

Check:

- router IP address
- username and password
- that Home Assistant can reach the router over the local network

## Contributing

Issues and pull requests are welcome.

When changing behavior, update the tests and keep the README in sync with the actual entity surface, options flow, and service list.
