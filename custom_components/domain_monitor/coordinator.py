import asyncio
from datetime import datetime, UTC, timedelta
from functools import partial
import json
import logging
import re
import ssl

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CERT_EXPIRY_CACHE,
    CONNECTIVITY_CHECKS,
    CONNECTIVITY_TIMEOUT,
    DEFAULT_RETRIES,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLOW_THRESHOLD,
    EVENT_STATUS_CHANGED,
    KEYWORD_MAX_BODY_BYTES,
    TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)

_DEFAULT_PORTS = {"http": 80, "https": 443}
_CERT_NOT_AFTER_FORMAT = "%b %d %H:%M:%S %Y %Z"


def service_id(service: dict) -> str:
    """Stable id of a service within an entry."""
    return f"{service['host']}:{service['type']}:{service['port']}"


def _valid_port(port) -> bool:
    return isinstance(port, int) and 1 <= port <= 65535


def _normalize_service_type(service_type):
    if service_type not in ("http", "https", "tcp"):
        return None
    return service_type


def _parse_service(item) -> dict | None:
    """Parse one service entry (dict from the JSON model or legacy string)."""
    if isinstance(item, dict):
        host = str(item.get("host", "")).strip()
        service_type = _normalize_service_type(item.get("type"))
        if not host or service_type is None:
            return None

        port = item.get("port")
        if isinstance(port, str):
            try:
                port = int(port)
            except ValueError:
                port = None
        if not _valid_port(port):
            if service_type == "tcp":
                return None
            port = _DEFAULT_PORTS[service_type]

        keyword = item.get("keyword")
        return {
            "host": host,
            "type": service_type,
            "port": port,
            "keyword": keyword if isinstance(keyword, str) and keyword else None,
        }

    if not isinstance(item, str):
        return None

    # Legacy string format: host:type:port:keyword / host:type:keyword / host:tcp:port
    parts = item.strip().split(":", 3)
    if len(parts) < 2:
        return None

    host, service_type = parts[0].strip(), _normalize_service_type(parts[1])
    if service_type is None:
        return None

    if service_type in ("http", "https"):
        port = None
        keyword = None

        if len(parts) == 3:
            keyword = parts[2]
        elif len(parts) == 4:
            try:
                port = int(parts[2])
            except ValueError:
                port = None
            keyword = parts[3]

        if not _valid_port(port):
            port = _DEFAULT_PORTS[service_type]

        return {
            "host": host,
            "type": service_type,
            "port": port,
            "keyword": keyword if keyword else None,
        }

    # TCP: port required and numeric
    if len(parts) < 3:
        return None
    try:
        port = int(parts[2])
    except ValueError:
        return None
    if not _valid_port(port):
        return None

    return {"host": host, "type": "tcp", "port": port, "keyword": None}


def normalize_services(raw) -> tuple[list[dict], list[str]]:
    """Parse the stored services value (JSON list or legacy string).

    Returns the parsed services (without id) and a list of the raw entries
    that could not be parsed (for the repair issue).
    """
    if isinstance(raw, str):
        raw_items = [item for item in raw.split(",")]
    elif isinstance(raw, list):
        raw_items = raw
    else:
        raw_items = []

    services: list[dict] = []
    invalid: list[str] = []

    for item in raw_items:
        if item is None or (isinstance(item, str) and not item.strip()):
            continue
        service = _parse_service(item)
        if service is None:
            invalid.append(item if isinstance(item, str) else json.dumps(item))
        else:
            services.append(service)

    return services, invalid


def _socket_host(host: str) -> str:
    """Strip brackets from IPv6 literals for socket calls."""
    if host.startswith("[") and host.endswith("]"):
        return host[1:-1]
    return host


def _cert_common_name(field) -> str | None:
    """Extract the commonName from a getpeercert() issuer/subject field.

    The structure can be a tuple of (tuples of 2-tuples) or a tuple of
    2-tuples depending on the source, so both shapes are flattened here.
    """
    for rdn in field or ():
        if isinstance(rdn, tuple) and rdn and isinstance(rdn[0], tuple):
            entries = rdn
        else:
            entries = (rdn,)
        for entry in entries:
            if not isinstance(entry, tuple) or len(entry) < 2:
                continue
            if entry[0] == "commonName":
                return entry[1]
    return None


