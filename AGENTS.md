# AGENTS.md — Notes for AI coding agents

Instructions for working on this repository. Files at the repo root (this file,
`.github/`, `README.md`, `hacs.json`, `ruff.toml`, `requirements_test.txt`,
`tests/`) are meta files: they are **not** installed into Home Assistant. Only
`custom_components/domain_monitor/` gets installed. Never put runtime code or
integration files outside `custom_components/domain_monitor/`.

## Project

Home Assistant custom integration **Domain Monitor** (HACS): monitors
HTTP/HTTPS/TCP availability of domains/services and exposes the results as
sensors. One config entry can monitor MULTIPLE services (v2); the global
binary sensor aggregates ALL entries.

- Language: Python, Home Assistant custom component, config via UI (config flow).
- `manifest.json` holds the version (e.g. `2.0.1`) — bump it for every release.
- `hacs.json` sets `homeassistant: 2024.6.0` as minimum HA version; Python 3.11+
  (the code uses `datetime.UTC`).
- CI: `.github/workflows/validate.yml` (hassfest, HACS action, ruff) and
  `test.yml` (pytest on ubuntu, Python 3.13 — HA does not install on Windows
  locally because `lru-dict` has no wheel for Python 3.13+ without a compiler).

## Data model (v2)

`entry.data["services"]` / `entry.options["services"]` is a JSON **list of
dicts** (since ConfigFlow.VERSION 2; old string entries are migrated by
`async_migrate_entry` in `__init__.py`):

```json
[{"host": "example.com", "type": "https", "port": 443, "keyword": "Welcome"},
 {"host": "nas.local", "type": "tcp", "port": 22}]
```

- `type`: `http` | `https` | `tcp`; port default 443/80 for http(s), required
  for tcp; `keyword`: optional regex (http/https only).
- Bracketed IPv6 literals (`[::1]`) are supported; bare IPv6 is not (legacy
  colon-separated strings remain parseable as fallback, but without IPv6).
- Per-service id: `host:type:port` (`service_id()` in coordinator.py) — this
  is the key for `coordinator.data`, `history`, `cert_data` and `disabled`.
- `normalize_services(raw)` returns `(services, invalid)`; invalid entries are
  collected (not silently dropped) and surfaced as a repair issue.
- Tuning lives in `entry.options`: `interval`, `timeout`, `retries`,
  `slow_threshold_ms` (options override data).

## Architecture (custom_components/domain_monitor/)

- `const.py` — all constants:
  - `DOMAIN`, `DEFAULT_SCAN_INTERVAL=60`, `TIMEOUT=10`, `DEFAULT_RETRIES=3`
  - `OVERALL_SENSOR_KEY` — key in `hass.data[DOMAIN]` for the global sensor,
    stored as `(owner_entry_id, entity)`
  - `CONNECTIVITY_CHECKS` / `CONNECTIVITY_TIMEOUT=5` — canary endpoints
  - `KEYWORD_MAX_BODY_BYTES=1_000_000` — cap for regex scanning
  - `CERT_EXPIRY_CACHE=12h` — certificate probe refresh interval
  - `EVENT_STATUS_CHANGED="domain_monitor_event"` — event bus event name
  - `MIN_/MAX_INTERVAL`, `MIN_/MAX_TIMEOUT`, `MIN_/MAX_RETRIES`,
    `MIN_/MAX_SLOW_THRESHOLD`, `DEFAULT_SLOW_THRESHOLD=2000` — validation
    limits shared by `config_flow.py` and `number.py` (keep them in sync there)
