import asyncio
from datetime import datetime, UTC, timedelta
import logging
import re

import aiohttp
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONNECTIVITY_CHECKS,
    CONNECTIVITY_TIMEOUT,
    DEFAULT_RETRIES,
    DEFAULT_SCAN_INTERVAL,
    TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)


class DomainDataCoordinator(DataUpdateCoordinator):

    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry

        self.interval = entry.options.get("interval", entry.data.get("interval", DEFAULT_SCAN_INTERVAL))
        self.timeout = entry.options.get("timeout", entry.data.get("timeout", TIMEOUT))
        self.retries = entry.options.get("retries", entry.data.get("retries", DEFAULT_RETRIES))

        # None = not checked yet, True/False = result of the last canary check
        self._internet_ok = None

        super().__init__(
            hass,
            logger=_LOGGER,
            name="domain_monitor",
            update_interval=timedelta(seconds=self.interval),
        )

        raw = entry.options.get("services", entry.data.get("services", ""))

        self.services = []
        self.history = {}

        for item in raw.split(","):
            # Nutze maxsplit=3, um host:type:port:keyword zu unterstützen
            parts = item.strip().split(":", 3)

            if len(parts) >= 2:
                host = parts[0]
                service_type = parts[1]

                if service_type in ["http", "https"]:
                    # Legacy: host:type:keyword (3 parts)
                    # New: host:type:port:keyword (4 parts)
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

                    self.services.append({
                        "type": service_type,
                        "host": host,
                        "port": port,
                        "keyword": keyword if keyword else None
                    })
                elif service_type == "tcp" and len(parts) >= 3:
                    try:
                        port = int(parts[2])
                    except ValueError:
                        _LOGGER.warning(
                            "Skipping invalid service entry (port is not a number): %s",
                            item.strip(),
                        )
                        continue
                    self.services.append({
                        "type": "tcp",
                        "host": host,
                        "port": port,
                    })

        for s in self.services:
            self.history[s["host"]] = []

    @property
    def internet_ok(self):
        """True/False from the last internet connectivity check, None if never run."""
        return self._internet_ok

    async def _async_update_data(self):
        results = {}

        # While the last canary check said there is no internet, re-run only
        # the cheap connectivity check until the internet is back instead of
        # burning through timeouts and retries on every monitored host.
        if self._internet_ok is False and not await self._async_check_internet():
            for s in self.services:
                item = self._no_internet_result(s["host"])
                self.history[s["host"]].append(item)
                self.history[s["host"]] = self.history[s["host"]][-100:]
                results[s["host"]] = item
            return results

        session = async_get_clientsession(self.hass)
        tasks = []

        for s in self.services:
            if s["type"] in ["http", "https"]:
                tasks.append(self.check_http(session, s["host"], s["type"], s.get("port"), s.get("keyword")))

            elif s["type"] == "tcp":
                tasks.append(self.check_tcp(s["host"], s["port"]))

        responses = await asyncio.gather(*tasks)

        # If any check failed, make sure Home Assistant itself can reach the
        # internet before blaming the monitored server.
        failed = [item for item in responses if item["status"] == "down"]
        if failed and not await self._async_check_internet():
            for item in failed:
                item["status"] = "unknown"
                item["no_internet"] = True

        for item in responses:
            host = item["host"]
            self.history[host].append(item)
            self.history[host] = self.history[host][-100:]
            results[host] = item

        return results

    @staticmethod
    def _no_internet_result(host):
        return {
            "host": host,
            "status": "unknown",
            "code": None,
            "response_ms": None,
            "time": datetime.now(UTC),
            "no_internet": True,
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

        self._internet_ok = any(await asyncio.gather(*tasks))
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

    async def check_http(self, session, host, proto, port=None, keyword=None):
        for attempt in range(self.retries):
            timestamp = int(datetime.now(UTC).timestamp())

            # Build URL with optional port
            if port:
                url = f"{proto}://{host}:{port}?t={timestamp}"
            else:
                url = f"{proto}://{host}?t={timestamp}"

            start = datetime.now(UTC)

            headers = {
                "User-Agent": "HomeAssistant-DomainMonitor/1.0",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache"
            }

            try:
                async with session.get(url, timeout=self.timeout, headers=headers) as resp:
                    status = "down"

                    if resp.status < 400:
                        status = "up"

                        if keyword:
                            content = await resp.text()
                            try:
                                if not re.search(keyword, content, re.IGNORECASE | re.DOTALL):
                                    status = "down"
                                    _LOGGER.debug("Regex '%s' not found in response from %s", keyword, host)
                            except re.error as e:
                                _LOGGER.error("Invalid Regex '%s' for host %s: %s", keyword, host, e)
                                status = "down"

                    result = {
                        "host": host,
                        "status": status,
                        "code": resp.status,
                        "response_ms": (datetime.now(UTC) - start).total_seconds() * 1000,
                        "time": start
                    }
                    if status == "up":
                        return result

            except Exception as e:
                _LOGGER.debug("Error checking %s (attempt %d/%d): %s", host, attempt + 1, self.retries, e)
                result = {
                    "host": host,
                    "status": "down",
                    "code": None,
                    "response_ms": None,
                    "time": start
                }

            if attempt < self.retries - 1:
                await asyncio.sleep(1)

        return result

    async def check_tcp(self, host, port):
        for attempt in range(self.retries):
            start = datetime.now(UTC)

            try:
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port),
                    timeout=self.timeout,
                )
            except Exception as e:
                _LOGGER.debug("Error checking TCP %s:%s (attempt %d/%d): %s", host, port, attempt + 1, self.retries, e)
                result = {
                    "host": host,
                    "status": "down",
                    "code": port,
                    "response_ms": None,
                    "time": start
                }

            else:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass

                return {
                    "host": host,
                    "status": "up",
                    "code": port,
                    "response_ms": (datetime.now(UTC) - start).total_seconds() * 1000,
                    "time": start
                }

            if attempt < self.retries - 1:
                await asyncio.sleep(1)

        return result
