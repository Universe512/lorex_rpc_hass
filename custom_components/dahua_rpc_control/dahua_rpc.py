import json
import logging
import urllib.request
import urllib.error
import hashlib
import threading

_LOGGER = logging.getLogger(__name__)


class DahuaRPC:
    def __init__(self, host, username, password):
        if not host.startswith("http://") and not host.startswith("https://"):
            host = f"http://{host}"
            
        self.host = host.rstrip("/")
        self.username = username
        self.password = password
        self.session = None
        self.id_counter = 10000
        
        # This lock forces simultaneous Home Assistant updates into a single-file line 
        # so we don't crash the camera's web server with "too many connections"
        self._lock = threading.RLock()

    # =========================================================================
    # CORE NETWORK & AUTHENTICATION
    # =========================================================================

    def _next_id(self):
        self.id_counter += 1
        return self.id_counter

    def _get_cgi(self, url):
        """Helper to perform a legacy CGI GET request with robust Digest Auth."""
        with self._lock:
            _LOGGER.debug("Dahua CGI GET URL: %s", url)
            
            # Setup HTTP Digest authentication handler
            password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
            password_mgr.add_password(None, self.host, self.username, self.password)
            handler = urllib.request.HTTPDigestAuthHandler(password_mgr)
            opener = urllib.request.build_opener(handler)
            
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0",
                }
            )
            
            try:
                with opener.open(req, timeout=10) as response:
                    raw = response.read().decode("utf-8", errors="replace")
                    _LOGGER.debug("Dahua CGI RAW RESPONSE: %s", raw)
                    return raw
            except urllib.error.HTTPError as err:
                _LOGGER.error("Dahua CGI HTTP error %s: %s", err.code, err.reason)
                raise
            except urllib.error.URLError as err:
                _LOGGER.error("Dahua CGI URL error: %s", err)
                raise

    def control_coaxial_cgi(self, io_state, channel=1):
        """
        Triggers hardware IO via the stable coaxialControlIO.cgi endpoint.
        Uses explicit URL-encoded brackets to bypass strict camera parsers.
        """
        url = f"{self.host}/cgi-bin/coaxialControlIO.cgi?action=control&channel={channel}&info%5B0%5D.Type=2&info%5B0%5D.IO={io_state}"
        return self._get_cgi(url)

    def _post(self, path, body, retry=True):
        # The 'with self._lock' ensures only one thread can run this block at a time
        with self._lock:
            url = f"{self.host}{path}"
            data = json.dumps(body, separators=(",", ":")).encode("utf-8")

            _LOGGER.debug("Dahua RPC POST URL: %s", url)
            _LOGGER.debug("Dahua RPC POST BODY: %s", data.decode("utf-8"))

            req = urllib.request.Request(
                url,
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/plain, */*",
                    "User-Agent": "Mozilla/5.0",
                    "Origin": self.host,
                    "Referer": f"{self.host}/",
                },
                method="POST",
            )

            try:
                with urllib.request.urlopen(req, timeout=10) as response:
                    raw = response.read().decode("utf-8", errors="replace")
                    _LOGGER.debug("Dahua RPC RAW RESPONSE: %s", raw)
                    result = json.loads(raw)
                    
                    if result.get("error"):
                        err_code = result["error"].get("code")
                        err_msg = result["error"].get("message", "")
                        
                        if err_code in [401, 1003, 268632075, 268632079, 285212675] or "session" in err_msg.lower():
                            _LOGGER.warning("Session error/expired (%s). Clearing session.", err_msg)
                            self.session = None
                            
                            if retry and path != "/RPC2_Login":
                                _LOGGER.info("Attempting to auto-reconnect.")
                                self.login()
                                if "session" in body:
                                    body["session"] = self.session
                                body["id"] = self._next_id()
                                return self._post(path, body, retry=False)
                                
                    return result

            except urllib.error.HTTPError as err:
                raw = err.read().decode("utf-8", errors="replace")
                _LOGGER.error("Dahua RPC HTTP error %s: %s", err.code, raw)
                if err.code == 401:
                    self.session = None
                    if retry and path != "/RPC2_Login":
                        _LOGGER.info("Attempting to auto-reconnect after HTTP 401.")
                        self.login()
                        if "session" in body:
                            body["session"] = self.session
                        body["id"] = self._next_id()
                        return self._post(path, body, retry=False)
                raise

            except urllib.error.URLError as err:
                _LOGGER.error("Dahua RPC URL error: %s", err)
                raise

    def login(self):
        with self._lock:
            login_id = self._next_id()
            step1_body = {
                "method": "global.login",
                "params": {
                    "userName": self.username,
                    "password": "",
                    "clientType": "Web3.0",
                    "loginType": "Direct",
                },
                "id": login_id,
                "session": 0,
            }

            step1 = self._post("/RPC2_Login", step1_body, retry=False)

            self.session = step1.get("session")
            params = step1.get("params", {})
            realm = params.get("realm")
            random = params.get("random")

            if not self.session or not realm or not random:
                raise ValueError(f"Invalid Dahua login step 1 response: {step1}")

            pwd_hash = hashlib.md5(f"{self.username}:{realm}:{self.password}".encode("utf-8")).hexdigest().upper()
            final_hash = hashlib.md5(f"{self.username}:{random}:{pwd_hash}".encode("utf-8")).hexdigest().upper()

            step2_body = {
                "method": "global.login",
                "params": {
                    "userName": self.username,
                    "password": final_hash,
                    "clientType": "Web3.0",
                    "loginType": "Direct",
                    "authorityType": "Default",
                },
                "id": self._next_id(),
                "session": self.session,
            }

            step2 = self._post("/RPC2_Login", step2_body, retry=False)

            if not step2.get("result"):
                self.session = None
                raise ValueError(f"Dahua login failed step 2: {step2}")

            _LOGGER.info("Dahua RPC login successful. Session: %s", self.session)
            return step2

    def ensure_login(self):
        with self._lock:
            if not self.session:
                return self.login()
            return {"session": self.session}

    # =========================================================================
    # GENERIC CONFIG GETTERS AND SETTERS
    # =========================================================================

    def get_config(self, config_name):
        self.ensure_login()
        body = {
            "method": "configManager.getConfig",
            "params": {"name": config_name},
            "id": self._next_id(),
            "session": self.session,
        }
        return self._post("/RPC2", body)

    def set_config(self, config_name, table_data):
        self.ensure_login()
        body = {
            "method": "configManager.setConfig",
            "params": {
                "name": config_name, 
                "table": table_data,
                "options": []
            },
            "id": self._next_id(),
            "session": self.session,
        }
        return self._post("/RPC2", body)

    # =========================================================================
    # COAXIAL CONTROL (LIGHTS & SIRENS) - Legacy / NVR fallback
    # =========================================================================

    def control_coaxial_io(self, io_type, io_state, trigger_mode=2):
        self.ensure_login()
        body = {
            "method": "CoaxialControlIO.control",
            "params": {
                "info": [
                    {
                        "Type": io_type,
                        "IO": io_state,
                        "TriggerMode": trigger_mode
                    }
                ],
                "channel": 0
            },
            "id": self._next_id(),
            "session": self.session
        }
        return self._post("/RPC2", body)

    # =========================================================================
    # SPECIALIZED HELPERS
    # =========================================================================

    def get_video_analyse_global(self):
        return self.get_config("VideoAnalyseGlobal")

    def set_video_analyse_type(self, analyse_type=""):
        current = self.get_video_analyse_global()
        table = None
        if isinstance(current, dict):
            if "params" in current and isinstance(current["params"], dict):
                table = current["params"].get("table")
            if table is None and "result" in current and isinstance(current["result"], dict):
                table = current["result"].get("table")

        if not table or not isinstance(table, list) or len(table) == 0:
            raise ValueError(f"Could not find VideoAnalyseGlobal table in response: {current}")

        if "Scene" not in table[0]:
            table[0]["Scene"] = {}

        table[0]["Scene"]["Type"] = analyse_type
        result = self.set_config("VideoAnalyseGlobal", table)
        verify = self.get_video_analyse_global()
        return {"set_result": result, "verify_result": verify}

    def set_lighting_scheme(self, mode):
        """Helper to set LightingScheme mode across all configured time periods."""
        current = self.get_config("LightingScheme")
        table = None
        if isinstance(current, dict):
            if "params" in current and isinstance(current["params"], dict):
                table = current["params"].get("table")
            if table is None and "result" in current and isinstance(current["result"], dict):
                table = current["result"].get("table")

        if not table or not isinstance(table, list) or len(table) == 0:
            raise ValueError(f"Could not find LightingScheme table in response: {current}")

        # The Dahua API expects the mode applied to every time block in the array.
        if isinstance(table[0], list):
            for item in table[0]:
                item["LightingMode"] = mode
        elif isinstance(table[0], dict):
            table[0]["LightingMode"] = mode

        result = self.set_config("LightingScheme", table)
        verify = self.get_config("LightingScheme")
        return {"set_result": result, "verify_result": verify}