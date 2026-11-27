DOMAIN = "domain_monitor"
DEFAULT_SCAN_INTERVAL = 60
TIMEOUT = 10
DEFAULT_RETRIES = 3

# Key in hass.data under which the global overall binary sensor is stored,
# together with the entry id of the coordinator it is bound to.
OVERALL_SENSOR_KEY = "overall_sensor"

# Canary checks used to detect "Home Assistant has no internet". If none of
# them succeeds, monitored servers are reported as unknown instead of down.
# The HTTP endpoints answer with status 204 when online, so a captive portal
# answering with 200/302 is not mistaken for a working connection.
CONNECTIVITY_TIMEOUT = 5
CONNECTIVITY_CHECKS = [
    {"type": "http", "url": "http://clients3.google.com/generate_204"},
    {"type": "http", "url": "http://connectivity-check.ubuntu.com"},
    {"type": "tcp", "host": "1.1.1.1", "port": 443},
]
