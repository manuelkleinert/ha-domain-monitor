# Domain Monitor (HACS)

Monitor HTTP, HTTPS, and TCP availability of domains and services inside Home Assistant — with internet-outage awareness, TLS certificate expiry tracking, uptime statistics, and more.

## Install
Add as a custom repository in HACS.

## Configuration
This integration is configured via the Home Assistant UI. Go to **Settings -> Devices & Services -> Add Integration** and search for "Domain Monitor".

During setup, you can configure:
- **Host**: The domain name or IP address to check (e.g., `google.com`, bracketed IPv6 like `[::1]` also works)
- **Type**: Choose between HTTPS, HTTP, or TCP checks
- **Port**: Optional. Automatically defaults to 443 for HTTPS and 80 for HTTP, or you can enter a custom port.
- **Keyword**: Optional (HTTP/HTTPS only). A Regex keyword to search for in the response body to determine if the service is functioning correctly.
- **Interval**: Frequency of checks in seconds.
- **Timeout**: Timeout for each check in seconds.
- **Retries**: Number of retries before marking the service as down.
- **Slow threshold**: Optional. If a healthy response takes longer than this many milliseconds, the result is flagged as `slow` (0 = disabled).

One config entry can monitor **multiple services** — manage them via the entry's options (gear icon): the options dialog opens with a menu (**Settings** for interval/timeout/retries/slow threshold, **Manage services** to add, edit, or delete services from a list with buttons). All entities of an entry are grouped under a single device.

## Entities per service
- **Status sensor** (`up`/`down`/`unknown`) with `uptime_percent` attribute
- **Response Time sensor** (ms, `duration` device class — graphable, long-term statistics)
- **Connected binary sensor** (`CONNECTIVITY`) for direct on/off automations
- **Certificate sensor** (HTTPS only): days until the TLS certificate expires, with `expires_at`, `issuer` and `subject` attributes
- **Monitor switch**: pause/resume checking of an individual service (the paused state survives HA restarts)
- **Check Now button**: trigger an immediate refresh

Plus per entry: Interval / Timeout / Retries / Slow threshold number entities, and one global **Overall Domain Status** binary sensor spanning ALL entries.

## Features
- **UP/DOWN Status**: Real-time status of your domains and services.
- **Internet outage aware**: Before a server is marked `down`, Home Assistant verifies its own connectivity via lightweight canary checks (HTTP 204 endpoints + TCP check to `1.1.1.1:443`). Without internet, services show `unknown` (attribute `no_internet: true`) instead of `down` — no false alarms in your automations.
- **Uptime Percentage**: Attribute on each status sensor, calculated from the last 100 checks.
- **TLS Certificate Monitoring**: HTTPS services report the days until their certificate expires — catch an expiring certificate before it breaks your site.
- **Slow detection**: Responses slower than the configured threshold are flagged (`slow: true`).
- **Status change events**: The integration fires `domain_monitor_event` on the event bus whenever a service changes status — more reliable for automations than state triggers.

### Example: status change automation
```yaml
automation:
  - alias: "Notify on service down"
    trigger:
      - platform: event
        event_type: domain_monitor_event
    condition:
      - condition: template
        value_template: "{{ trigger.event.data.new_status == 'down' }}"
    action:
      - service: notify.persistent_notification
        data:
          title: "Service down: {{ trigger.event.data.host }}"
          message: "{{ trigger.event.data.old_status }} -> {{ trigger.event.data.new_status }}"
```

### Example: certificate expiry warning
```yaml
automation:
  - alias: "Warn before certificate expires"
    trigger:
      - platform: numeric_state
        entity_id: sensor.example_com_https_443_certificate  # replace with your entity id
        below: 14
    action:
      - service: notify.persistent_notification
        data:
          title: "Certificate of example.com expires soon"
          message: "Only {{ states('sensor.example_com_https_443_certificate') }} days left!"
```

## Internet outage behavior
- Before a failed check marks a server as `down`, Home Assistant verifies its own connectivity via canary checks (HTTP 204 endpoints + TCP checks to `1.1.1.1:443` and `8.8.8.8:443`). Without internet, services show `unknown` (attribute `no_internet: true`) instead of `down` — no false alarms in your automations.
- While the outage lasts, monitored hosts are still checked with a single attempt per cycle (no retries burned) — so the integration recovers immediately and can never get stuck, even if the canary endpoints themselves are blocked (e.g. by ad blockers/DNS filtering).
- The overall sensor stays `on` and exposes `internet_connected: false` and `unknown_hosts` attributes.

## Diagnostics
"Download diagnostics" on the device page returns the configuration (keyword regexes redacted), current results and certificate info — handy for issue reports.

## Migration from 1.x
Version 2.0 migrates existing entries automatically (service strings become structured JSON). Because of the new stable entity IDs, previously customized entities are re-created once — re-apply any dashboard customizations after updating.