- `coordinator.py` — `DomainDataCoordinator(DataUpdateCoordinator)`:
  - Created with `config_entry=entry` (required by newer HA versions).
  - `_async_update_data()` update cycle:
    1. If `_internet_ok is False` (last canary said offline): run ONLY the
       canary again. Still offline → every service gets a cheap
       `unknown`/`no_internet: true` result and the cycle ends (no timeouts,
       no retries burned). Online again → fall through to normal checks.
    2. Refresh stale certificates for HTTPS services (`_async_refresh_certificates`).
    3. Disabled services (switch off) get `unknown`/`enabled: false` without
       running checks; all others run in parallel (`asyncio.gather`).
       IMPORTANT: enabled services are collected in `task_services` alongside
       their tasks so results are paired back correctly even when a disabled
       service precedes an enabled one (a positional zip over self.services
       shifted results under wrong ids once — do not reintroduce).
    4. If any check failed → run the canary ONCE. Internet down → all failed
       results become `status="unknown"` + `no_internet: true` instead of
       `down`. Internet up → results stay `down` (server is really down).
    5. `_store()` compares old/new status per service id and fires
       `EVENT_STATUS_CHANGED` on real transitions (not on the very first
       result), appends to `self.history[sid]` (last 100 kept).
  - `internet_ok` property: `None` (never checked) / `True` / `False`.
  - `uptime_percent(sid)`: % of `up` in the last 100 history entries
    (`unknown` counts as not-up), `None` without data.
  - `set_enabled(sid, enabled)`: switch runtime toggle (no reload, not
    persisted — resets on restart); sets a disabled result and fires listeners.
  - `check_http`: GET with cache-buster `?t=<unix ts>`, no-cache headers,
    status < 400 = up, optional regex keyword check. Body is capped at
    `KEYWORD_MAX_BODY_BYTES` and the regex runs in an executor thread
    (`hass.async_add_executor_job(partial(re.search, ...))`) so a pathological
    regex can never block the event loop (ReDoS protection). Invalid regex →
    logged as error, status down. Result includes `slow` flag
    (response_ms > slow_threshold, only for up).
  - `check_tcp`: `asyncio.wait_for(asyncio.open_connection(...))`, writer is
    closed + awaited (no socket leak). Uses `get_running_loop`-safe APIs
    (no `socket.create_connection`, no `get_event_loop`). IPv6 brackets are
    stripped via `_socket_host()` for socket calls.
  - Canary: `_async_check_internet()` runs `CONNECTIVITY_CHECKS` in parallel,
    any success = online. HTTP canaries must return EXACTLY status 204 —
    a captive portal answering 200/302 therefore counts as offline.
    Endpoints: `http://clients3.google.com/generate_204`,
    `http://connectivity-check.ubuntu.com`, TCP `1.1.1.1:443`.
  - Certificates: `_async_fetch_certificate()` opens a TLS connection with
    `ssl.create_default_context()` (verification ON, `server_hostname` for
    SNI) and reads `getpeercert()`; `parse_peer_cert()` is a pure function
    (unit tested) handling BOTH RDN shapes of the `issuer`/`subject` fields;
    result cached in `cert_data[sid]` for `CERT_EXPIRY_CACHE`. Probes are
    skipped while offline. On failure an error entry
    (`{"error": ..., "checked_at": ...}`) is stored so the sensor can explain
    its unknown state (e.g. self-signed certs / IP hosts — verification stays
    ON by design).
- `sensor.py` — per service: `DomainSensor` (status + `uptime_percent`
  attribute), `DomainResponseTimeSensor` (ms, device class `DURATION`,
  `measurement`), and for HTTPS
  `DomainCertificateSensor` (days left, unit `d`, `measurement`).
  All entities **must** extend `CoordinatorEntity` (plain `Entity` froze
  states — that bug existed once, do not reintroduce).
- Entity naming/i18n: ALL entities use `_attr_has_entity_name = True` +
  `_attr_translation_key` (+ `_attr_translation_placeholders = {"host": label}`)
  — names come from the `entity.<platform>.<key>.name` sections in
  `strings.json`/`translations/*.json`. Do NOT hardcode `_attr_name` again.
- Icons: `mdi:tachometer` is REMOVED from current MDI (shows as missing icon in
  HA) — use `mdi:gauge`. That bug existed once; prefer current MDI names.
