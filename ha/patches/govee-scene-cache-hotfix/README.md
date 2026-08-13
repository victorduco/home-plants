# Govee scene-cache startup hotfix

This overlay is pinned to the audited Govee integration `v2026.7.8` files in
Home Assistant Core `2026.8.1`. It keeps dynamic scenes, effects, and DIY scenes
enabled while bounding each complete catalogue fetch (including client retries)
to 15 seconds.

The cache manager now:

- shares one task per device and catalogue type;
- awaits that task through `asyncio.shield()`, so cancelling one entity setup
  cannot cancel the fetch used by other entities;
- removes an in-flight entry only from its task's identity-checked done callback;
- returns an existing stale value after a timeout without replacing its value or
  timestamp;
- cancels and awaits all scene tasks before the coordinator closes the API client.

## Validate without changing Home Assistant

```sh
bash ha/patches/govee-scene-cache-hotfix/apply.sh --check hassio@192.168.1.151
```

`--check` streams the two current files over SSH read-only, verifies their audited
SHA-256 values, stages the overlay locally, applies `coordinator.patch`, and
compiles both staged modules. It performs no remote writes.

## Apply

```sh
bash ha/patches/govee-scene-cache-hotfix/apply.sh --apply hassio@192.168.1.151
```

The apply mode repeats all checks, uploads into a temporary directory under the
integration, rechecks source and uploaded checksums, creates timestamped backups,
and atomically renames both files. A commit error restores either replaced file.
It deliberately does not reload the integration or restart Home Assistant.

The command prints the two backup paths. Restore those copies if the hotfix must
be rolled back, then restart or reload the integration at a separately chosen
time.

## Isolated regression test

```sh
python3.13 -m unittest discover -s tests -p 'test_govee_scene_cache_hotfix.py' -v
```

The test imports the overlay with lightweight API/model stubs; Home Assistant and
the installed custom integration are not touched.
