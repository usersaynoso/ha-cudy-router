"""Provides the backend for a Cudy router."""

from __future__ import annotations

import hashlib
from http.cookies import SimpleCookie
import logging
import re
import time
from typing import Any
import urllib.parse

import requests
import urllib3

from homeassistant.core import HomeAssistant

from .const import (
    MODULE_DATA_USAGE,
    MODULE_DEVICES,
    MODULE_LAN,
    MODULE_MESH,
    MODULE_MODEM,
    MODULE_SMS,
    MODULE_SYSTEM,
    MODULE_WIFI_2G,
    MODULE_WIFI_5G,
    OPTIONS_DEVICELIST,
)
from .parser import (
    parse_data_usage,
    parse_devices,
    parse_devices_status,
    parse_lan_status,
    parse_mesh_devices,
    parse_modem_info,
    parse_sms_status,
    parse_system_status,
    parse_wifi_status,
)

_LOGGER = logging.getLogger(__name__)


def _sha256_hex(s: str) -> str:
    """Compute SHA256 hash and return as hex string."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _extract_hidden(html: str, name: str) -> str:
    """Extract value from hidden input field."""
    match = re.search(r'name="%s"[^>]*value="([^"]*)"' % re.escape(name), html)
    return match.group(1) if match else ""


def _compute_luci_password(plain_password: str, salt: str, token: str) -> str:
    """Compute the LuCI password hash.

    h1 = sha256(password + salt)
    luci_password = sha256(h1 + token)
    """
    h1 = _sha256_hex(plain_password + salt)
    return _sha256_hex(h1 + token) if token else h1


class CudyRouter:
    """Represents a router and provides functions for communication."""

    def __init__(
        self, hass: HomeAssistant, host: str, username: str, password: str
    ) -> None:
        """Initialize the router."""
        self.host = host
        self.auth_cookie: str | None = None
        self.hass = hass
        self.username = username
        self.password = password
        self._session: requests.Session | None = None
        # Determine base URL - always use https if no scheme provided
        if host.startswith("https://"):
            self.base_url = host.rstrip("/")
        elif host.startswith("http://"):
            # Allow http but prefer https
            self.base_url = host.rstrip("/")
        else:
            # Default to https for security
            self.base_url = f"https://{host}"

    def _get_session(self) -> requests.Session:
        """Get or create a requests session with SSL verification disabled."""
        if self._session is None:
            self._session = requests.Session()
            self._session.verify = False
            # Suppress SSL warnings for self-signed certs
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        return self._session

    def get_cookie_header(self, force_auth: bool) -> str:
        """Returns a cookie header that should be used for authentication."""

        if not force_auth and self.auth_cookie:
            return f"sysauth={self.auth_cookie}"
        if self.authenticate():
            return f"sysauth={self.auth_cookie}"
        else:
            return ""

    def _authenticate_legacy(self) -> bool:
        """Legacy authentication method (plain password)."""
        data_url = f"{self.base_url}/cgi-bin/luci"
        headers = {"Content-Type": "application/x-www-form-urlencoded", "Cookie": ""}
        body = f"luci_username={urllib.parse.quote(self.username)}&luci_password={urllib.parse.quote(self.password)}&luci_language=en"

        try:
            session = self._get_session()
            response = session.post(
                data_url, timeout=30, headers=headers, data=body, allow_redirects=False
            )
            if response.ok or response.status_code == 302:
                set_cookie = response.headers.get("set-cookie", "")
                if set_cookie:
                    cookie = SimpleCookie()
                    cookie.load(set_cookie)
                    if cookie.get("sysauth"):
                        self.auth_cookie = cookie.get("sysauth").value
                        return True
        except requests.exceptions.ConnectionError:
            _LOGGER.debug("Connection error during legacy auth")
        except Exception as e:
            _LOGGER.debug("Legacy auth error: %s", e)
        return False

    def _authenticate_new(self) -> bool:
        """New authentication method with salt/token and SHA256 hashing (for 5G routers like P5)."""
        session = self._get_session()
        login_url = f"{self.base_url}/cgi-bin/luci/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": f"{self.base_url}/",
        }

        try:
            # GET login page to extract salt and token (may return 403 but still has HTML)
            response = session.get(login_url, timeout=15, headers=headers)
            html = response.text

            csrf = _extract_hidden(html, "_csrf")
            token = _extract_hidden(html, "token")
            salt = _extract_hidden(html, "salt")

            _LOGGER.debug("Login page HTTP: %s, csrf: %s, token: %s, salt: %s",
                         response.status_code, bool(csrf), bool(token), bool(salt))

            if not (salt and token):
                _LOGGER.debug("Could not extract salt/token from login page")
                return False

            # Compute hashed password
            luci_password = _compute_luci_password(self.password, salt, token)

            # POST login
            post_data = {
                "_csrf": csrf,
                "token": token,
                "salt": salt,
                "luci_username": self.username,
                "luci_password": luci_password,
                "zonename": "UTC",
                "timeclock": "0",
            }
            post_headers = {
                **headers,
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": self.base_url,
            }

            response = session.post(
                login_url, timeout=15, headers=post_headers,
                data=urllib.parse.urlencode(post_data), allow_redirects=False
            )

            # Check for sysauth cookie
            for cookie in session.cookies:
                if cookie.name == "sysauth":
                    self.auth_cookie = cookie.value
                    _LOGGER.debug("New auth successful, got sysauth cookie")
                    return True

            _LOGGER.debug("New auth: no sysauth cookie received, status=%s", response.status_code)
            return False

        except requests.exceptions.ConnectionError as e:
            _LOGGER.debug("Connection error during new auth: %s", e)
        except requests.exceptions.Timeout as e:
            _LOGGER.debug("Timeout during new auth: %s", e)
        except Exception as e:
            _LOGGER.warning("New auth error: %s", e, exc_info=True)
        return False

    def authenticate(self) -> bool:
        """Test if we can authenticate with the host. Tries new method first, then legacy."""
        # Clear any existing session cookies
        if self._session:
            self._session.cookies.clear()
        self.auth_cookie = None

        # Try new authentication method first (for 5G routers like Cudy P5)
        if self._authenticate_new():
            return True

        # Retry new auth after short delay (token rotation / session weirdness)
        time.sleep(0.4)
        if self._authenticate_new():
            return True

        # Fall back to legacy authentication
        _LOGGER.debug("New auth failed, trying legacy auth")
        return self._authenticate_legacy()

    def get(self, url: str, silent: bool = False) -> str:
        """Retrieves data from the given URL using an authenticated session.
        
        Args:
            url: The URL path to fetch (relative to /cgi-bin/luci/)
            silent: If True, don't log errors for failed requests (for optional endpoints)
        """

        retries = 2
        while retries > 0:
            retries -= 1

            data_url = f"{self.base_url}/cgi-bin/luci/{url}"
            session = self._get_session()
            
            # Set the auth cookie in session if available
            if self.auth_cookie:
                session.cookies.set("sysauth", self.auth_cookie)

            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": f"{self.base_url}/cgi-bin/luci/admin",
            }

            try:
                response = session.get(
                    data_url, timeout=30, headers=headers, allow_redirects=False
                )
                if response.status_code == 403:
                    if self.authenticate():
                        continue
                    else:
                        if not silent:
                            _LOGGER.error("Error during authentication to %s", url)
                        break
                if response.ok:
                    return response.text
                else:
                    break
            except Exception:  # pylint: disable=broad-except
                _LOGGER.debug("Exception during GET %s", url)
                pass

        if not silent:
            _LOGGER.debug("Failed to retrieve data from %s", url)
        return ""

    def _post_action_on_page(
        self, page: str, button_text_substring: str, extra_fields: dict[str, str] | None = None
    ) -> tuple[int, str]:
        """Fetch a page, find a button by text/value substring and POST the action.

        Returns (status_code, head_of_response).
        """
        session = self._get_session()
        page_url = f"{self.base_url}/cgi-bin/luci/{page}"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": f"{self.base_url}/cgi-bin/luci/admin",
        }

        code = 0
        try:
            resp = session.get(page_url, timeout=15, headers=headers)
            html = resp.text
            code = resp.status_code

            token = _extract_hidden(html, "token")
            if not token:
                raise RuntimeError("No token on page %s (HTTP %s)" % (page, code))

            # Find a button/input with a name/value we can submit
            # Try <button ... name="..." value="...">text</button>
            m = re.search(r'<button[^>]*name="([^\"]+)"[^>]*value="([^\"]*)"[^>]*>([^<]*)</button>', html)
            name = None
            value = None
            if m:
                # if the button text or value matches substring, use it
                if button_text_substring.lower() in (m.group(2) or "").lower() or button_text_substring.lower() in (m.group(3) or "").lower():
                    name, value = m.group(1), m.group(2)

            # Fallback: look for input type=submit
            if not name:
                m2 = re.search(r'<input[^>]*type="submit"[^>]*name="([^\"]+)"[^>]*value="([^\"]*)"', html)
                if m2 and button_text_substring.lower() in (m2.group(2) or "").lower():
                    name, value = m2.group(1), m2.group(2)

            if not name:
                raise RuntimeError("Could not find action button containing '%s' on %s" % (button_text_substring, page))

            post_fields = {"token": token, "timeclock": "0", "cbi.submit": "1", name: value}
            if extra_fields:
                post_fields.update(extra_fields)

            r = session.post(page_url, timeout=30, headers={**headers, "Content-Type": "application/x-www-form-urlencoded", "Origin": self.base_url}, data=urllib.parse.urlencode(post_fields), allow_redirects=False)
            return r.status_code, r.text[:220]
        except Exception as e:
            _LOGGER.error("Action on %s failed: %s", page, e)
            return code or 0, str(e)[:220]

    def reboot_router(self) -> tuple[int, str]:
        """Trigger router reboot via LuCI web UI."""
        # The Cudy router reboot page is at /admin/system/reboot/reboot
        # It has a simple form with token and a cbi.apply button
        session = self._get_session()
        page_url = f"{self.base_url}/cgi-bin/luci/admin/system/reboot/reboot"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": f"{self.base_url}/cgi-bin/luci/admin/panel",
        }

        try:
            resp = session.get(page_url, timeout=15, headers=headers)
            html = resp.text
            token = _extract_hidden(html, "token")
            if not token:
                return 0, "No token on reboot page"

            post_fields = {
                "token": token,
                "timeclock": "0",
                "cbi.submit": "1",
                "cbi.apply": "OK",
            }
            r = session.post(
                page_url, timeout=30,
                headers={**headers, "Content-Type": "application/x-www-form-urlencoded", "Origin": self.base_url},
                data=urllib.parse.urlencode(post_fields), allow_redirects=False
            )
            return r.status_code, r.text[:220]
        except Exception as e:
            _LOGGER.error("Reboot failed: %s", e)
            return 0, str(e)[:220]

    def restart_5g_connection(self) -> tuple[int, str]:
        """Restart the 5G modem connection by triggering Modem Reset.

        Note: On Cudy P5, this is a modem factory reset which restarts the
        cellular connection.
        """
        # The reset page is at /admin/network/gcom/reset
        # Button name="cbid.reset.1.reset" value="Modem Reset"
        session = self._get_session()
        page_url = f"{self.base_url}/cgi-bin/luci/admin/network/gcom/reset"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": f"{self.base_url}/cgi-bin/luci/admin/network/gcom/status",
        }

        try:
            resp = session.get(page_url, timeout=15, headers=headers)
            html = resp.text
            token = _extract_hidden(html, "token")
            if not token:
                return 0, "No token on reset page"

            post_fields = {
                "token": token,
                "timeclock": "0",
                "cbi.submit": "1",
                "cbid.reset.1.reset": "Modem Reset",
            }
            r = session.post(
                page_url, timeout=30,
                headers={**headers, "Content-Type": "application/x-www-form-urlencoded", "Origin": self.base_url},
                data=urllib.parse.urlencode(post_fields), allow_redirects=False
            )
            return r.status_code, r.text[:220]
        except Exception as e:
            _LOGGER.error("Restart 5G failed: %s", e)
            return 0, str(e)[:220]

    def switch_5g_band(self, band_value: str) -> tuple[int, str]:
        """Attempt to set the 5G band by finding a select element on the settings page.

        The method looks for a select whose name contains 'band' and submits
        the chosen value.
        """
        session = self._get_session()
        page = "admin/network/gcom/setting"
        page_url = f"{self.base_url}/cgi-bin/luci/{page}"
        headers = {"User-Agent": "Mozilla/5.0", "Referer": f"{self.base_url}/cgi-bin/luci/admin"}

        try:
            resp = session.get(page_url, timeout=15, headers=headers)
            html = resp.text
            token = _extract_hidden(html, "token")
            if not token:
                return 0, "No token on page"

            # Find select name attribute containing 'band'
            m = re.search(r'<select[^>]*name="([^"]*band[^"]*)"', html, flags=re.IGNORECASE)
            if not m:
                return 0, "No band select found"

            select_name = m.group(1)
            post_fields = {"token": token, "timeclock": "0", "cbi.submit": "1", select_name: band_value}
            r = session.post(page_url, timeout=30, headers={**headers, "Content-Type": "application/x-www-form-urlencoded", "Origin": self.base_url}, data=urllib.parse.urlencode(post_fields), allow_redirects=False)
            return r.status_code, r.text[:220]
        except Exception as e:
            _LOGGER.error("Switch band failed: %s", e)
            return 0, str(e)[:220]

    def send_sms(self, phone_number: str, message: str) -> tuple[int, str]:
        """Send an SMS via the router's LuCI web interface.

        Args:
            phone_number: The destination phone number (e.g. +441234567890)
            message: The SMS text content (max ~70 chars for single SMS)

        Returns:
            Tuple of (HTTP status code, response snippet or error message)
        """
        session = self._get_session()
        page = "admin/network/gcom/sms/smsnew"
        page_url = f"{self.base_url}/cgi-bin/luci/{page}?nomodal=&iface=4g"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": f"{self.base_url}/cgi-bin/luci/admin/network/gcom/sms",
        }

        try:
            # GET the form page to obtain token
            resp = session.get(page_url, timeout=15, headers=headers)
            html = resp.text
            token = _extract_hidden(html, "token")
            if not token:
                _LOGGER.error("SMS send: no token found on smsnew page")
                return 0, "No token on SMS page"

            # POST the SMS
            # Form fields from router:
            #   name="cbid.smsnew.1.phone"   -> phone number
            #   name="cbid.smsnew.1.content" -> message text
            #   name="cbid.smsnew.1.send"    -> submit button value="Send"
            post_fields = {
                "token": token,
                "timeclock": "0",
                "cbi.submit": "1",
                "cbid.smsnew.1.phone": phone_number,
                "cbid.smsnew.1.content": message,
                "cbid.smsnew.1.send": "Send",
            }
            r = session.post(
                page_url,
                timeout=30,
                headers={
                    **headers,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": self.base_url,
                },
                data=urllib.parse.urlencode(post_fields),
                allow_redirects=False,
            )
            _LOGGER.debug("SMS send response: %s", r.status_code)
            return r.status_code, r.text[:220]
        except Exception as e:
            _LOGGER.error("SMS send failed: %s", e)
            return 0, str(e)[:220]

    def send_at_command(self, command: str) -> tuple[int, str]:
        """Send an AT command to the modem via the router's LuCI web interface.

        Args:
            command: The AT command to execute (e.g. 'AT+CSQ')

        Returns:
            Tuple of (HTTP status code, response text or error message)
        """
        session = self._get_session()
        page = "admin/network/gcom/atcmd"
        page_url = f"{self.base_url}/cgi-bin/luci/{page}?embedded=&iface=4g"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": f"{self.base_url}/cgi-bin/luci/admin/network/gcom/config",
        }

        try:
            # GET the form page to obtain token
            resp = session.get(page_url, timeout=15, headers=headers)
            html = resp.text
            token = _extract_hidden(html, "token")
            if not token:
                _LOGGER.error("AT command: no token found on atcmd page")
                return 0, "No token on AT command page"

            # POST the AT command
            post_fields = {
                "token": token,
                "timeclock": "0",
                "cbi.submit": "1",
                "cbid.atcmd.1.command": command,
                "cbid.atcmd.1.refresh": "AT Command",
            }
            r = session.post(
                page_url,
                timeout=30,
                headers={
                    **headers,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": self.base_url,
                },
                data=urllib.parse.urlencode(post_fields),
                allow_redirects=False,
            )
            
            # Extract the response from textarea
            response_html = r.text
            textarea_match = re.search(r'<textarea[^>]*id="cbid\.atcmd\.1\._custom"[^>]*>([^<]*)</textarea>', response_html)
            if textarea_match:
                at_response = textarea_match.group(1).strip()
                return r.status_code, at_response
            
            _LOGGER.debug("AT command response: %s", r.status_code)
            return r.status_code, r.text[:500]
        except Exception as e:
            _LOGGER.error("AT command failed: %s", e)
            return 0, str(e)[:220]

    async def get_data(
        self, hass: HomeAssistant, options: dict[str, Any]
    ) -> dict[str, Any]:
        """Retrieves data from the router"""

        data: dict[str, Any] = {}

        # Modem status (5G/LTE info)
        data[MODULE_MODEM] = parse_modem_info(
            f"{await hass.async_add_executor_job(self.get, 'admin/network/gcom/status')}{await hass.async_add_executor_job(self.get, 'admin/network/gcom/status?detail=1&iface=4g')}"
        )
        
        # Connected devices
        data[MODULE_DEVICES] = parse_devices(
            await hass.async_add_executor_job(
                self.get, "admin/network/devices/devlist?detail=1"
            ),
            options and options.get(OPTIONS_DEVICELIST),
        )
        
        # Add device client counts to the devices module
        # Try multiple possible endpoints for device status
        devices_status_html = await hass.async_add_executor_job(
            self.get, "admin/network/devices/status"
        )
        # Also try the main panel which sometimes has client counts
        if not devices_status_html or "client" not in devices_status_html.lower():
            panel_html = await hass.async_add_executor_job(
                self.get, "admin/panel"
            )
            devices_status_html = f"{devices_status_html}{panel_html}"
        
        devices_status = parse_devices_status(devices_status_html)
        data[MODULE_DEVICES].update(devices_status)
        
        # System status (uptime, firmware, local time)
        # Fetch from multiple endpoints to increase chances of finding firmware
        system_html = await hass.async_add_executor_job(
            self.get, "admin/system/status"
        )
        # Also try the main panel which often has firmware info
        panel_html = await hass.async_add_executor_job(
            self.get, "admin/panel"
        )
        # Try overview page which sometimes has firmware (silently)
        overview_html = await hass.async_add_executor_job(
            self.get, "admin/status/overview", True  # silent
        )
        # Try system page which sometimes has firmware (silently)
        system_page_html = await hass.async_add_executor_job(
            self.get, "admin/system/system", True  # silent
        )
        data[MODULE_SYSTEM] = parse_system_status(
            f"{system_html}{panel_html}{overview_html or ''}{system_page_html or ''}"
        )
        
        # Data usage statistics
        data[MODULE_DATA_USAGE] = parse_data_usage(
            await hass.async_add_executor_job(self.get, "admin/network/gcom/statistics?iface=4g")
        )
        
        # SMS status
        data[MODULE_SMS] = parse_sms_status(
            await hass.async_add_executor_job(self.get, "admin/network/gcom/sms/status")
        )
        
        # WiFi 2.4G status
        data[MODULE_WIFI_2G] = parse_wifi_status(
            await hass.async_add_executor_job(self.get, "admin/network/wireless/status?iface=wlan00")
        )
        
        # WiFi 5G status
        data[MODULE_WIFI_5G] = parse_wifi_status(
            await hass.async_add_executor_job(self.get, "admin/network/wireless/status?iface=wlan10")
        )
        
        # LAN status
        data[MODULE_LAN] = parse_lan_status(
            await hass.async_add_executor_job(self.get, "admin/network/lan/status")
        )
        
        # Mesh devices - try multiple possible endpoints (silent since mesh is optional)
        mesh_html = ""
        mesh_endpoints = [
            "admin/network/mesh/status",
            "admin/network/mesh",
            "admin/network/mesh/topology",
            "admin/network/mesh/nodes",
            "admin/easymesh/status",
            "admin/easymesh",
        ]
        for endpoint in mesh_endpoints:
            result = await hass.async_add_executor_job(
                self.get, endpoint, True  # silent=True
            )
            if result and ("mesh" in result.lower() or "node" in result.lower() or "satellite" in result.lower()):
                mesh_html += result  # Combine results from multiple endpoints
                _LOGGER.debug("Found mesh data at endpoint: %s (length: %d)", endpoint, len(result))
        
        data[MODULE_MESH] = parse_mesh_devices(mesh_html)

        return data

    def reboot_mesh_device(self, mac_address: str) -> tuple[int, str]:
        """Reboot a specific mesh device by MAC address.

        Args:
            mac_address: The MAC address of the mesh device to reboot

        Returns:
            Tuple of (HTTP status code, response snippet or error message)
        """
        session = self._get_session()
        # Try multiple possible mesh management endpoints
        endpoints = [
            "admin/network/mesh/node",
            "admin/network/mesh/reboot",
            "admin/network/mesh/manage",
        ]
        
        for endpoint in endpoints:
            page_url = f"{self.base_url}/cgi-bin/luci/{endpoint}"
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Referer": f"{self.base_url}/cgi-bin/luci/admin/network/mesh",
            }

            try:
                resp = session.get(page_url, timeout=15, headers=headers)
                if resp.status_code == 404:
                    continue
                    
                html = resp.text
                token = _extract_hidden(html, "token")
                if not token:
                    continue

                # Try different POST field patterns for mesh reboot
                post_patterns = [
                    {"token": token, "timeclock": "0", "cbi.submit": "1", 
                     "mac": mac_address, "action": "reboot"},
                    {"token": token, "timeclock": "0", "cbi.submit": "1",
                     "cbid.mesh.1.mac": mac_address, "cbid.mesh.1.reboot": "Reboot"},
                    {"token": token, "timeclock": "0", "cbi.submit": "1",
                     "node_mac": mac_address, "reboot": "1"},
                ]
                
                for post_fields in post_patterns:
                    r = session.post(
                        page_url,
                        timeout=30,
                        headers={
                            **headers,
                            "Content-Type": "application/x-www-form-urlencoded",
                            "Origin": self.base_url,
                        },
                        data=urllib.parse.urlencode(post_fields),
                        allow_redirects=False,
                    )
                    if r.status_code in (200, 302):
                        _LOGGER.debug("Mesh reboot for %s successful via %s", mac_address, endpoint)
                        return r.status_code, f"Reboot initiated for {mac_address}"
                        
            except Exception as e:
                _LOGGER.debug("Mesh reboot attempt on %s failed: %s", endpoint, e)
                continue
        
        _LOGGER.error("Failed to reboot mesh device %s - no working endpoint found", mac_address)
        return 0, f"Failed to reboot mesh device {mac_address}"

    def set_mesh_led(self, mac_address: str, enabled: bool) -> tuple[int, str]:
        """Set LED state for a specific mesh device.

        Args:
            mac_address: The MAC address of the mesh device
            enabled: True to turn LEDs on, False to turn off

        Returns:
            Tuple of (HTTP status code, response snippet or error message)
        """
        session = self._get_session()
        # Try multiple possible LED control endpoints
        endpoints = [
            "admin/network/mesh/led",
            "admin/network/mesh/settings",
            "admin/system/led",
        ]
        
        for endpoint in endpoints:
            page_url = f"{self.base_url}/cgi-bin/luci/{endpoint}"
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Referer": f"{self.base_url}/cgi-bin/luci/admin/network/mesh",
            }

            try:
                resp = session.get(page_url, timeout=15, headers=headers)
                if resp.status_code == 404:
                    continue
                    
                html = resp.text
                token = _extract_hidden(html, "token")
                if not token:
                    continue

                led_value = "1" if enabled else "0"
                # Try different POST field patterns for LED control
                post_patterns = [
                    {"token": token, "timeclock": "0", "cbi.submit": "1",
                     "mac": mac_address, "led": led_value},
                    {"token": token, "timeclock": "0", "cbi.submit": "1",
                     "cbid.led.1.enable": led_value, "node_mac": mac_address},
                    {"token": token, "timeclock": "0", "cbi.submit": "1",
                     "led_enable": led_value, "mac_address": mac_address},
                    # Global LED control (no MAC needed)
                    {"token": token, "timeclock": "0", "cbi.submit": "1",
                     "cbid.system.led.trigger": "none" if not enabled else "default-on"},
                ]
                
                for post_fields in post_patterns:
                    r = session.post(
                        page_url,
                        timeout=30,
                        headers={
                            **headers,
                            "Content-Type": "application/x-www-form-urlencoded",
                            "Origin": self.base_url,
                        },
                        data=urllib.parse.urlencode(post_fields),
                        allow_redirects=False,
                    )
                    if r.status_code in (200, 302):
                        _LOGGER.debug("Mesh LED %s for %s successful via %s", 
                                     "on" if enabled else "off", mac_address, endpoint)
                        return r.status_code, f"LED {'on' if enabled else 'off'} for {mac_address}"
                        
            except Exception as e:
                _LOGGER.debug("Mesh LED control attempt on %s failed: %s", endpoint, e)
                continue
        
        _LOGGER.error("Failed to set mesh LED for %s - no working endpoint found", mac_address)
        return 0, f"Failed to set LED for mesh device {mac_address}"

    def get_mesh_led_state(self, mac_address: str) -> bool | None:
        """Get current LED state for a mesh device.

        Args:
            mac_address: The MAC address of the mesh device

        Returns:
            True if LEDs are on, False if off, None if unknown
        """
        session = self._get_session()
        endpoints = [
            "admin/network/mesh/led",
            "admin/network/mesh/settings",
            "admin/network/mesh/status",
        ]
        
        for endpoint in endpoints:
            page_url = f"{self.base_url}/cgi-bin/luci/{endpoint}"
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Referer": f"{self.base_url}/cgi-bin/luci/admin/network/mesh",
            }

            try:
                resp = session.get(page_url, timeout=15, headers=headers)
                if resp.status_code == 404:
                    continue
                    
                html = resp.text
                
                # Look for LED state indicators in HTML
                # Check for checked checkbox or selected option
                if mac_address.lower() in html.lower() or "led" in html.lower():
                    # Check various patterns for LED on state
                    if re.search(r'led["\s]*[:=]\s*["\']?(?:on|1|true|enabled)', html, re.IGNORECASE):
                        return True
                    if re.search(r'led["\s]*[:=]\s*["\']?(?:off|0|false|disabled)', html, re.IGNORECASE):
                        return False
                    # Check for checked checkbox
                    if re.search(r'name="[^"]*led[^"]*"[^>]*checked', html, re.IGNORECASE):
                        return True
                    if re.search(r'name="[^"]*led[^"]*"[^>]*(?!checked)', html, re.IGNORECASE):
                        return False
                        
            except Exception as e:
                _LOGGER.debug("Get mesh LED state on %s failed: %s", endpoint, e)
                continue
        
        # Default to True (LEDs on) if we can't determine state
        return True