def parse_peer_cert(cert: dict) -> dict | None:
    """Turn an ssl getpeercert() dict into our certificate info."""
    if not cert or "notAfter" not in cert:
        return None
    try:
        not_after = datetime.strptime(cert["notAfter"], _CERT_NOT_AFTER_FORMAT)
    except (ValueError, TypeError):
        return None
    not_after = not_after.replace(tzinfo=UTC)

    return {
        "expires_at": not_after.isoformat(),
        "days_left": (not_after - datetime.now(UTC)).days,
        "issuer": _cert_common_name(cert.get("issuer")),
        "subject": _cert_common_name(cert.get("subject")),
        "checked_at": datetime.now(UTC).isoformat(),
    }


class DomainDataCoordinator(DataUpdateCoordinator):

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        self.hass = hass
        self.entry = entry

        self.interval = entry.options.get("interval", entry.data.get("interval", DEFAULT_SCAN_INTERVAL))
        self.timeout = entry.options.get("timeout", entry.data.get("timeout", TIMEOUT))
        self.retries = entry.options.get("retries", entry.data.get("retries", DEFAULT_RETRIES))
        self.slow_threshold = entry.options.get(
            "slow_threshold_ms", entry.data.get("slow_threshold_ms", DEFAULT_SLOW_THRESHOLD)
        )

        # None = not checked yet, True/False = result of the last canary check
        self._internet_ok = None

        # service ids the user paused via the switch entities
        self.disabled: set[str] = set()

        # TLS certificate info per service id (see parse_peer_cert)
        self.cert_data: dict[str, dict] = {}

        parsed, invalid = normalize_services(entry.options.get("services", entry.data.get("services", [])))
        self.services = [{**service, "id": service_id(service)} for service in parsed]
        self.invalid_services = invalid

        super().__init__(
            hass,
            logger=_LOGGER,
            name="domain_monitor",
            update_interval=timedelta(seconds=self.interval),
            config_entry=entry,
        )

        self.history: dict[str, list] = {service["id"]: [] for service in self.services}

    @property
    def internet_ok(self):
        """True/False from the last internet connectivity check, None if never run."""
        return self._internet_ok

    def uptime_percent(self, sid: str):
        """Percentage of 'up' results in the last 100 checks, None without data."""
        history = self.history.get(sid, [])
        if not history:
            return None
        ups = sum(1 for result in history if result.get("status") == "up")
        return round(100 * ups / len(history), 1)

    def cert_info(self, sid: str):
        return self.cert_data.get(sid)

    def set_enabled(self, sid: str, enabled: bool) -> None:
        """Pause/resume monitoring of one service (runtime only, no reload)."""
        if enabled:
            self.disabled.discard(sid)
        else:
            self.disabled.add(sid)

        if sid in self.disabled:
            current = (self.data or {}).get(sid)
            if self.data is None:
                self.data = {}
            self.data[sid] = {
                **(current or {}),
                "status": "unknown",
                "code": None,
                "response_ms": None,
                "enabled": False,
                "slow": False,
            }
        self.async_update_listeners()

    async def _async_update_data(self):
        results = {}

        # While the last canary check said there is no internet, the hosts are
        # still checked - but with a SINGLE attempt each instead of all
        # retries (no long timeouts). If a single host check succeeds, the
        # canary was wrong (e.g. blocked canary endpoints) and we recover;
        # if everything fails, the canary was right and the hosts are
        # reported as unknown instead of down.
        offline_mode = self._internet_ok is False
        attempts = 1 if offline_mode else None

        session = async_get_clientsession(self.hass)

        if not offline_mode:
            await self._async_refresh_certificates()

        tasks = []
        task_services = []
        for service in self.services:
            sid = service["id"]

            if sid in self.disabled:
                self._store(service, self._disabled_result(service), results)
            elif service["type"] in ("http", "https"):
                tasks.append(self.check_http(session, service, attempts=attempts))
                task_services.append(service)
            else:
                tasks.append(self.check_tcp(service, attempts=attempts))
                task_services.append(service)

        responses = await asyncio.gather(*tasks)

        # If any check failed, make sure Home Assistant itself can reach the
        # internet before blaming the monitored server.
        failed = [item for item in responses if item["status"] == "down"]
        if failed and not await self._async_check_internet():
            for item in failed:
                item["status"] = "unknown"
                item["no_internet"] = True
        elif not failed and offline_mode:
            # Hosts answer while the canaries do not: the canary endpoints are
            # misleading (blocked/filtered), internet is actually fine.
            self._internet_ok = True
            _LOGGER.info(
                "Monitored hosts are reachable while the canary checks fail - "
                "treating the canary as misleading and resuming regular checks"
            )

        for service, item in zip(task_services, responses):
            self._store(service, item, results)

        return results

    def _store(self, service: dict, item: dict, results: dict) -> None:
        sid = service["id"]

        old_status = (self.data or {}).get(sid, {}).get("status")
        if old_status is not None and old_status != item["status"]:
            self.hass.bus.async_fire(
                EVENT_STATUS_CHANGED,
                {
                    "entry_id": self.entry.entry_id,
                    "service_id": sid,
                    "host": item.get("host"),
                    "type": item.get("type"),
                    "port": item.get("port"),
                    "old_status": old_status,
                    "new_status": item["status"],
                    "response_ms": item.get("response_ms"),
                    "slow": item.get("slow", False),
                    "no_internet": item.get("no_internet", False),
                },
            )

        item.setdefault("enabled", sid not in self.disabled)
        self.history[sid].append(item)
        self.history[sid] = self.history[sid][-100:]
        results[sid] = item

    @staticmethod
    def _base_result(service: dict) -> dict:
        return {
            "host": service["host"],
            "type": service["type"],
            "port": service["port"],
            "status": "unknown",
            "code": None,
            "response_ms": None,
            "time": datetime.now(UTC),
        }

    def _disabled_result(self, service: dict) -> dict:
        return {
            **self._base_result(service),
            "enabled": False,
        }

    async def _async_check_internet(self):
        """Run the canary checks in parallel and return True if any succeeds."""
        session = async_get_clientsession(self.hass)
        tasks = []

        for check in CONNECTIVITY_CHECKS:
            if check["type"] == "http":
                tasks.append(self._canary_http(session, check["url"]))
            else:
                tasks.append(self._canary_tcp(check["host"], check["port"]))

        previous_ok = self._internet_ok
        self._internet_ok = any(await asyncio.gather(*tasks))
        if previous_ok is not False and self._internet_ok is False:
            _LOGGER.warning(
                "No internet connectivity detected (all canary checks failed) – "
                "monitored services are reported as unknown until it is back"
            )
        elif previous_ok is False and self._internet_ok:
            _LOGGER.info("Internet connectivity is back – resuming regular checks")
        _LOGGER.debug("Internet connectivity check result: %s", self._internet_ok)
        return self._internet_ok

    async def _canary_http(self, session, url):
        try:
            async with session.get(url, timeout=CONNECTIVITY_TIMEOUT) as resp:
                return resp.status == 204
        except Exception:
            return False

    async def _canary_tcp(self, host, port):
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=CONNECTIVITY_TIMEOUT,
            )
        except Exception:
            return False

        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True

    async def _async_refresh_certificates(self):
        """Fetch certificate expiry info for HTTPS services (cached)."""
        stale = []
        for service in self.services:
            if service["type"] != "https":
                continue
            cached = self.cert_data.get(service["id"])
            if cached:
                try:
                    checked_at = datetime.fromisoformat(cached["checked_at"])
                except (KeyError, ValueError):
                    checked_at = None
                if checked_at and (datetime.now(UTC) - checked_at).total_seconds() < CERT_EXPIRY_CACHE:
                    continue
            stale.append(service)

        if not stale:
            return

        await asyncio.gather(*(self._async_fetch_certificate(s) for s in stale))

    async def _async_fetch_certificate(self, service: dict) -> None:
        """Connect with TLS verification ON and read the certificate."""
        host = service["host"]
        hostname = _socket_host(host)

        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(
                    hostname,
                    service["port"],
                    ssl=ssl.create_default_context(),
                    server_hostname=hostname,
                ),
                timeout=CONNECTIVITY_TIMEOUT,
            )
        except Exception as e:
            _LOGGER.debug("Certificate check failed for %s:%s: %s", host, service["port"], e)
            self.cert_data[service["id"]] = {
                "error": f"certificate check failed: {e}",
                "checked_at": datetime.now(UTC).isoformat(),
            }
            return

        try:
            ssl_object = writer.get_extra_info("ssl_object")
            cert = ssl_object.getpeercert() if ssl_object else None
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

        info = parse_peer_cert(cert or {})
        if info is None:
            _LOGGER.debug("No certificate information received from %s:%s", host, service["port"])
            self.cert_data[service["id"]] = {
                "error": "no certificate information received",
                "checked_at": datetime.now(UTC).isoformat(),
            }
            return

        self.cert_data[service["id"]] = info
        _LOGGER.debug("Certificate for %s expires at %s", host, info["expires_at"])

    async def check_http(self, session, service: dict, attempts=None):
        host = service["host"]
        proto = service["type"]
        port = service["port"]
        keyword = service["keyword"]
        max_attempts = attempts or self.retries

        for attempt in range(max_attempts):
            timestamp = int(datetime.now(UTC).timestamp())

            # Build URL with optional port
            if port:
                url = f"{proto}://{host}:{port}?t={timestamp}"
            else:
                url = f"{proto}://{host}?t={timestamp}"

            start = datetime.now(UTC)

            headers = {
                "User-Agent": "HomeAssistant-DomainMonitor/2.0",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache"
            }

            try:
                async with session.get(url, timeout=self.timeout, headers=headers) as resp:
                    status = "down"

                    if resp.status < 400:
                        status = "up"

                        if keyword:
                            # Cap the body size and run the regex in an
                            # executor: a pathological pattern must not block
                            # the event loop (ReDoS) or exhaust memory.
                            body = await resp.content.read(KEYWORD_MAX_BODY_BYTES)
                            content = body.decode("utf-8", "ignore")
                            try:
                                found = await self.hass.async_add_executor_job(
                                    partial(re.search, keyword, content, re.IGNORECASE | re.DOTALL)
                                )
                                if not found:
                                    status = "down"
                                    _LOGGER.debug("Regex '%s' not found in response from %s", keyword, host)
                            except re.error as e:
                                _LOGGER.error("Invalid Regex '%s' for host %s: %s", keyword, host, e)
                                status = "down"

                    response_ms = (datetime.now(UTC) - start).total_seconds() * 1000
                    result = {
                        "host": host,
                        "type": proto,
                        "port": port,
                        "status": status,
                        "code": resp.status,
                        "response_ms": response_ms,
                        "slow": status == "up" and self.slow_threshold > 0 and response_ms > self.slow_threshold,
                        "time": start
                    }
                    if status == "up":
                        return result

            except Exception as e:
                _LOGGER.debug("Error checking %s (attempt %d/%d): %s", host, attempt + 1, max_attempts, e)
                result = {
                    "host": host,
                    "type": proto,
                    "port": port,
                    "status": "down",
                    "code": None,
                    "response_ms": None,
                    "slow": False,
                    "time": start
                }

            if attempt < max_attempts - 1:
                await asyncio.sleep(1)

        return result

    async def check_tcp(self, service: dict, attempts=None):
        host = _socket_host(service["host"])
        port = service["port"]
        max_attempts = attempts or self.retries

        for attempt in range(max_attempts):
            start = datetime.now(UTC)

            try:
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port),
                    timeout=self.timeout,
                )
            except Exception as e:
                _LOGGER.debug("Error checking TCP %s:%s (attempt %d/%d): %s", host, port, attempt + 1, max_attempts, e)
                result = {
                    "host": service["host"],
                    "type": "tcp",
                    "port": port,
                    "status": "down",
                    "code": port,
                    "response_ms": None,
                    "slow": False,
                    "time": start
                }

            else:
                response_ms = (datetime.now(UTC) - start).total_seconds() * 1000
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass

                return {
                    "host": service["host"],
                    "type": "tcp",
                    "port": port,
                    "status": "up",
                    "code": port,
                    "response_ms": response_ms,
                    "slow": self.slow_threshold > 0 and response_ms > self.slow_threshold,
                    "time": start
                }

            if attempt < max_attempts - 1:
                await asyncio.sleep(1)

        return result
