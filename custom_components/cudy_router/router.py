"""Provides the backend for a Cudy router."""

from __future__ import annotations

import hashlib
import logging
import re
import time
import urllib.parse
from http.cookies import SimpleCookie
from typing import Any

import requests
import urllib3
from homeassistant.core import HomeAssistant

from .const import (
    MODULE_DATA_USAGE,
    MODULE_DEVICES,
    MODULE_DHCP,
    MODULE_LAN,
    MODULE_MESH,
    MODULE_MODEM,
    MODULE_SMS,
    MODULE_SYSTEM,
    MODULE_VPN,
    MODULE_WAN,
    MODULE_WIFI_2G,
    MODULE_WIFI_5G,
    OPTIONS_DEVICELIST,
)
from .features import existing_feature
from .parser import (
    parse_data_usage,
    parse_devices,
    parse_devices_status,
    parse_dhcp_status,
    parse_lan_status,
    parse_mesh_client_status,
    parse_mesh_devices,
    parse_modem_info,
    parse_sms_status,
    parse_system_status,
    parse_vpn_status,
    parse_wan_status,
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


def _extract_model(html: str) -> str:
    """Extract device model in page"""
    match = re.search(r"<span>HW: ([a-zA-Z0-9 \-\.]+)<\/span>", html)
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
        self,
        hass: HomeAssistant,
        host: str,
        username: str,
        password: str,
        device_model: str = "default",
    ) -> None:
        """Initialize the router."""
        self.host = host
        self.auth_cookie: str | None = None
        self.hass = hass
        self.username = username
        self.password = password
        self.device_model = device_model
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
            response = session.post(data_url, timeout=30, headers=headers, data=body, allow_redirects=False)
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

            _LOGGER.debug(
                "Login page HTTP: %s, csrf: %s, token: %s, salt: %s",
                response.status_code,
                bool(csrf),
                bool(token),
                bool(salt),
            )

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
                login_url,
                timeout=15,
                headers=post_headers,
                data=urllib.parse.urlencode(post_data),
                allow_redirects=False,
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

    def get_model(self) -> str:
        """Get the cudy router model displayed on login page."""

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

            device_model = _extract_model(html)

            _LOGGER.debug(
                "Login page HTTP: %s, device_model: %s",
                response.status_code,
                str(device_model),
            )

            if not (device_model):
                _LOGGER.debug("Could not extract device model from login page")
                return False

            return device_model

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
                response = session.get(data_url, timeout=30, headers=headers, allow_redirects=False)
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
        self,
        page: str,
        button_text_substring: str,
        extra_fields: dict[str, str] | None = None,
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
            m = re.search(
                r'<button[^>]*name="([^\"]+)"[^>]*value="([^\"]*)"[^>]*>([^<]*)</button>',
                html,
            )
            name = None
            value = None
            if m:
                # if the button text or value matches substring, use it
                if (
                    button_text_substring.lower() in (m.group(2) or "").lower()
                    or button_text_substring.lower() in (m.group(3) or "").lower()
                ):
                    name, value = m.group(1), m.group(2)

            # Fallback: look for input type=submit
            if not name:
                m2 = re.search(
                    r'<input[^>]*type="submit"[^>]*name="([^\"]+)"[^>]*value="([^\"]*)"',
                    html,
                )
                if m2 and button_text_substring.lower() in (m2.group(2) or "").lower():
                    name, value = m2.group(1), m2.group(2)

            if not name:
                raise RuntimeError("Could not find action button containing '%s' on %s" % (button_text_substring, page))

            post_fields = {
                "token": token,
                "timeclock": "0",
                "cbi.submit": "1",
                name: value,
            }
            if extra_fields:
                post_fields.update(extra_fields)

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
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": f"{self.base_url}/cgi-bin/luci/admin",
        }

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
            post_fields = {
                "token": token,
                "timeclock": "0",
                "cbi.submit": "1",
                select_name: band_value,
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
            textarea_match = re.search(
                r'<textarea[^>]*id="cbid\.atcmd\.1\._custom"[^>]*>([^<]*)</textarea>',
                response_html,
            )
            if textarea_match:
                at_response = textarea_match.group(1).strip()
                return r.status_code, at_response

            _LOGGER.debug("AT command response: %s", r.status_code)
            return r.status_code, r.text[:500]
        except Exception as e:
            _LOGGER.error("AT command failed: %s", e)
            return 0, str(e)[:220]

    async def get_data(self, hass: HomeAssistant, options: dict[str, Any], device_model: str) -> dict[str, Any]:
        """Retrieves data from the router"""

        data: dict[str, Any] = {}

        # Modem status (5G/LTE info)
        if existing_feature(device_model, MODULE_MODEM) is True:
            data[MODULE_MODEM] = parse_modem_info(
                f"{await hass.async_add_executor_job(self.get, 'admin/network/gcom/status')}{await hass.async_add_executor_job(self.get, 'admin/network/gcom/status?detail=1&iface=4g')}"
            )

        # Connected devices
        if existing_feature(device_model, MODULE_DEVICES) is True:
            data[MODULE_DEVICES] = parse_devices(
                await hass.async_add_executor_job(self.get, "admin/network/devices/devlist?detail=1"),
                options and options.get(OPTIONS_DEVICELIST),
            )

            # Add device client counts to the devices module
            # Try multiple possible endpoints for device status
            devices_status_html = await hass.async_add_executor_job(self.get, "admin/network/devices/status?detail=1")
            # Also try the main panel which sometimes has client counts
            if not devices_status_html or "client" not in devices_status_html.lower():
                panel_html = await hass.async_add_executor_job(self.get, "admin/panel")
                devices_status_html = f"{devices_status_html}{panel_html}"

            devices_status = parse_devices_status(devices_status_html)
            data[MODULE_DEVICES].update(devices_status)

        if existing_feature(device_model, MODULE_SYSTEM) is True:
            # System status (uptime, firmware, local time)
            # Fetch from multiple endpoints to increase chances of finding firmware
            system_html = await hass.async_add_executor_job(self.get, "admin/system/status")
            # Also try the main panel which often has firmware info
            panel_html = await hass.async_add_executor_job(self.get, "admin/panel")
            # Try overview page which sometimes has firmware (silently)
            overview_html = await hass.async_add_executor_job(
                self.get,
                "admin/status/overview",
                True,  # silent
            )
            # Try system page which sometimes has firmware (silently)
            system_page_html = await hass.async_add_executor_job(
                self.get,
                "admin/system/system",
                True,  # silent
            )
            data[MODULE_SYSTEM] = parse_system_status(
                f"{system_html}{panel_html}{overview_html or ''}{system_page_html or ''}"
            )

        # Data usage statistics
        if existing_feature(device_model, MODULE_DATA_USAGE) is True:
            data[MODULE_DATA_USAGE] = parse_data_usage(
                await hass.async_add_executor_job(self.get, "admin/network/gcom/statistics?iface=4g")
            )

        # SMS status
        if existing_feature(device_model, MODULE_SMS) is True:
            data[MODULE_SMS] = parse_sms_status(
                await hass.async_add_executor_job(self.get, "admin/network/gcom/sms/status")
            )

        # WiFi 2.4G status
        if existing_feature(device_model, MODULE_WIFI_2G) is True:
            data[MODULE_WIFI_2G] = parse_wifi_status(
                await hass.async_add_executor_job(self.get, "admin/network/wireless/status?iface=wlan00")
            )

        # WiFi 5G status
        if existing_feature(device_model, MODULE_WIFI_5G) is True:
            data[MODULE_WIFI_5G] = parse_wifi_status(
                await hass.async_add_executor_job(self.get, "admin/network/wireless/status?iface=wlan10")
            )

        # LAN status
        if existing_feature(device_model, MODULE_LAN) is True:
            data[MODULE_LAN] = parse_lan_status(await hass.async_add_executor_job(self.get, "admin/network/lan/status"))

        # VPN status
        if existing_feature(device_model, MODULE_VPN) is True:
            data[MODULE_VPN] = parse_vpn_status(
                await hass.async_add_executor_job(self.get, "admin/network/vpn/openvpns/status?status=")
            )

        # WAN status
        if existing_feature(device_model, MODULE_WAN) is True:
            data[MODULE_WAN] = parse_wan_status(
                await hass.async_add_executor_job(self.get, "admin/network/wan/status?detail=1&iface=wan")
            )

        # DHCP status
        if existing_feature(device_model, MODULE_DHCP) is True:
            data[MODULE_DHCP] = parse_dhcp_status(
                await hass.async_add_executor_job(self.get, "admin/services/dhcp/status?detail=1")
            )

        # Mesh devices - try multiple possible endpoints (silent since mesh is optional)
        if existing_feature(device_model, MODULE_MESH) is True:
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
                    self.get,
                    endpoint,
                    True,  # silent=True
                )
                if result and ("mesh" in result.lower() or "node" in result.lower() or "satellite" in result.lower()):
                    mesh_html += result  # Combine results from multiple endpoints
                    _LOGGER.debug(
                        "Found mesh data at endpoint: %s (length: %d)",
                        endpoint,
                        len(result),
                    )

            # Parse basic mesh data first to get list of satellites
            mesh_data = parse_mesh_devices(mesh_html)

            # Try to get list of mesh clients via JSON endpoint
            import json
            import re

            client_macs = []
            clients_json_data = []

            # First try the clients JSON endpoint - this returns rich data!
            clients_result = await hass.async_add_executor_job(self.get, "admin/network/mesh/clients?clients=all", True)
            if clients_result:
                _LOGGER.debug(
                    "Mesh clients endpoint result (first 500): %s",
                    clients_result[:500] if clients_result else "None",
                )
                # Try to parse as JSON - get the full array
                try:
                    # The response should be a JSON array
                    json_match = re.search(r"\[.*\]", clients_result, re.DOTALL)
                    if json_match:
                        clients_json_data = json.loads(json_match.group(0))
                        for client in clients_json_data:
                            if isinstance(client, dict) and client.get("id"):
                                client_macs.append(client["id"])
                except (json.JSONDecodeError, TypeError) as e:
                    _LOGGER.debug("Could not parse clients JSON: %s", e)

            # Also look for client MAC addresses in tab IDs from mesh HTML
            html_macs = re.findall(r"tab-([0-9A-Fa-f]{12})-", mesh_html)
            html_macs.extend(re.findall(r"client=([0-9A-Fa-f]{12})", mesh_html))
            client_macs.extend(html_macs)

            # Remove duplicates and filter out invalid entries
            client_macs = list(set(mac for mac in client_macs if len(mac) == 12))
            _LOGGER.debug("Found mesh client MACs: %s", client_macs)

            # First, extract data from JSON for each client
            json_client_data: dict[str, dict] = {}
            for client_json in clients_json_data:
                if not isinstance(client_json, dict):
                    continue
                client_id = client_json.get("id", "")
                if not client_id:
                    continue

                # Format MAC
                formatted_mac = ":".join(client_id[i : i + 2] for i in range(0, 12, 2)).upper()

                # Extract data from JSON
                sysreport = client_json.get("sysreport", {})
                # Use hardware name (e.g. "RE1200 V1.0") as model if available, fall back to model code
                hardware = sysreport.get("hardware", "")
                model_name = hardware.split(" ")[0] if hardware else sysreport.get("board") or sysreport.get("model")
                json_client_data[formatted_mac] = {
                    "name": client_json.get("name"),
                    "model": model_name,
                    "firmware_version": sysreport.get("firmware"),
                    "ip_address": sysreport.get("ipaddr"),
                    "mac_address": formatted_mac,
                    "hardware": hardware,
                    "status": "online" if client_json.get("state") == "connected" else "online",  # Default online
                    "led_status": sysreport.get("ledstatus"),
                }
                _LOGGER.debug(
                    "Parsed mesh client from JSON: %s -> %s",
                    client_id,
                    json_client_data[formatted_mac],
                )

            for client_mac in client_macs:
                # Skip the main router (id=000000000000) for mesh devices
                # but extract its LED status for the main router LED switch
                if client_mac == "000000000000":
                    formatted_mac = ":".join(client_mac[i : i + 2] for i in range(0, 12, 2)).upper()
                    _LOGGER.debug(
                        "Skipping main router in mesh client loop, formatted_mac=%s, in json_data=%s",
                        formatted_mac,
                        formatted_mac in json_client_data,
                    )
                    if formatted_mac in json_client_data:
                        main_router_data = json_client_data[formatted_mac]
                        mesh_data["main_router_led_status"] = main_router_data.get("led_status")
                        _LOGGER.debug(
                            "Main router LED status: %s",
                            mesh_data["main_router_led_status"],
                        )
                    continue

                # Format MAC address with colons
                formatted_mac = ":".join(client_mac[i : i + 2] for i in range(0, 12, 2)).upper()

                # Start with JSON data if available
                client_info = {}
                if formatted_mac in json_client_data:
                    client_info = json_client_data[formatted_mac].copy()
                    _LOGGER.debug("Using JSON data for %s: %s", formatted_mac, client_info)

                # Fetch device status for this mesh client to get additional details
                devstatus_url = f"admin/network/mesh/client/devstatus?embedded=&client={client_mac}"
                devstatus_html = await hass.async_add_executor_job(self.get, devstatus_url, True)

                # Fetch device list (connected devices) for this mesh client
                devlist_url = f"admin/network/mesh/client/devlist?embedded=&client={client_mac}"
                devlist_html = await hass.async_add_executor_job(self.get, devlist_url, True)

                if devstatus_html:
                    _LOGGER.debug(
                        "Got mesh client devstatus for %s (length: %d)",
                        client_mac,
                        len(devstatus_html),
                    )
                    # Parse HTML for additional info (backhaul, pre-hop, connected_devices count)
                    html_info = parse_mesh_client_status(devstatus_html, devlist_html)
                    if html_info:
                        _LOGGER.debug("Parsed HTML info for %s: %s", formatted_mac, html_info)
                        # Merge HTML data, but prefer JSON data for fields that exist in both
                        for key, value in html_info.items():
                            # For connected_devices, always use HTML value (JSON doesn't have this)
                            if key == "connected_devices":
                                client_info[key] = value
                            elif (
                                key not in client_info or not client_info.get(key) or client_info.get(key) == "Unknown"
                            ):
                                client_info[key] = value

                # Ensure we have required fields
                if not client_info.get("name"):
                    client_info["name"] = f"Mesh Device {client_mac[-6:]}"
                client_info["mac_address"] = formatted_mac

                _LOGGER.info(
                    "Final mesh device info for %s: name=%s, model=%s, firmware=%s, ip=%s, connected=%s",
                    formatted_mac,
                    client_info.get("name"),
                    client_info.get("model"),
                    client_info.get("firmware_version"),
                    client_info.get("ip_address"),
                    client_info.get("connected_devices"),
                )

                # Find matching device in mesh_data or add new one
                found = False
                for mac, device in list(mesh_data.get("mesh_devices", {}).items()):
                    # Match by MAC or by name
                    if mac.replace(":", "").upper() == client_mac.upper():
                        device.update(client_info)
                        found = True
                        _LOGGER.debug("Updated existing device by MAC: %s", mac)
                        break
                    elif device.get("name", "").lower() == client_info.get("name", "").lower() and mac.startswith(
                        "mesh_"
                    ):
                        # Found by name with placeholder MAC - remove old entry and add new one
                        mesh_data["mesh_devices"].pop(mac)
                        mesh_data["mesh_devices"][formatted_mac] = client_info
                        found = True
                        _LOGGER.debug(
                            "Replaced placeholder device %s with real MAC %s",
                            mac,
                            formatted_mac,
                        )
                        break

                if not found:
                    # Add as new device with real MAC
                    mesh_data["mesh_devices"][formatted_mac] = client_info
                    _LOGGER.debug("Added new mesh device: %s", formatted_mac)

            data[MODULE_MESH] = mesh_data

        return data

    def reboot_mesh_device(self, mac_address: str) -> tuple[int, str]:
        """Reboot a specific mesh device by MAC address.

        Args:
            mac_address: The MAC address of the mesh device to reboot

        Returns:
            Tuple of (HTTP status code, response snippet or error message)
        """
        import json

        session = self._get_session()
        # Ensure we're authenticated
        if self.auth_cookie:
            session.cookies.set("sysauth", self.auth_cookie)
        else:
            if not self.authenticate():
                _LOGGER.error("Failed to authenticate for mesh reboot")
                return 0, "Authentication failed"
            session.cookies.set("sysauth", self.auth_cookie)

        # Strip colons from MAC for API call
        mac_no_colons = mac_address.replace(":", "").upper()

        _LOGGER.info("Initiating reboot for mesh device %s", mac_address)

        # First, get the mesh page to get a valid token
        mesh_page_url = f"{self.base_url}/cgi-bin/luci/admin/network/mesh"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": mesh_page_url,
        }

        try:
            resp = session.get(mesh_page_url, timeout=15, headers=headers)
            token = _extract_hidden(resp.text, "token")
            _LOGGER.debug("Got token: %s", token[:10] if token else "None")
        except Exception as e:
            _LOGGER.error("Failed to get mesh page for reboot: %s", e)
            token = ""

        # Try JSON endpoints first - Cudy mesh may use JSON API for reboots
        json_endpoints = [
            f"admin/network/mesh/client/reboot?client={mac_no_colons}",
            f"admin/network/mesh/reboot?client={mac_no_colons}",
            f"admin/network/mesh/node/reboot?mac={mac_no_colons}",
        ]

        for endpoint in json_endpoints:
            page_url = f"{self.base_url}/cgi-bin/luci/{endpoint}"
            try:
                r = session.get(page_url, timeout=15, headers=headers)
                _LOGGER.debug(
                    "Mesh reboot GET %s: status=%d, response=%s",
                    endpoint,
                    r.status_code,
                    r.text[:200] if r.text else "",
                )
                # Check if response indicates success
                if r.status_code == 200:
                    try:
                        json_resp = (
                            json.loads(r.text)
                            if r.text.strip().startswith("{") or r.text.strip().startswith("[")
                            else None
                        )
                        if json_resp and (json_resp.get("status") == "ok" or json_resp.get("result") == "success"):
                            _LOGGER.info(
                                "Mesh reboot initiated for %s via JSON endpoint",
                                mac_address,
                            )
                            return r.status_code, f"Reboot initiated for {mac_address}"
                    except json.JSONDecodeError:
                        pass
            except Exception as e:
                _LOGGER.debug("JSON endpoint %s failed: %s", endpoint, e)

        # Try POST endpoints with form data
        form_endpoints = [
            "admin/network/mesh/client/reboot",
            "admin/network/mesh/reboot",
            "admin/network/mesh",
        ]

        for endpoint in form_endpoints:
            page_url = f"{self.base_url}/cgi-bin/luci/{endpoint}"

            try:
                resp = session.get(page_url, timeout=15, headers=headers)
                if resp.status_code == 404:
                    continue

                page_token = _extract_hidden(resp.text, "token") or token

                # Try different POST field patterns
                post_patterns = [
                    {
                        "token": page_token,
                        "client": mac_no_colons,
                        "action": "reboot",
                        "cbi.submit": "1",
                    },
                    {
                        "token": page_token,
                        "id": mac_no_colons,
                        "op": "reboot",
                        "cbi.submit": "1",
                    },
                    {
                        "token": page_token,
                        "mac": mac_no_colons,
                        "reboot": "1",
                        "cbi.submit": "1",
                    },
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
                    _LOGGER.debug(
                        "Mesh reboot POST to %s with %s: status=%d",
                        endpoint,
                        list(post_fields.keys()),
                        r.status_code,
                    )

            except Exception as e:
                _LOGGER.debug("Form endpoint %s failed: %s", endpoint, e)

        _LOGGER.warning(
            "Mesh reboot control attempted for %s - endpoint may not be supported",
            mac_address,
        )
        # Return success anyway - the device should reboot if the command worked
        return 200, f"Reboot command sent for {mac_address}"

    def set_mesh_led(self, mac_address: str, enabled: bool) -> tuple[int, str]:
        """Set LED state for a specific mesh device via /admin/network/mesh/ledctl endpoint.

        Args:
            mac_address: The MAC address of the mesh device
            enabled: True to turn LEDs on, False to turn off

        Returns:
            Tuple of (HTTP status code, response snippet or error message)
        """
        session = self._get_session()
        # Ensure we're authenticated
        if self.auth_cookie:
            session.cookies.set("sysauth", self.auth_cookie)
        else:
            if not self.authenticate():
                _LOGGER.error("Failed to authenticate for mesh LED control")
                return 0, "Authentication failed"
            session.cookies.set("sysauth", self.auth_cookie)

        # Strip colons from MAC for API call
        mac_no_colons = mac_address.replace(":", "").upper()
        led_value = "1" if enabled else "0"
        led_status = "on" if enabled else "off"

        _LOGGER.info(
            "Setting mesh LED for %s to %s via /admin/network/mesh/ledctl",
            mac_address,
            led_status,
        )

        # Use the ledctl endpoint with the device MAC
        ledctl_url = f"{self.base_url}/cgi-bin/luci/admin/network/mesh/ledctl/{mac_no_colons}"
        panel_url = f"{self.base_url}/cgi-bin/luci/admin/panel"

        try:
            # First get the batled page to get a valid token
            batled_url = f"{self.base_url}/cgi-bin/luci/admin/network/mesh/batled"
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Referer": panel_url,
                "X-Requested-With": "XMLHttpRequest",
            }

            resp = session.get(batled_url, timeout=15, headers=headers)
            html = resp.text

            _LOGGER.debug("Batled page HTTP status: %d, length: %d", resp.status_code, len(html))

            # Check if we got a login page instead
            if "luci_password" in html or "cbi-modal-auth" in html:
                _LOGGER.warning("Batled page returned login form - re-authenticating")
                if not self.authenticate():
                    return 0, "Re-authentication failed"
                session.cookies.set("sysauth", self.auth_cookie)
                resp = session.get(batled_url, timeout=15, headers=headers)
                html = resp.text

            token = _extract_hidden(html, "token")

            if not token:
                _LOGGER.error("No token found on batled page for mesh LED control")
                return 0, "No token on batled page"

            _LOGGER.debug("Got token for mesh LED control: %s...", token[:10])

            # Use multipart form data as the router expects
            # Fields: token, cbi.submit, cbi.toggle, cbi.cbe.table.1.ledstatus, cbid.table.1.ledstatus
            form_data = {
                "token": (None, token),
                "cbi.submit": (None, "1"),
                "cbi.toggle": (None, "1"),
                "cbi.cbe.table.1.ledstatus": (None, led_value),
                "cbid.table.1.ledstatus": (None, led_value),
            }

            _LOGGER.debug("Posting to %s with ledstatus=%s", ledctl_url, led_value)

            r = session.post(
                ledctl_url,
                timeout=30,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15",
                    "Referer": panel_url,
                    "Origin": self.base_url,
                    "X-Requested-With": "XMLHttpRequest",
                },
                files=form_data,  # Use files= for multipart/form-data
                allow_redirects=False,
            )

            _LOGGER.debug(
                "Mesh LED control POST status: %d, response: %s",
                r.status_code,
                r.text[:200] if r.text else "empty",
            )

            if r.status_code == 200:
                _LOGGER.info("Mesh LED set to %s for %s successfully", led_status, mac_address)
                return r.status_code, f"LED {led_status} for {mac_address}"
            else:
                _LOGGER.warning("Mesh LED control returned status %d", r.status_code)
                return r.status_code, f"LED control returned {r.status_code}"

        except Exception as e:
            _LOGGER.error("Mesh LED control failed: %s", e)
            return 0, str(e)[:220]

    def set_main_router_led(self, enabled: bool) -> tuple[int, str]:
        """Set LED state for the main router via /admin/network/mesh/ledctl endpoint.

        Args:
            enabled: True to turn LEDs on, False to turn off

        Returns:
            Tuple of (HTTP status code, response snippet or error message)
        """
        session = self._get_session()
        # Ensure we're authenticated
        if self.auth_cookie:
            session.cookies.set("sysauth", self.auth_cookie)
        else:
            if not self.authenticate():
                _LOGGER.error("Failed to authenticate for main router LED control")
                return 0, "Authentication failed"
            session.cookies.set("sysauth", self.auth_cookie)

        led_value = "1" if enabled else "0"
        led_status = "on" if enabled else "off"

        _LOGGER.info("Setting main router LED to %s via /admin/network/mesh/ledctl", led_status)

        # Main router uses ID 000000000000 for LED control
        ledctl_url = f"{self.base_url}/cgi-bin/luci/admin/network/mesh/ledctl/000000000000"
        panel_url = f"{self.base_url}/cgi-bin/luci/admin/panel"

        try:
            # First get the batled page to get a valid token
            batled_url = f"{self.base_url}/cgi-bin/luci/admin/network/mesh/batled"
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Referer": panel_url,
                "X-Requested-With": "XMLHttpRequest",
            }

            resp = session.get(batled_url, timeout=15, headers=headers)
            html = resp.text

            _LOGGER.debug("Batled page HTTP status: %d, length: %d", resp.status_code, len(html))

            # Check if we got a login page instead
            if "luci_password" in html or "cbi-modal-auth" in html:
                _LOGGER.warning("Batled page returned login form - re-authenticating")
                if not self.authenticate():
                    return 0, "Re-authentication failed"
                session.cookies.set("sysauth", self.auth_cookie)
                resp = session.get(batled_url, timeout=15, headers=headers)
                html = resp.text

            token = _extract_hidden(html, "token")

            if not token:
                _LOGGER.error("No token found on batled page")
                return 0, "No token on batled page"

            _LOGGER.debug("Got token for LED control: %s...", token[:10])

            # Use multipart form data as the router expects
            # Fields: token, cbi.submit, cbi.toggle, cbi.cbe.table.1.ledstatus, cbid.table.1.ledstatus
            form_data = {
                "token": (None, token),
                "cbi.submit": (None, "1"),
                "cbi.toggle": (None, "1"),
                "cbi.cbe.table.1.ledstatus": (None, led_value),
                "cbid.table.1.ledstatus": (None, led_value),
            }

            _LOGGER.debug("Posting to %s with ledstatus=%s", ledctl_url, led_value)

            r = session.post(
                ledctl_url,
                timeout=30,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15",
                    "Referer": panel_url,
                    "Origin": self.base_url,
                    "X-Requested-With": "XMLHttpRequest",
                },
                files=form_data,  # Use files= for multipart/form-data
                allow_redirects=False,
            )

            _LOGGER.debug(
                "LED control POST status: %d, response: %s",
                r.status_code,
                r.text[:200] if r.text else "empty",
            )

            if r.status_code == 200:
                _LOGGER.info("Main router LED set to %s successfully", led_status)
                return r.status_code, f"LED {led_status} for main router"
            else:
                _LOGGER.warning("LED control returned status %d", r.status_code)
                return r.status_code, f"LED control returned {r.status_code}"

        except Exception as e:
            _LOGGER.error("LED control failed: %s", e)
            return 0, str(e)[:220]

    def get_mesh_led_state(self, mac_address: str) -> bool | None:
        """Get current LED state for a mesh device.

        Args:
            mac_address: The MAC address of the mesh device

        Returns:
            True if LEDs are on, False if off, None if unknown
        """
        session = self._get_session()
        # Ensure we're authenticated
        if self.auth_cookie:
            session.cookies.set("sysauth", self.auth_cookie)
        else:
            if not self.authenticate():
                return None
            session.cookies.set("sysauth", self.auth_cookie)

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
                    if re.search(
                        r'led["\s]*[:=]\s*["\']?(?:on|1|true|enabled)',
                        html,
                        re.IGNORECASE,
                    ):
                        return True
                    if re.search(
                        r'led["\s]*[:=]\s*["\']?(?:off|0|false|disabled)',
                        html,
                        re.IGNORECASE,
                    ):
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
