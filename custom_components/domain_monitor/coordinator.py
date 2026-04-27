import aiohttp
import asyncio
from datetime import datetime, timedelta
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
import logging
import socket

from .const import DEFAULT_SCAN_INTERVAL, TIMEOUT

_LOGGER = logging.getLogger(__name__)


class DomainDataCoordinator(DataUpdateCoordinator):

    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry

        super().__init__(
            hass,
            logger=_LOGGER,
            name="domain_monitor",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

        raw = entry.options.get("services", entry.data.get("services", ""))

        self.services = []
        self.history = {}

        for item in raw.split(","):
            parts = item.strip().split(":")

            if len(parts) == 2:
                # Typ kann 'http' oder 'https' sein
                self.services.append({
                    "type": parts[1],
                    "host": parts[0]
                })

            elif len(parts) == 3:
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
                    "host": parts[0],
                    "port": port,
                })

        for s in self.services:
            self.history[s["host"]] = []

    async def _async_update_data(self):
        results = {}

        async with aiohttp.ClientSession() as session:
            tasks = []

            for s in self.services:
                if s["type"] in ["http", "https"]:
                    tasks.append(self.check_http(session, s["host"], s["type"]))

                elif s["type"] == "tcp":
                    tasks.append(self.check_tcp(s["host"], s["port"]))

            responses = await asyncio.gather(*tasks)

        for item in responses:
            host = item["host"]

            self.history[host].append(item)
            self.history[host] = self.history[host][-100:]

            results[host] = item

        return results

    async def check_http(self, session, host, proto):
        # Cache-Busting: Zeitstempel hinzufügen, um Cloudflare-Cache zu umgehen
        timestamp = int(datetime.utcnow().timestamp())
        url = f"{proto}://{host}?t={timestamp}"
        start = datetime.utcnow()

        headers = {
            "User-Agent": "HomeAssistant-DomainMonitor/1.0",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache"
        }

        try:
            async with session.get(url, timeout=TIMEOUT, headers=headers) as resp:
                return {
                    "host": host,
                    "status": "up" if resp.status < 400 else "down",
                    "code": resp.status,
                    "response_ms": (datetime.utcnow() - start).total_seconds() * 1000,
                    "time": start
                }

        except Exception:
            return {
                "host": host,
                "status": "down",
                "code": None,
                "response_ms": None,
                "time": start
            }

    async def check_tcp(self, host, port):
        start = datetime.utcnow()

        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: socket.create_connection((host, port), timeout=TIMEOUT)
            )

            return {
                "host": host,
                "status": "up",
                "code": port,
                "response_ms": (datetime.utcnow() - start).total_seconds() * 1000,
                "time": start
            }

        except Exception:
            return {
                "host": host,
                "status": "down",
                "code": port,
                "response_ms": None,
                "time": start
            }