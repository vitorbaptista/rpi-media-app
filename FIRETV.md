# Fire TV control via adb

Reference notes for controlling the Fire TV Cube on the local network via `adb`.
Written after a discovery session; intended to shortcut future implementation work.

## Target device

- Model: Fire TV Cube 3rd gen (`AFTGAZL`), Fire OS 7 / Android 9.
- Locale observed: `pt_BR`.
- Advertises as `Fire TV Cube de VITOR` via mDNS service type `amzn.dmgr`.
- IP is DHCP-assigned — always re-resolve, never hardcode.

## Host requirements

- `android-tools` (provides `adb`).
- `avahi` (for `avahi-browse`) — to rediscover the IP.
- `nmap` — optional, for port probing.

## Discovery

```bash
# Resolve current IP via mDNS (one-shot)
avahi-browse -artp 2>/dev/null | awk -F';' '/Fire TV/ && /^=/ {print $8; exit}'

# Confirm adb is reachable (port 5555 must be open)
nmap -Pn -p 5555 <ip>
```

If port 5555 is closed, ADB debugging is off on the device:
Settings → My Fire TV → Developer options → **ADB debugging: ON**.
If "Developer options" is hidden: Settings → My Fire TV → About → tap **Build/Serial** 7 times.

## Connection

```bash
adb connect <ip>:5555
```

First connection shows an **"Allow USB debugging?"** prompt on the TV screen — must be approved physically (check "Always allow from this computer" to make it persistent). State progression: `unauthorized` → `device`.

## Prime Video architecture on this Cube

Critical finding: **there is no standalone Prime Video app** (`com.amazon.avod` is not installed). Prime Video is integrated into the Fire TV launcher/UI:

- Package: `com.amazon.firebat`
- Playback activity: `com.amazon.pyrocore.IgnitionActivity`

This is the component to target for all deep-link operations.

## Deep-link URL scheme

`IgnitionActivity`'s registered intent filters (from `dumpsys package com.amazon.firebat`):

| Scheme | Authorities | Paths |
|---|---|---|
| `https` | `watch.amazon.com`, `watch.amazon.co.uk`, `watch.amazon.co.de`, `watch.amazon.co.jp`, `app.primevideo.com` | GLOB `/detail`, `/collections`, `/landing`, `/search`, `/settings` |
| `amzn` | `avod`, `pvde`, `firebat`, `sunrise` | (any) |

GLOB `/detail` is an **exact-string** match. URLs like `/detail/<id>/...` do NOT match — the ID must be in the query string:

**Canonical format:**
```
https://watch.amazon.com/detail?gti=<GTI>
```

`www.primevideo.com` is NOT a registered authority — those URLs open in the Silk browser instead of native playback.

## ID formats — critical distinction

Prime Video content has two different identifier encodings that are NOT interchangeable:

| Format | Example | Where it appears |
|---|---|---|
| **pvid** (26-char) | `0GNL3V4ANLKWX6KOB7JIWJ11KB` | `primevideo.com/detail/<pvid>/` public URLs |
| **GTI** (UUID) | `amzn1.dv.gti.c8fa075a-411d-4a3a-bdf1-ec82a888c1db` | `watch.amazon.com/detail?gti=<GTI>` deep links; page metadata |

Using a pvid where a GTI is expected → **error 5004** ("content not available / invalid ID") on the TV.

### Extracting the GTI from a pvid URL

The GTI is embedded in the HTML metadata of the public detail page. Fetch and parse:

```bash
# Conceptual — in practice use WebFetch / curl + regex
curl -sL 'https://www.primevideo.com/detail/<pvid>/' \
  | grep -oE 'amzn1\.dv\.gti\.[0-9a-f-]{36}' | sort -u
```

For a TV series detail page, multiple GTIs are returned (series-level + one per episode). The page HTML identifies which is which by context (episode number/title near each GTI).

## Playback recipe

The Prime Video app **does not expose a public "play" URL**. The `Play` button triggers an internal call, not an intent. A deep link to `/detail?gti=<GTI>` only opens the detail page — `autoplay=1` is silently ignored.

Workaround: deep-link to detail, then simulate pressing the Play button (which is already focused when the page loads).

```bash
IP=<fire-tv-ip>
GTI=amzn1.dv.gti.<uuid>

adb -s "$IP:5555" shell am force-stop com.amazon.firebat
adb -s "$IP:5555" shell am start \
  -n com.amazon.firebat/com.amazon.pyrocore.IgnitionActivity \
  -a android.intent.action.VIEW \
  -d "https://watch.amazon.com/detail?gti=$GTI"
sleep 6
adb -s "$IP:5555" shell input keyevent KEYCODE_DPAD_CENTER
```

Notes:
- `force-stop` is needed when switching titles — otherwise the running instance may ignore or misinterpret a new intent.
- The 6-second sleep is a network-dependent guess. Tune per environment. Too short → keyevent fires before the Play button is focused.
- For a show's detail page, Play resumes the "next up" episode as determined by the user's watch history — not necessarily the GTI you passed if the GTI refers to the series. Always use the **episode-level GTI** for precise targeting.

## End-to-end flow

Given a user-provided `primevideo.com/detail/<pvid>` share URL:

1. Fetch the page, extract all GTIs with context.
2. Pick the episode GTI that matches the user's intent.
3. Run the playback recipe above with that GTI.

## Known limitations

