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
    {"type": "tcp", "host": "8.8.8.8", "port": 443},
]

# Only the first N bytes of a response body are scanned for the keyword
# regex, and the regex itself runs in an executor thread so a pathological
# pattern can never block the event loop.
KEYWORD_MAX_BODY_BYTES = 1_000_000

# Limits enforced by the config/options flow.
MIN_INTERVAL = 10
MAX_INTERVAL = 3600
MIN_TIMEOUT = 1
MAX_TIMEOUT = 60
MIN_RETRIES = 1
MAX_RETRIES = 10
MIN_SLOW_THRESHOLD = 0
MAX_SLOW_THRESHOLD = 10000
DEFAULT_SLOW_THRESHOLD = 2000

# TLS certificate expiry information is refreshed at most this often.
CERT_EXPIRY_CACHE = 12 * 3600

# Event fired on the HA event bus whenever a service changes status.
EVENT_STATUS_CHANGED = "domain_monitor_event"
