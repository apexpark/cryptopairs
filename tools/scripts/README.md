# Scripts

Place exchange discovery, migration, and operational helper scripts here.

## Alpha Tracking

Use the alpha tracker utility to keep delivery focused:

```bash
python3 tools/scripts/alpha_tracker.py summary
python3 tools/scripts/alpha_tracker.py set-focus --id 1
python3 tools/scripts/alpha_tracker.py set-status --id 1 --status IN_PROGRESS --note "started"
python3 tools/scripts/alpha_tracker.py checkpoint --delta "implemented API skeleton" --next-action "add integration test"
python3 tools/scripts/alpha_tracker.py park --title "investigate optional chart library" --return-after-id 2
```