- **No public playback URL.** Only detail-page deep-links exist; the Play button must be simulated.
- **No GTI in logcat.** Prime Video zeroes out `title`/`mediaId` in MediaSession broadcasts, so you cannot reverse-engineer the currently-playing GTI from the device.
- **Switching between titles requires force-stop.** Delivering a new VIEW intent to a running IgnitionActivity often doesn't trigger navigation.
- **pvid ↔ GTI conversion requires a network fetch.** There's no offline mapping; the GTI has to come from the detail page HTML (or a catalog API if we ever add one).
- **autoplay/resume query params are ignored** on this Cube / Fire OS version.

## Useful one-off commands

```bash
# Current foregrounded activity
adb shell dumpsys activity activities | grep -m1 ResumedActivity

# Probe which app handles a given URL
adb shell cmd package query-activities -a android.intent.action.VIEW -d '<url>'

# Full filter inspection for a component
adb shell dumpsys package com.amazon.firebat | grep -A 10 'IgnitionActivity filter'

# Stream logs filtered for playback events
adb logcat -v time | grep -iE 'MediaCodec|Ignition|IntentSupporter'

# Send common remote-control inputs
adb shell input keyevent KEYCODE_DPAD_CENTER      # Enter/select
adb shell input keyevent KEYCODE_MEDIA_PLAY_PAUSE # Play/pause toggle
adb shell input keyevent KEYCODE_BACK             # Back
adb shell input keyevent KEYCODE_HOME             # Home
```

## YouTube

Preinstalled YouTube app (Amazon's Cobalt-based client):

- Package: `com.amazon.firetv.youtube`
- Activity: `dev.cobalt.app.MainActivity`
- Intent filters: `https`/`http`/`youtube` schemes on `youtube.com`, `www.youtube.com`, `m.youtube.com`, `youtu.be`, `search`, `play` — GLOB path `.*` (any path).

Unlike Prime Video, **YouTube auto-plays from a deep link** — no keyevent workaround needed. Standard watch URLs work directly:

```bash
adb -s "$IP:5555" shell am force-stop com.amazon.firetv.youtube
adb -s "$IP:5555" shell am start \
  -n com.amazon.firetv.youtube/dev.cobalt.app.MainActivity \
  -a android.intent.action.VIEW \
  -d "https://www.youtube.com/watch?v=<video-id>"
```

## Netflix

Preinstalled Netflix app:

- Package: `com.netflix.ninja`
- Activity: `com.netflix.ninja.MainActivity`
- Intent filters (relevant subset): `http`/`https` on `www.netflix.com` with GLOB paths `/watch.*`, `/title.*`, `/browse`, `/home`, `/deeplink.*`; also the `nflx://` scheme.

### Profile-picker trap (the obvious recipe does NOT work)

The naive `am start -a VIEW -d https://www.netflix.com/watch/<id>` opens Netflix but lands on the profile picker; selecting a profile then drops the deep-link URL and lands on the home screen. `onNewIntent` delivery after profile selection is silently ignored by MainActivity. Force-stopping and re-launching restarts the cycle.

### Working recipe (bypasses profile picker)

Use Netflix's internal `netflix://title/<id>` URI **plus** the Amazon Fire-TV catalog extra `amzn_deeplink_data`. This takes a privileged code path inside the app that selects the last-used profile silently and navigates straight to the title.

```bash
IP=192.168.15.174
NETFLIX_ID=81629410

adb -s "$IP:5555" shell am force-stop com.netflix.ninja
sleep 2
adb -s "$IP:5555" shell am start \
  -n com.netflix.ninja/.MainActivity \
  -a android.intent.action.VIEW \
  -d "netflix://title/$NETFLIX_ID" \
  -f 0x10000020 \
  -e amzn_deeplink_data "$NETFLIX_ID"
```

Flag breakdown (`0x10000020`):

| Bit | Flag | Why it matters |
|---|---|---|
| `0x10000000` | `FLAG_ACTIVITY_NEW_TASK` | Required when starting from outside an activity context. |
| `0x00000020` | `FLAG_INCLUDE_STOPPED_PACKAGES` | Allows the intent to reach the app after `force-stop` (which puts it in the "stopped" state). Without this, force-stopped packages filter out incoming intents. |

Other details:
- The `sleep 2` between force-stop and start is load-bearing — without it, Netflix sometimes ignores the intent (presumably the process isn't fully torn down yet).
- The Netflix ID in the URL path is the public `netflix.com/watch/<id>` ID — no translation step needed.
- Requires a signed-in Netflix account with an available profile; title must be available in the account's region.

### Critical gotcha: "brought to the front"

If the target app is already running in the background, `am start` without a prior `force-stop` will print:

```
Warning: Activity not started, its current task has been brought to the front
```

…and the new URL is **ignored** — Android just surfaces the existing task in whatever state it was. **Always `force-stop` the target package before re-launching with a new URL.** This applies to both firebat and the YouTube app (and presumably every other media app).

## Things not yet explored

- `amzn://avod/...` and `amzn://pvde/...` internal URI paths — may support a direct playback form that bypasses the Play-button workaround.
- Catalog Integration API — Amazon's documented mechanism for partner apps to publish content to Fire TV; might yield an authenticated deep-link format that auto-plays.
- Alexa-over-adb — the Cube has Alexa onboard; voice commands trigger playback. Capturing that flow may reveal the true internal playback intent.
- Netflix and other streaming apps — each has its own deep-link scheme; not investigated.
- Installing a sideloaded custom player (VLC, Kodi) and using it to play local/HTTP video via `file://` and `http://` URIs — the native Fire OS ships only `com.amazon.dummy.gallery` as a `video/mp4` handler, so a third-party player is required for non-Prime video.
