# Domain Monitor (HACS)

Monitor HTTP, HTTPS, and TCP availability of domains and services inside Home Assistant.

## Install
Add as a custom repository in HACS.

## Configuration
This integration is configured via the Home Assistant UI. Go to **Settings -> Devices & Services -> Add Integration** and search for "Domain Monitor".

During setup, you can configure:
- **Host**: The domain name or IP address to check (e.g., `google.com`)
- **Type**: Choose between HTTPS, HTTP, or TCP checks
- **Port**: Optional. Automatically defaults to 443 for HTTPS and 80 for HTTP, or you can enter a custom port.
- **Keyword**: Optional (HTTP/HTTPS only). A Regex keyword to search for in the response body to determine if the service is functioning correctly.
- **Interval**: Frequency of checks in seconds.
- **Timeout**: Timeout for each check in seconds.
- **Retries**: Number of retries before marking the service as down.

## Features
- **UP/DOWN Status**: Real-time status of your domains and services via binary sensors.
- **Response Time**: Track how long it takes to get a response.
- **Uptime Percentage**: Tracks the percentage of successful checks (rolling window of the last 100 checks).
- **Dynamic Configuration**: Adjust the scan interval, timeout, and retry count directly from the device dashboard using Number entities, without restarting Home Assistant.
- **Reconfigure via UI**: Update the host, type, port, or keyword seamlessly through the integration options.
- **Internet outage aware**: If Home Assistant itself has no internet connection, monitored services are reported as `unknown` (attribute `no_internet: true`) instead of `down`, so your automations do not raise false alarms.

## Internet outage behavior
Before a failed check marks a server as `down`, the integration verifies Home
Assistant's own connectivity with lightweight canary checks (HTTP 204 endpoints
such as `clients3.google.com/generate_204` and a TCP check against `1.1.1.1:443`).
If none of them succeeds, the monitored server is not the problem:

- Per-service sensors show the state `unknown` with the attribute `no_internet: true`.
- The **Overall Domain Status** sensor stays `on` and exposes the attributes
  `internet_connected: false` and `unknown_hosts`.
- While the outage lasts, only the cheap canary checks run until the internet
  is back; monitored servers are checked again automatically afterwards.

## Automation
You can easily trigger automations based on the state change of the monitored domain (e.g., when the binary sensor state changes to `off` / `down`).
