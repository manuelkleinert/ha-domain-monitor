import json
import sqlite3

db = sqlite3.connect(r"C:\Users\manue\Git\home-assistant\config\home-assistant_v2.db")

rows = db.execute(
    """
    SELECT sm.entity_id, s.state, s.attributes, s.last_updated_ts
    FROM states s
    JOIN states_meta sm ON sm.metadata_id = s.metadata_id
    WHERE sm.entity_id LIKE '%landscapehunter%'
       OR sm.entity_id LIKE '%manuelkleinert%'
       OR sm.entity_id LIKE '%gesamt%'
    ORDER BY sm.entity_id, s.last_updated_ts
    """
).fetchall()

latest = {}
for entity_id, state, attrs, ts in rows:
    latest[entity_id] = (state, attrs, ts)

for entity_id, (state, attrs, ts) in sorted(latest.items()):
    ts_str = db.execute("SELECT datetime(?, 'unixepoch')", (ts,)).fetchone()[0]
    a = json.loads(attrs) if attrs else {}
    keep = {
        k: v
        for k, v in a.items()
        if k in ("device_class", "state_class", "unit_of_measurement", "response_ms",
                 "code", "no_internet", "enabled", "uptime_percent", "days_left",
                 "expires_at", "error", "friendly_name")
    }
    print(f"{entity_id} | state={state} | {ts_str}")
    for k, v in keep.items():
        print(f"    {k} = {v}")
print(f"--- {len(latest)} Entities")
