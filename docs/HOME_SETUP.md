# Home Assistant button setup

## Behavior and acceptance criteria

The setup panel starts unconfigured unless the running agent or the private
setup store has an actual Home Assistant configuration. Missing settings do not
prove that Home Assistant is absent from the PC. No device action is performed
during setup. The user supplies the instance address and a long-lived token,
presses Connect, then explicitly selects the lights/switches ccoli may control.
Saving selection changes the running tool client's integration immediately.

1. Open the actual Home Assistant login page and finish its own onboarding.
2. Open User profile → Security and create a long-lived access token, then paste
   it into the password field. The token is never returned by ccoli's API.
3. Connect verifies GET /api/ and fetches bounded GET /api/states metadata.
4. Select exact light/switch entity IDs and Save. Empty selection disables home
   tools. Disconnect clears the private token/configuration and runtime tools.

The token/profile flow follows the [official authentication documentation](https://www.home-assistant.io/docs/authentication/).
Verification uses Home Assistant's authenticated [REST API](https://developers.home-assistant.io/docs/api/rest/).
The address is the user's actual origin; ccoli does not assume port8123.

## Installation options

[Home Assistant OS on a Windows VM](https://www.home-assistant.io/installation/windows/)
is the official Windows path and needs bridged networking. The [Container guide](https://www.home-assistant.io/installation/linux/#install-home-assistant-container)
requires Docker Engine and explicitly excludes Docker Desktop. Container has no
HA apps and needs manual maintenance. A Windows Docker Desktop bridge deployment
is therefore an experimental option, not the official supported recommendation;
LAN multicast/USB discovery is not equivalent to HA OS. This service does not
claim installation or start any containers. A separate opt-in installer, if
provided by the host application, must report actual job/readiness evidence.

## Integration contract

`HomeAssistantSetupService(secret_path, apply_home, initial_home=None)` owns only
its private store. The host constructs it at `server/data/home-assistant-setup.json`,
excludes that path from Git and Docker, and exposes it as `agent.home_setup_service`.
The host callback updates `agent.tool_agent.home` under `_home_turn_lock`.
It must perform a reversible assignment and accept None to disable the tools.

Authenticated routes under `/api/home-setup`:

| Method/path | Input | Result |
|---|---|---|
| GET `/api/home-setup/status` (root aliases accepted) | none | sanitized status |
| POST `/connect` | base_url, optional token | verified candidates/status |
| POST `/selection` | allowed_entities exact ID array | live allow-list/status |
| POST `/disconnect` | empty object | cleared configuration/status |

Status fields: base_url, verified, active, token_present, candidates
[{entity_id,name,state}], allowed_entities, pending, state, links, steps,
error_code. Active means an actual configured runtime client; verified means a
successful server check in this process. Restored clients are explicitly
unverified until Connect succeeds. New credentials disable the old allow-list;
rechecking identical credentials preserves only currently discovered selected
IDs. Blank/omitted token is reused only for the same saved origin.

Connect snapshots a generation before network work. Disconnect, selection or a
new Connect invalidates old in-flight results. Selection requires verified
candidates. Failed verification leaves the previous committed configuration
unchanged. Runtime assignment/storage failure rolls back the previous client
and never includes exception/request/token values in the error response.

## Bounds and private data

Only fixed GET /api/ and /api/states are requested, without redirects or proxy/
netrc credentials. Timeout5s per request, total discovery deadline10s, decoded
response2MiB, states2000, candidates256, names128characters and IDs255characters.
Only light/switch IDs and on/off/unknown/unavailable states are exposed; all other
attributes are discarded. No automation/script/service endpoint is called.

Request JSON is read with a16KiB bound and an exact field schema. Duplicate keys,
invalid types, nonfinite numbers, oversized strings and unknown fields get fixed
sanitized errors rather than FastAPI validation responses containing input.
The private version1 JSON store has a128KiB bound and uses atomic replacement and restrictive file
permissions where supported. Windows access follows the user's directory ACL;
never put this file in a shared/public folder. It is neither public config YAML
nor a browser-readable secret. Malformed/symlink/oversized stores are not loaded.

Docker acceptance gate:

```bash
docker compose -p home-setup-dev -f docker/docker-compose.test.yml run --rm --build server-test pytest -q server/tests/test_home_setup.py server/tests/test_home_assistant.py
```

Tests mock network and use temporary private stores: default status, verified
fixed endpoints, allow-list/live callback, persistence/restart, redirect/auth/
response-bound failure, stale connect/disconnect, rollback, route authentication
and token-safe malformed JSON. No actual Home Assistant account/device is
configured by these tests. Real acceptance needs a user-supplied instance/token,
explicit selection, and a confirmed allowed light/switch state change.
Atomic-write temporary files use server/data/.home-setup-* and must also be
excluded from Git/Docker, including remnants after an interrupted process.

The hard discovery wall deadline includes process startup, DNS, connection,
response headers and decoded body. A fixed subprocess module entry performs only
the two authenticated read requests. The token travels only through stdin memory,
never command arguments/environment/files/logs. Bounded sanitized stdout carries
candidate metadata or a stable error code. Timeout or a changed setup generation
terminates/reaps the helper. It never imports/reexecutes a user server launcher,
so it cannot start a second voice runtime or acquire COM/GPU resources.