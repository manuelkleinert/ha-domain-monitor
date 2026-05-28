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

## Automation
You can easily trigger automations based on the state change of the monitored domain (e.g., when the binary sensor state changes to `off` / `down`).
