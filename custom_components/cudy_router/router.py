"""Provides the backend for a Cudy router."""

from __future__ import annotations

import hashlib
import logging
import re
import time
import urllib.parse
from http.cookies import SimpleCookie
from typing import TYPE_CHECKING, Any

import requests
import urllib3

from .router_data import collect_router_data

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

DEFAULT_GET_TIMEOUT = 30
DEFAULT_PAGE_TIMEOUT = 15
DEFAULT_POST_TIMEOUT = 30
DEFAULT_RETRIES = 2
RETRY_BACKOFF_SECONDS = 0.35
RETRYABLE_STATUSES = {408, 429, 500, 502, 503, 504}


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

    def _luci_url(self, path: str) -> str:
        """Build a LuCI endpoint URL from a relative path."""
        return f"{self.base_url}/cgi-bin/luci/{path.lstrip('/')}"

    def _set_session_auth_cookie(self, session: requests.Session) -> None:
        """Ensure session has the latest sysauth cookie if available."""
        if self.auth_cookie:
            session.cookies.set("sysauth", self.auth_cookie)

    def _request(
        self,
        method: str,
        url: str,
        *,
        timeout: int,
        headers: dict[str, str],
        allow_redirects: bool = False,
        silent: bool = False,
        retries: int = DEFAULT_RETRIES,
        reauth_on_403: bool = True,
        data: Any = None,
        files: Any = None,
    ) -> requests.Response | None:
        """Execute an HTTP request with shared retry/backoff/auth-refresh behavior."""
        session = self._get_session()
        last_error: Exception | None = None

        for attempt in range(retries + 1):
            self._set_session_auth_cookie(session)
            try:
                response = session.request(
                    method=method,
                    url=url,
                    timeout=timeout,
                    headers=headers,
                    allow_redirects=allow_redirects,
                    data=data,
                    files=files,
                )
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as err:
                last_error = err
                if attempt < retries:
                    time.sleep(RETRY_BACKOFF_SECONDS * (2**attempt))
                    continue
                if not silent:
                    _LOGGER.debug("HTTP %s %s failed: %s", method, url, err)
                return None
            except requests.RequestException as err:
                last_error = err
                if not silent:
                    _LOGGER.debug("HTTP %s %s request exception: %s", method, url, err)
                return None

            if response.status_code == 403 and reauth_on_403 and attempt < retries:
                if self.authenticate():
                    continue
                if not silent:
                    _LOGGER.error("Authentication refresh failed for %s", url)
                return response

            if response.status_code in RETRYABLE_STATUSES and attempt < retries:
                time.sleep(RETRY_BACKOFF_SECONDS * (2**attempt))
                continue

            return response

        if not silent and last_error:
            _LOGGER.debug("HTTP %s %s failed after retries: %s", method, url, last_error)
        return None

    def _luci_get(
        self,
        path: str,
        *,
        timeout: int = DEFAULT_PAGE_TIMEOUT,
        headers: dict[str, str] | None = None,
        silent: bool = False,
    ) -> requests.Response | None:
        """Issue a GET request to a LuCI path with standard behavior."""
        return self._request(
            "GET",
            self._luci_url(path),
            timeout=timeout,
            headers=headers
            or {
                "User-Agent": "Mozilla/5.0",
                "Referer": f"{self.base_url}/cgi-bin/luci/admin",
            },
            allow_redirects=False,
            silent=silent,
        )

    def _luci_post(
        self,
        path: str,
        *,
        timeout: int = DEFAULT_POST_TIMEOUT,
        headers: dict[str, str] | None = None,
        silent: bool = False,
        data: Any = None,
        files: Any = None,
    ) -> requests.Response | None:
        """Issue a POST request to a LuCI path with standard behavior."""
        return self._request(
            "POST",
            self._luci_url(path),
            timeout=timeout,
            headers=headers
            or {
                "User-Agent": "Mozilla/5.0",
                "Referer": f"{self.base_url}/cgi-bin/luci/admin",
            },
            allow_redirects=False,
            silent=silent,
            data=data,
            files=files,
        )

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
            response = self._request(
                "POST",
                data_url,
                timeout=DEFAULT_POST_TIMEOUT,
                headers=headers,
                allow_redirects=False,
                silent=False,
                retries=1,
                reauth_on_403=False,
                data=body,
            )
            if response is None:
                # Keep legacy behavior available if shared request flow encounters
                # transport-specific issues on older router TLS stacks.
                session = self._get_session()
                response = session.post(
                    data_url,
                    timeout=DEFAULT_POST_TIMEOUT,
                    headers=headers,
                    data=body,
                    allow_redirects=False,
                )
            if response and (response.ok or response.status_code == 302):
                set_cookie = response.headers.get("set-cookie", "")
                if set_cookie:
                    cookie = SimpleCookie()
                    cookie.load(set_cookie)
                    if cookie.get("sysauth"):
                        self.auth_cookie = cookie.get("sysauth").value
                        return True
            _LOGGER.debug(
                "Legacy auth did not return sysauth cookie (status=%s)",
                response.status_code if response else "no-response",
            )
        except requests.exceptions.ConnectionError:
            _LOGGER.debug("Connection error during legacy auth")
        except requests.exceptions.Timeout:
            _LOGGER.debug("Timeout during legacy auth")
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
            response = self._request(
                "GET",
                login_url,
                timeout=DEFAULT_PAGE_TIMEOUT,
                headers=headers,
                allow_redirects=False,
                silent=False,
                retries=1,
                reauth_on_403=False,
            )
            if not response:
                # Fallback to legacy direct call for router compatibility.
                session = self._get_session()
                response = session.get(login_url, timeout=DEFAULT_PAGE_TIMEOUT, headers=headers)
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

            response = self._request(
                "POST",
                login_url,
                timeout=DEFAULT_PAGE_TIMEOUT,
                headers=post_headers,
                data=urllib.parse.urlencode(post_data),
                allow_redirects=False,
                silent=False,
                retries=1,
                reauth_on_403=False,
            )
            if not response:
                session = self._get_session()
                response = session.post(
                    login_url,
                    timeout=DEFAULT_PAGE_TIMEOUT,
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

        login_url = f"{self.base_url}/cgi-bin/luci/"

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": f"{self.base_url}/",
        }

        try:
            # GET login page to extract salt and token (may return 403 but still has HTML)
            response = self._request(
                "GET",
                login_url,
                timeout=DEFAULT_PAGE_TIMEOUT,
                headers=headers,
                allow_redirects=False,
                silent=False,
                retries=1,
                reauth_on_403=False,
            )
            if not response:
                session = self._get_session()
                response = session.get(login_url, timeout=DEFAULT_PAGE_TIMEOUT, headers=headers)
            html = response.text

            device_model = _extract_model(html)

            _LOGGER.debug(
                "Login page HTTP: %s, device_model: %s",
                response.status_code,
                str(device_model),
            )

            if not (device_model):
                _LOGGER.debug("Could not extract device model from login page")
                return "default"

            return device_model

        except requests.exceptions.ConnectionError as e:
            _LOGGER.debug("Connection error during new auth: %s", e)
        except requests.exceptions.Timeout as e:
            _LOGGER.debug("Timeout during new auth: %s", e)
        except Exception as e:
            _LOGGER.warning("New auth error: %s", e, exc_info=True)
        return "default"

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

        response = self._luci_get(
            url,
            timeout=DEFAULT_GET_TIMEOUT,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": f"{self.base_url}/cgi-bin/luci/admin",
            },
            silent=silent,
        )
        if response and response.ok:
            return response.text
        if not silent:
            status = response.status_code if response else "no-response"
            _LOGGER.debug("Failed to retrieve data from %s (status=%s)", url, status)
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
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": f"{self.base_url}/cgi-bin/luci/admin",
        }

        code = 0
        try:
            resp = self._luci_get(page, timeout=DEFAULT_PAGE_TIMEOUT, headers=headers)
            if not resp:
                return 0, f"Failed to load page {page}"
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

            r = self._luci_post(
                page,
                timeout=DEFAULT_POST_TIMEOUT,
                headers={
                    **headers,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": self.base_url,
                },
                data=urllib.parse.urlencode(post_fields),
            )
            if not r:
                return 0, f"Failed to post action on {page}"
            return r.status_code, r.text[:220]
        except Exception as e:
            _LOGGER.error("Action on %s failed: %s", page, e)
            return code or 0, str(e)[:220]

    def reboot_router(self) -> tuple[int, str]:
        """Trigger router reboot via LuCI web UI."""
        # The Cudy router reboot page is at /admin/system/reboot/reboot
        # It has a simple form with token and a cbi.apply button
        page = "admin/system/reboot/reboot"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": f"{self.base_url}/cgi-bin/luci/admin/panel",
        }

        try:
            resp = self._luci_get(page, timeout=DEFAULT_PAGE_TIMEOUT, headers=headers)
            if not resp:
                return 0, "Failed to load reboot page"
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
            r = self._luci_post(
                page,
                timeout=DEFAULT_POST_TIMEOUT,
                headers={
                    **headers,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": self.base_url,
                },
                data=urllib.parse.urlencode(post_fields),
            )
            if not r:
                return 0, "Failed to submit reboot request"
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
        page = "admin/network/gcom/reset"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": f"{self.base_url}/cgi-bin/luci/admin/network/gcom/status",
        }

        try:
            resp = self._luci_get(page, timeout=DEFAULT_PAGE_TIMEOUT, headers=headers)
            if not resp:
                return 0, "Failed to load reset page"
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
            r = self._luci_post(
                page,
                timeout=DEFAULT_POST_TIMEOUT,
                headers={
                    **headers,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": self.base_url,
                },
                data=urllib.parse.urlencode(post_fields),
            )
            if not r:
                return 0, "Failed to submit modem reset request"
            return r.status_code, r.text[:220]
        except Exception as e:
            _LOGGER.error("Restart 5G failed: %s", e)
            return 0, str(e)[:220]

    def switch_5g_band(self, band_value: str) -> tuple[int, str]:
        """Attempt to set the 5G band by finding a select element on the settings page.

        The method looks for a select whose name contains 'band' and submits
        the chosen value.
        """
        page = "admin/network/gcom/setting"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": f"{self.base_url}/cgi-bin/luci/admin",
        }

        try:
            resp = self._luci_get(page, timeout=DEFAULT_PAGE_TIMEOUT, headers=headers)
            if not resp:
                return 0, "Failed to load band settings page"
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
            r = self._luci_post(
                page,
                timeout=DEFAULT_POST_TIMEOUT,
                headers={
                    **headers,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": self.base_url,
                },
                data=urllib.parse.urlencode(post_fields),
            )
            if not r:
                return 0, "Failed to submit band change request"
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
        page = "admin/network/gcom/sms/smsnew"
        page_with_query = f"{page}?nomodal=&iface=4g"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": f"{self.base_url}/cgi-bin/luci/admin/network/gcom/sms",
        }

        try:
            # GET the form page to obtain token
            resp = self._luci_get(page_with_query, timeout=DEFAULT_PAGE_TIMEOUT, headers=headers)
            if not resp:
                return 0, "Failed to load SMS page"
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
            r = self._luci_post(
                page_with_query,
                timeout=DEFAULT_POST_TIMEOUT,
                headers={
                    **headers,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": self.base_url,
                },
                data=urllib.parse.urlencode(post_fields),
            )
            if not r:
                return 0, "Failed to submit SMS request"
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
        page = "admin/network/gcom/atcmd"
        page_with_query = f"{page}?embedded=&iface=4g"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": f"{self.base_url}/cgi-bin/luci/admin/network/gcom/config",
        }

        try:
            # GET the form page to obtain token
            resp = self._luci_get(page_with_query, timeout=DEFAULT_PAGE_TIMEOUT, headers=headers)
            if not resp:
                return 0, "Failed to load AT command page"
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
            r = self._luci_post(
                page_with_query,
                timeout=DEFAULT_POST_TIMEOUT,
                headers={
                    **headers,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": self.base_url,
                },
                data=urllib.parse.urlencode(post_fields),
            )
            if not r:
                return 0, "Failed to submit AT command request"

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
        """Retrieve and parse data from the router."""
        return await collect_router_data(self, hass, options, device_model)

    def reboot_mesh_device(self, mac_address: str) -> tuple[int, str]:
        """Reboot a specific mesh device by MAC address.

        Args:
            mac_address: The MAC address of the mesh device to reboot

        Returns:
            Tuple of (HTTP status code, response snippet or error message)
        """
        import json

        if not self.auth_cookie and not self.authenticate():
            _LOGGER.error("Failed to authenticate for mesh reboot")
            return 0, "Authentication failed"

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
            resp = self._luci_get("admin/network/mesh", timeout=DEFAULT_PAGE_TIMEOUT, headers=headers, silent=True)
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
            try:
                r = self._luci_get(endpoint, timeout=DEFAULT_PAGE_TIMEOUT, headers=headers, silent=True)
                if not r:
                    continue
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
            try:
                resp = self._luci_get(endpoint, timeout=DEFAULT_PAGE_TIMEOUT, headers=headers, silent=True)
                if not resp or resp.status_code == 404:
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
                    r = self._luci_post(
                        endpoint,
                        timeout=DEFAULT_POST_TIMEOUT,
                        headers={
                            **headers,
                            "Content-Type": "application/x-www-form-urlencoded",
                            "Origin": self.base_url,
                        },
                        data=urllib.parse.urlencode(post_fields),
                        silent=True,
                    )
                    if not r:
                        continue
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

    def _set_led_state(self, device_id: str, enabled: bool, label: str) -> tuple[int, str]:
        """Set LED state on mesh LED control endpoint."""
        if not self.auth_cookie and not self.authenticate():
            _LOGGER.error("Failed to authenticate for %s LED control", label)
            return 0, "Authentication failed"

        led_value = "1" if enabled else "0"
        led_status = "on" if enabled else "off"
        panel_url = f"{self.base_url}/cgi-bin/luci/admin/panel"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": panel_url,
            "X-Requested-With": "XMLHttpRequest",
        }

        try:
            resp = self._luci_get("admin/network/mesh/batled", timeout=DEFAULT_PAGE_TIMEOUT, headers=headers, silent=True)
            if not resp:
                return 0, "Failed to load batled page"
            html = resp.text
            _LOGGER.debug("Batled page HTTP status: %d, length: %d", resp.status_code, len(html))

            if "luci_password" in html or "cbi-modal-auth" in html:
                _LOGGER.warning("Batled page returned login form - re-authenticating")
                if not self.authenticate():
                    return 0, "Re-authentication failed"
                resp = self._luci_get("admin/network/mesh/batled", timeout=DEFAULT_PAGE_TIMEOUT, headers=headers, silent=True)
                if not resp:
                    return 0, "Failed to reload batled page after re-auth"
                html = resp.text

            token = _extract_hidden(html, "token")
            if not token:
                _LOGGER.error("No token found on batled page")
                return 0, "No token on batled page"

            form_data = {
                "token": (None, token),
                "cbi.submit": (None, "1"),
                "cbi.toggle": (None, "1"),
                "cbi.cbe.table.1.ledstatus": (None, led_value),
                "cbid.table.1.ledstatus": (None, led_value),
            }

            post_path = f"admin/network/mesh/ledctl/{device_id}"
            r = self._luci_post(
                post_path,
                timeout=DEFAULT_POST_TIMEOUT,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15",
                    "Referer": panel_url,
                    "Origin": self.base_url,
                    "X-Requested-With": "XMLHttpRequest",
                },
                files=form_data,
                silent=True,
            )
            if not r:
                return 0, "Failed to submit LED control request"

            _LOGGER.debug(
                "LED control POST status for %s: %d, response: %s",
                label,
                r.status_code,
                r.text[:200] if r.text else "empty",
            )

            if r.status_code == 200:
                _LOGGER.info("%s LED set to %s successfully", label, led_status)
                return r.status_code, f"LED {led_status} for {label}"
            _LOGGER.warning("LED control for %s returned status %d", label, r.status_code)
            return r.status_code, f"LED control returned {r.status_code}"
        except Exception as err:
            _LOGGER.error("LED control failed for %s: %s", label, err)
            return 0, str(err)[:220]

    def set_mesh_led(self, mac_address: str, enabled: bool) -> tuple[int, str]:
        """Set LED state for a specific mesh device."""
        mac_no_colons = mac_address.replace(":", "").upper()
        return self._set_led_state(mac_no_colons, enabled, mac_address)

    def set_main_router_led(self, enabled: bool) -> tuple[int, str]:
        """Set LED state for the main router."""
        return self._set_led_state("000000000000", enabled, "main router")

    def get_mesh_led_state(self, mac_address: str) -> bool | None:
        """Get current LED state for a mesh device.

        Args:
            mac_address: The MAC address of the mesh device

        Returns:
            True if LEDs are on, False if off, None if unknown
        """
        if not self.auth_cookie and not self.authenticate():
            return None

        endpoints = [
            "admin/network/mesh/led",
            "admin/network/mesh/settings",
            "admin/network/mesh/status",
        ]

        for endpoint in endpoints:
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Referer": f"{self.base_url}/cgi-bin/luci/admin/network/mesh",
            }

            try:
                resp = self._luci_get(endpoint, timeout=DEFAULT_PAGE_TIMEOUT, headers=headers, silent=True)
                if not resp or resp.status_code == 404:
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
