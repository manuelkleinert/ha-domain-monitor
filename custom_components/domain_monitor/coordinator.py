import aiohttp
import asyncio
from datetime import datetime, timedelta
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from .const import DEFAULT_SCAN_INTERVAL, TIMEOUT

class DomainDataCoordinator(DataUpdateCoordinator):

    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry

        super().__init__(
            hass,
            logger=None,
            name="domain_monitor",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

        self.domains = [
            d.strip()
            for d in entry.data.get("domains", "").split(",")
            if d.strip()
        ]

        self.history = {d: [] for d in self.domains}

    async def _async_update_data(self):
        results = {}

        async with aiohttp.ClientSession() as session:
            tasks = [self.check_domain(session, d) for d in self.domains]
            responses = await asyncio.gather(*tasks)

        for domain, result in responses:
            self.history[domain].append(result)
            self.history[domain] = self.history[domain][-100:]
            results[domain] = result

        return results

    async def check_domain(self, session, domain):
        url = f"https://{domain}"
        start = datetime.utcnow()

        try:
            async with session.get(url, timeout=TIMEOUT) as resp:
                end = datetime.utcnow()
                return domain, {
                    "status": "up" if resp.status < 400 else "down",
                    "code": resp.status,
                    "response_ms": (end - start).total_seconds() * 1000,
                    "time": start
                }
        except Exception:
            return domain, {
                "status": "down",
                "code": None,
                "response_ms": None,
                "time": start
            }
