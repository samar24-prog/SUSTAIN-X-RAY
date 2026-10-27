# Live demo simulator

Start the frontend/backend with the README's local run commands, then select **Live simulator** in the sidebar. Click **Start / resume**. The backend independently generates seven channels every 1–30 seconds (default 3 seconds); the UI polls every 1.5 seconds. It continues while navigating other pages. Pause before selecting a different scenario or changing assumptions.

## Scenarios
- Normal: 120 kW baseline with a small sinusoidal variation and seeded noise; 60 L/min RO feed, 65% product and 35% reject by default.
- Electricity spike: multiplies synthetic load by 1.8. A demo rule flags >20% above configured baseline.
- RO imbalance: product falls to 50%, leaving a deliberate 15% balance gap. Demo balance rule threshold is 10%; this does not diagnose a leak.
- Sensor dropout: omits reject readings. The UI displays gaps and unavailable balance/rejection/recovery, rather than substituting zero.
- Block 1/2/3: independent hypothetical flows, not asserted to share the RO plant's plumbing.

All intervals use actual elapsed wall-clock time: kWh = average kW × seconds / 3600; litres = L/min × seconds / 60. Pause/resume excludes the pause duration. Seed controls synthetic variability, not a measured baseline. Every generated reading passes the application's Reading model, has a DEMO-prefixed channel ID, source=demo and a scenario/run source reference.

## Isolation and lifecycle
No generated values are written to bills, readings, alerts or verification collections. The simulator owns a thread-safe in-memory ring buffer of 240 frames (maximum 1,680 reading records), with the latest 60 frames charted. It is shared by all users of one backend process. Restart clears it; it never auto-starts on server boot. Run **one backend worker** for this local demo. Multiple workers would have independent buffers; use a shared simulator service/state before horizontally scaling.

The UI shows current settings, timestamps, paused/streaming/stale status and connection errors. Sample age exceeding 3 × sampling interval is stale. Viewer role may observe; operators/admins may start, pause and clear. Clearing only discards ephemeral synthetic frames. Export demo CSV to retain/import a snapshot explicitly; source=demo remains set and duplicate import rules still apply. Exported imports are not required for the live view.

## API
- GET /api/simulator — authenticated snapshot; also generates a frame if one is due, so polling keeps the stream going on serverless hosts.
- POST /api/simulator/start — operator/admin; JSON {"scenario":"normal","interval_seconds":3,"baseline_kw":120,"input_lpm":60,"seed":42}.
- POST /api/simulator/pause — stop generation, preserve buffer.
- POST /api/simulator/reset — clear buffer while paused.

This exercises live timestamps, frontend updates, missing sensors, synthetic rule detection and CSV exports. It does not connect physical meters, establish hardware compatibility, send notifications or establish real savings. Campus dashboards remain historical/manual/imported views; this dedicated page makes demo/live-hardware distinction explicit.
