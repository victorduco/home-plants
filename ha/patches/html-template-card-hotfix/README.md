# html-template-card subscription lifecycle hotfix

This overlay is pinned to HACS
`PiotrMachowski/Home-Assistant-Lovelace-HTML-Jinja2-Template-card` `v1.0.2`
(commit `1da4df8`) as installed with Home Assistant `2026.8.1`.

The upstream card starts a new `render_template` WebSocket subscription on every
qualifying `hass` update, discards the asynchronous unsubscribe handle, and does
not clean up when the card disconnects. A cached tablet dashboard can therefore
retain thousands of server-side Jinja render trackers.

The hotfix preserves `content`, `entities`, `always_update`, `do_not_parse`,
`title`, `picture_elements_mode`, `ignore_line_breaks`, and `getCardSize()`. It
serializes the entire lifecycle instead:

- stale callbacks are invalidated synchronously with a generation token;
- a pending `subscribeMessage()` acknowledgement is awaited;
- its asynchronous unsubscribe function is then awaited;
- only after confirmed removal may a replacement subscription start;
- disconnect, connection replacement, and configuration replacement all use the
  same serialized cleanup path;
- websocket-library auto-resubscribe is disabled so a reconnect cannot restore an
  orphan after cleanup was requested while the transport was unavailable;
- rapid update triggers coalesce to the latest generation;
- subscribe and unsubscribe rejections are caught; an unconfirmed unsubscribe
  fails closed rather than permitting an overlapping tracker.

Both the plain JavaScript and `html-template-card.js.gz` must be replaced because
Home Assistant's HTTP server may choose the precompressed resource.

## Read-only compatibility check

```sh
bash ha/patches/html-template-card-hotfix/apply.sh --check hassio@192.168.1.151
```

This verifies the exact installed plain and gzip SHA-256 values, verifies that
the pinned gzip expands to the pinned JavaScript, builds and syntax-checks the
hotfix and its gzip locally, and performs no remote writes.

## Apply

```sh
bash ha/patches/html-template-card-hotfix/apply.sh --apply hassio@192.168.1.151
```

Apply uploads unprivileged artifacts to `/tmp`, repeats every source and upload
checksum under `sudo`, then copies into root-owned same-directory temporary files
before atomic renames. It preserves the original owner, group, and mode and
creates timestamped backups beside both resources. Any partial commit restores
both targets from those backups using same-directory atomic renames.

The script does not restart or reload Home Assistant and does not change the
Lovelace resource URL. Existing clients need a separately controlled cache bust
or hard reload. A later HACS update may overwrite the overlay; the exact checksum
gate intentionally refuses to patch any unreviewed version.

## Regression tests

```sh
node --test \
  tests/html_template_card_hotfix.test.mjs \
  tests/debounced_html_template_card_v3.test.mjs
```

The legacy-overlay tests use deferred subscribe acknowledgements and deferred
asynchronous unsubscribes. The v3 tests prove that the production card uses only
bounded one-shot REST renders, ignores unrelated entities, serializes in-flight
requests, enforces debounce/max-wait, and cannot create a WebSocket subscription.