- `binary_sensor.py` — per service `DomainServiceBinarySensor`
  (CONNECTIVITY; `available` False while status unknown → no false alarms) and
  the global "Overall Domain Status" (unique_id `domain_monitor_overall_status`):
  - Created by the first entry's platform setup; stored in
    `hass.data[DOMAIN][OVERALL_SENSOR_KEY]` as `(owner_entry_id, entity)`.
  - `__init__.py` re-creates it (reload of a remaining entry) when its owner
    entry is unloaded.
  - It is a `CoordinatorEntity` of its owning coordinator and additionally
    subscribes to every OTHER coordinator in `async_added_to_hass` so any
    refresh updates it. Coordinators are found dynamically via
    `isinstance(item, DataUpdateCoordinator)` (no fragile key filtering).
  - It gets NO `device_info` on purpose: with a device it would inherit the
    device name (titled after the first service) as a prefix and read like a
    single-host sensor. Without a device the translated name is shown as-is
    (note: `translation_key` only resolves when `has_entity_name` is True —
    verified against HA 2024.6 `_name_internal`).
  - `unknown` hosts count as NOT down (no false alarms during internet outage
    or before first data); `is_on` is only False if at least one real `down`.
  - Attributes: `down_hosts`, `unknown_hosts`, `total_monitored`,
    `problem_count`, `internet_connected` (only once any canary has run).
- `switch.py` — per service a `DomainMonitorSwitch` (Monitor on/off) calling
  `coordinator.set_enabled()`; extends `RestoreEntity` so a paused service
  stays paused across HA restarts.
- `number.py` — interval/timeout/retries/slow-threshold entities
  (entity_category CONFIG); write into `entry.options`, which triggers a
  reload via `update_listener`.
- `button.py` — one "Check <service> Now" button per service
  (`CoordinatorEntity`), triggers `async_request_refresh`.
- `config_flow.py` — user flow creates an entry with one service. The
  options flow OPENS WITH A MENU (`async_show_menu`: "Settings" / "Manage
  services"; labels translated via `menu_options` in strings — HA flow forms
  cannot mix form fields and action buttons, so a checkbox was replaced by
  this menu, do not reintroduce a checkbox): "Settings" → `settings` form
  (tuning, saves immediately), "Manage services" → `manage` = BUTTON MENU
  (add/edit/delete/**settings-back**/done → label "Save") with the CURRENT
  service list rendered as Markdown in the description (`{services_list}`
  placeholder) → `edit_service`/`delete_service` (dropdown) or
  `add_service` → `service` form → back to `manage`. "Settings" returns to
  the main menu KEEPING the working copy (the dialog X always aborts the
  whole flow — that is frontend behavior and not changeable). Changes go to
  a WORKING COPY (`self._services`); nothing is saved until `done` (one
  single entry reload at the end). Shared schemas `_tuning_schema()` /
  `_service_fields_schema()` with validation: host must match
  `^[A-Za-z0-9._-]+$` or bracketed IPv6, port 1–65535, interval 10–3600,
  timeout 1–60, retries 1–10, slow threshold 0–10000.
  NEVER put pseudo entries like "+ Add"/"- Done -" into a `vol.In` dropdown —
  they cannot be translated; use menu buttons instead.
- `diagnostics.py` — `async_get_config_entry_diagnostics` with keyword
  regexes redacted (`async_redact_data`).
- `device.py` — `build_device_info(entry)`: one device per entry
  (`identifiers={(DOMAIN, entry_id)}`); used by ALL entity platforms.
- `__init__.py` — `async_migrate_entry` (v1 string → v2 JSON list, drops
  unparseable entries with warning); setup: coordinator,
  `async_config_entry_first_refresh`, forward to PLATFORMS
  `["sensor", "number", "button", "switch", "binary_sensor"]`, update
  listener (reloads entry on options change), repair issue management
  (`ir.async_create_issue` for `coordinator.invalid_services`). Unload: pop
  coordinator + delete issue; if the unloaded entry owned the global sensor,
  drop `OVERALL_SENSOR_KEY` and reload the first remaining entry so the
  global sensor is re-created there.

