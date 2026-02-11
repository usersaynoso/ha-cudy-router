# Cudy Router — Home Assistant Integration

This repository provides a Home Assistant integration for Cudy routers (including some 5G models).

Installation (HACS)

1. Open HACS in Home Assistant and choose "Integrations" → "Explore & Add Repositories".
2. Add this repository: `https://github.com/usersaynoso/ha-cudy-router`.
3. Install the integration and restart Home Assistant.

Manual installation

1. Copy the `custom_components/cudy_router` directory into your Home Assistant `config` directory.
2. Restart Home Assistant.

Configuration

- Add the integration via Settings → Devices & Services → Add Integration → "Cudy Router".
- Provide your router host (e.g. `https://192.168.10.1`), username and password.

Notes

- This integration requires access to the router's web interface (Remote Management or local LAN access).
- For HACS listing metadata is provided in `hacs.json`.
# Home Assistant Integration for Cudy Routers

This repository contains a **community-built** Home Assistant integration for Cudy routers.

Community-built means it is **not endorsed, maintained, or supported by Cudy**.  
If something breaks or behaves oddly, please report issues here rather than contacting Cudy support.

---

## Supported Routers

- **Cudy P5** (5G Router) - Fully tested
- Other Cudy routers with LuCI web interface should work (feedback welcome)

---

## Features

The integration authenticates against the router's **web-based admin interface** and extracts data by parsing the rendered pages.

### Sensors

#### Modem / Cellular Connection
| Sensor | Description |
|--------|-------------|
| Network Type | Current network (e.g., "EE 5G-SA", "LTE") |
| Signal Strength | Signal quality (1-4 bars) |
| RSRP | Reference Signal Received Power (dBm) |
| RSRQ | Reference Signal Received Quality (dB) |
| SINR | Signal to Interference & Noise Ratio (dB) |
| RSSI | Received Signal Strength Indicator (dBm) |
| Band | Current band(s) in use (e.g., "B78+B3") |
| Cell ID | Cell tower ID with eNB/sector attributes |
| SIM Slot | Active SIM slot (Sim 1 / Sim 2) |
| Connected Time | Duration of current connection |
| Public IP | Public IP address (carrier-assigned) |
| WAN IP | WAN IP address (may be CGNAT address) |
| IMEI | Device IMEI number |
| IMSI | SIM IMSI number |
| ICCID | SIM card ICCID |
| Mode | Connection mode (TDD/FDD) |
| Bandwidth | Download bandwidth (e.g., "40MHz") |
| Session Upload | Data uploaded this session (MB) |
| Session Download | Data downloaded this session (MB) |

#### Data Usage
| Sensor | Description |
|--------|-------------|
| Current Session Traffic | Traffic for current connection (MB) |
| Monthly Traffic | Traffic this month (MB) |
| Total Traffic | Total traffic since counter reset (MB) |

#### System
| Sensor | Description |
|--------|-------------|
| Uptime | Router uptime (seconds) |
| Local Time | Router's local time |
| Firmware Version | Installed firmware version |

#### SMS
| Sensor | Description |
|--------|-------------|
| SMS Inbox | Number of messages in inbox |
| SMS Outbox | Number of sent messages |
| SMS Unread | Number of unread messages |

#### WiFi 2.4G & 5G
| Sensor | Description |
|--------|-------------|
| SSID | WiFi network name |
| Channel | WiFi channel |

#### LAN
| Sensor | Description |
|--------|-------------|
| LAN IP | Router's LAN IP address |
| LAN MAC | Router's MAC address |

#### Connected Devices
| Sensor | Description |
|--------|-------------|
| Device Count | Total connected devices |
| WiFi 2.4G Clients | Devices on 2.4G band |
| WiFi 5G Clients | Devices on 5G band |
| Total Clients | Total client count |
| Top Downloader | Device with highest download speed |
| Top Uploader | Device with highest upload speed |
| Total Download/Upload Speed | Aggregate bandwidth usage |

#### Mesh Network (v1.1.0+)
| Sensor | Description |
|--------|-------------|
| Mesh Devices | Number of mesh nodes connected |
| Mesh Device Name | Name of each mesh node |
| Mesh Device Model | Model of each mesh node |
| Mesh Device MAC | MAC address of each mesh node |
| Mesh Device Firmware | Firmware version of each mesh node |
| Mesh Device Status | Online/offline status of each node |
| Mesh Device IP | IP address of each mesh node |

### Switches

#### Mesh LED Control (v1.1.0+)
Each mesh device gets a LED switch entity to turn the device LEDs on or off.

### Buttons

#### Router Reboot (v1.1.0+)
A button entity to reboot the main router.

#### Mesh Device Reboot (v1.1.0+)
Each mesh device gets a reboot button to restart that specific node.

### Services

#### `cudy_router.reboot_router`
Reboot the router.

#### `cudy_router.restart_5g_connection`
Restart the 5G/LTE modem connection (modem reset). Useful for reconnecting to get a new IP or fix connectivity issues.

#### `cudy_router.switch_5g_band`
Switch the modem band preference.
- **band** (required): Band value (e.g., "auto", "5g-only", "lte-only")

#### `cudy_router.send_sms`
Send an SMS via the router's modem.
- **phone_number** (required): Destination number with country code (e.g., "+441234567890")
- **message** (required): SMS text content

#### `cudy_router.send_at_command`
Send an AT command directly to the modem (advanced users).
- **command** (required): AT command to execute (e.g., "AT+CSQ")

---

## Installation

1. Create a `cudy_router` folder in `config/custom_components/`
2. Copy all files from this repository into that folder
3. Restart Home Assistant
4. Go to **Configuration → Integrations → Add Integration**
5. Search for "Cudy Router"
6. Enter your router's details:
   - **Host**: Use the local LAN IP with https:// (e.g., `https://192.168.10.1`)
   - **Username**: Usually `admin`
   - **Password**: Your router admin password

⚠️ The directory name **must** be exactly `cudy_router` or Home Assistant will fail to load the integration.

### Important Notes

- **Always use HTTPS** - The router requires HTTPS connections
- **Use Local LAN IP** - Don't use a remote/WAN IP as it may change (CGNAT)
- The integration will accept self-signed certificates

---

## Configuration Options

After setup, you can configure:
- **Device List**: Comma-separated list of MAC addresses or hostnames to track individually

---

## Development & Contributions

Testing has been performed against:
- Cudy P5 (5G router)

Compatibility with other models is not guaranteed. Contributions, bug reports, and feedback are welcome.

For major changes, please open an issue first to discuss.

Code formatting follows **Home Assistant Core** style guidelines.

### Dev Quickstart

1. Create a virtual environment and activate it.
2. Install dependencies:
   - `python -m pip install -r requirements.txt`
   - `python -m pip install pytest mypy`
3. Run formatter/fixes:
   - `./scripts/format`
4. Run tests:
   - `./scripts/test`
5. Optional focused typecheck:
   - `python -m mypy custom_components/cudy_router/router_data.py custom_components/cudy_router/parser_network.py custom_components/cudy_router/sensor_descriptions.py`

---

## License

Released under the [GNU General Public License v3.0](https://www.gnu.org/licenses/gpl-3.0.en.html)