## Entity/unique_id scheme (v2, do not change lightly)

- All service entities: `domain_monitor_<entry_id>_<host:type:port>_<kind>`
  with kind `status`, `response_time`, `certificate`, `connected`, `monitor`,
  `check_button`
- Number: `domain_monitor_<entry_id>_<interval|timeout|retries|slow_threshold>`
- Overall binary sensor: `domain_monitor_overall_status` (changing a
  unique_id orphans the old entity in the registry — avoid unless required).
- The v2 scheme intentionally differs from v1 (host-based ids collided when
  two entries monitored the same host; that is why 2.0.0 re-creates entities).

## Security & robustness rules (keep these!)

- SSL verification stays ON (never pass `ssl=False` / `verify=False`).
- Regex keywords: always cap the body and run matching in an executor.
- Validate all user input in the flows (`vol.Match`, `vol.Range`) —
  `retries=0` would crash `check_http` with NameError, a port like 0 or
  99999 breaks aiohttp.
- Close every socket/writer you open (TCP check, canaries, cert probe).
- Never let one failed check block the whole event loop or the other checks
  (all checks run in parallel with individual timeouts).
- Config-Flow-Validierungs-Grenzen müssen zwischen `config_flow.py` und
  `number.py` übereinstimmen (deshalb stehen sie in `const.py`).

## Verification

PowerShell, repo root. Full pytest runs only in CI on Linux (HA is not
installable on this Windows machine); locally use the stubbed smoke tests:

```
python tests\smoke_local.py      # pure logic without homeassistant installed
python tests\simulate_cycle.py   # full update cycle with fake session (stubs HA)
python tests\simulate_flow.py    # options-flow editor end-to-end (stubs HA)
python -m ruff check custom_components tests
python -m py_compile (Get-ChildItem custom_components\domain_monitor -Filter *.py).FullName
python -c "import json; [json.load(open(p, encoding='utf-8')) for p in ['custom_components/domain_monitor/manifest.json','hacs.json','custom_components/domain_monitor/strings.json','custom_components/domain_monitor/translations/de.json','custom_components/domain_monitor/translations/en.json']]"
```

In CI (ubuntu): `pytest tests -v` (pytest-homeassistant-custom-component).
Test setup notes: `pytest.ini` sets `asyncio_mode = auto` (async tests run
without markers); `tests/conftest.py` puts the REPO ROOT on sys.path (do not
re-add per-file sys.path hacks — one inserted the wrong dir once and CI
failed to collect); menu steps are navigated with
`async_configure(flow_id, {"next_step_id": "step_name"})` (exactly how the
frontend sends it, verified against data_entry_flow.py 2024.6).

## Release process

1. Bump `version` in `custom_components/domain_monitor/manifest.json`.
2. Create `.github/releases/vX.Y.Z.md` with the release notes in English
   (sections: `## New`, `## Fixed`, `## Changed`).
3. Commit, push, then push the tag:
   `git tag vX.Y.Z && git push origin vX.Y.Z`
4. `.github/workflows/release.yml` automatically creates the GitHub release
   using that notes file. Do NOT create the release manually.
   The notes file must exist for the tag name before pushing the tag.

## Known quirks / open items

- `history` is keyed by service id; two services on the same host (http +
  https) each keep their own history — good — but cross-entry data is not
  shared either.
- The monitor switch is runtime-only: after an HA restart all services are
  active again (by design; document if users ask).
- `smoke_local.py` / `simulate_*.py` stub homeassistant modules — keep them
  in sync if the coordinator's or the flow's imports change.
- The options flow handler uses `self.config_entry` (framework-set property,
  HA 2024.3+) — do not go back to storing the entry in the constructor.
- The user communicates in German; release notes and code are in English.
