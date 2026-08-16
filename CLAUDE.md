# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Frame: a screen-area recorder with a wide, flat, macOS-style floating "pill" controller.
Two independent, native implementations sharing one design, in the same repo:

- **Linux (GNOME Wayland)** — Python + GTK4/libadwaita, at `frame/` (the package). This is the
  primary/original implementation.
- **Windows 11** — C# / WPF, at `windows/Wpeek/`. A from-scratch port using only in-box Windows
  APIs (no Linux code is shared or ported directly — see `windows/README.md`).

Treat these as two separate codebases that happen to ship the same product design. A change to
one almost never implies a change to the other unless it's a UX/behavior change that should stay
consistent across both.

## Linux tool (`frame/`)

### Commands

```bash
./install-deps.sh                                   # Debian/Ubuntu deps (see README for Fedora)
./run.sh                                             # or: python3 -m frame
python3 -m unittest discover -s tests -p 'test_*.py' # run all tests
python3 -m unittest tests.test_pipeline              # run a single test module
./build-deb.sh 2.2.0        # .deb
./build-rpm.sh 2.2.0        # .rpm (on Fedora)
./build-appimage.sh 2.2.0   # AppImage (bundles ffmpeg)
./install-extension.sh      # install the GNOME Shell extension for the current user
```

Bump the version in `frame/__init__.py` (`__version__`) before building packages — it's shown in
the app's ⚙ settings menu and used as the build-script version arg.

### Architecture

- **`frame/app.py`** — the entire GTK4 UI: the `FrameWindow` pill (idle/recording states),
  per-monitor `SelectionWindow` overlays for drag-to-select, toasts, settings popover, and app
  entry point (`FrameApp`). Wires together config, recorder, countdown overlay, D-Bus control,
  and global shortcuts. Read this first to understand the UI flow.
- **`frame/recorder.py`** — capture backend: talks to the **Mutter ScreenCast D-Bus API** to get a
  PipeWire node for a screen region, then builds and drives a **GStreamer** pipeline
  (`build_pipeline`, a pure function — no GStreamer state touched — so it's unit-testable without
  a real display/compositor). Pause/resume works by toggling a `valve` element rather than
  stopping the pipeline, because a live `pipewiresrc` breaks EOS/finalize if you stop it. GIF
  output records to an intermediate near-lossless `.mkv` and shell-converts via `ffmpeg` afterward.
  Falls back to VP8/VP9 encoders when x264 isn't installed.
- **`frame/config.py`** — dependency-free JSON settings store at
  `~/.config/frame/config.json` (or `$XDG_CONFIG_HOME`). Validates against a whitelist per key and
  always falls back to defaults on missing/corrupt/invalid data rather than raising — never make
  this module raise on bad input.
- **`frame/dbus_control.py`** — exports `com.github.frame.Control` on the app's own session-bus
  name so external agents can drive recording without window focus. This is what the GNOME
  top-bar extension (`gnome-shell-extension/frame@professorcam.github.io/`) and global hotkeys
  talk to. All handlers run best-effort: no D-Bus connection means silent no-op, never a crash.
- **`frame/globalshortcuts.py`** — registers `Ctrl+Alt+P`/`Ctrl+Alt+S` via the
  `xdg-desktop-portal` `GlobalShortcuts` interface so pause/stop work even when the pill is
  buried behind the captured window. Skips silently if the portal doesn't implement it.
- **`frame/overlay.py`** — the on-screen countdown overlay for delayed recording starts.

Remote control (top-bar extension + hotkeys) and the in-app buttons both funnel through the same
`FrameWindow` handlers (`_remote_pause`/`_remote_stop`/etc. in `app.py`), always marshaled onto
the GTK main thread via `GLib.idle_add` — never touch GTK widgets directly from a D-Bus or
portal callback thread.

Multi-monitor selection: one `SelectionWindow` is opened per monitor (each `fullscreen_on_monitor`
pinned, each showing its own 1:1 screenshot); the first completed drag wins and the rest are
torn down (`_close_selectors`). Coordinates are converted from window-local to absolute
compositor space by adding the monitor's `(ox, oy)` offset before being handed to the recorder.

Self-capture exclusion: Wayland/Mutter has no per-window screencast-exclusion flag, so the pill
hides itself (`self.set_visible(False)` in `_cb_started`) for the duration of the actual capture
and calls `self.present()` again once the pipeline stops (`_cb_converting`/`_cb_stopped`/
`_cb_error`). This is why pause/stop must stay reachable while the window is hidden — that's what
the D-Bus control interface and global shortcuts are actually for, not just "window buried behind
the capture target".

### Tests

`tests/` covers `config.py` (settings persistence/validation), `recorder.py`'s
`build_pipeline` (pipeline string construction under different available-encoder scenarios), and
`dbus_control.py` (the D-Bus interface). There's no GUI/widget test coverage — `app.py` isn't
exercised by the test suite.

## Windows tool (`windows/Wpeek/`)

### Commands

```powershell
cd windows
./build-windows.ps1   # → Wpeek/bin/Release/net8.0-windows10.0.19041.0/win-x64/publish/frame.exe
```

Requires the .NET 8 SDK to build; the published `frame.exe` is self-contained (bundles the .NET
runtime) and needs nothing installed to run.

**No Windows host exists in the authoring environment** — this code must be built and
smoke-tested on real Windows 11 hardware before trusting a change. `windows/README.md` has the
on-device verification checklist (pill UI, region selector, GIF path, MP4 path, multi-monitor/
mixed-DPI); follow it after any change under `windows/Wpeek/`, especially anything touching
`Encoding/Mp4Encoder.cs` (Media Foundation is the most interop-heavy piece — a vertically flipped
video means flipping the sign of `MF_MT_DEFAULT_STRIDE`).

### Architecture

All in-box Windows APIs, no third-party dependencies:

- **`MainWindow.xaml(.cs)`** — the pill (idle / recording / toast), same state machine shape as
  the Linux `FrameWindow`.
- **`RegionSelector.xaml(.cs)`** — full-desktop drag-to-select overlay.
- **`CountdownWindow.xaml(.cs)`** — pre-record countdown, Linux's `overlay.py` equivalent.
- **`Capture/ScreenRecorder.cs`, `Capture/Frame.cs`** — GDI `BitBlt` capture loop with pause
  support and orchestration (Linux equivalent of `recorder.py`, but polling-based rather than a
  GStreamer pipeline).
- **`Encoding/GifEncoder.cs`** — animated GIF via WPF's `GifBitmapEncoder` plus a hand-patched
  loop/delay (WPF's encoder doesn't natively support looping GIFs).
- **`Encoding/Mp4Encoder.cs`** — H.264/MP4 via the Media Foundation Sink Writer, P/Invoked through
  `Native/MediaFoundation.cs`.
- **`Native/NativeMethods.cs`** — GDI/user32 P/Invoke declarations for capture, plus
  `SetWindowDisplayAffinity` and `StretchBlt`.
- **`Config.cs`** — JSON settings at `%APPDATA%\frame\config.json`, same role as `config.py`.

Memory budget / resolution cap: `GifEncoder` holds every decoded frame in memory (as WPF
`BitmapFrame`s inside a `GifBitmapEncoder`) until the recording stops, and throws once a memory
budget is exceeded — **confirmed by an actual on-device recording**: a near-fullscreen
(~1490×990) capture at the default 30fps used to hit a hardcoded 1.2GB cap in about 5.7 seconds.
`Mp4Encoder` doesn't have this problem — it streams each frame straight into the Media
Foundation Sink Writer instead of buffering — so this is GIF-specific. Two independent
mitigations, both confirmed on-device:

- **Dynamic memory budget** (`GifEncoder.ComputeBudget`): instead of a fixed constant, the cap is
  a conservative fraction (`AvailFraction` = 33%) of *currently available* physical RAM, queried
  fresh via `GlobalMemoryStatusEx` at the start of each recording (`NativeMethods.MEMORYSTATUSEX`
  / `GlobalMemoryStatusEx`), clamped to `[MinBudget, MaxBudget]` (500MB–8GB) so it neither starves
  a low-memory machine nor lets one recording claim unbounded RAM on a high-memory one. On this
  40GB-RAM dev machine that same ~1490×990 native-resolution recording ran a full 20s (vs. the old
  5.7s) before being manually stopped, producing a 182MB/1486×990 file successfully.
- **Resolution cap** (`ScreenRecorder`'s `maxHeight` parameter, wired to `Config.MaxHeight` / the
  ⚙ Settings "Resolution" dropdown: Native/1080p/720p/480p): when set, the capture blit itself
  downscales via `StretchBlt` (`COLORONCOLOR` mode) into a smaller DIB, so memory and CPU cost
  drop with it — a capture-time scale, not a post-encode resize. The same near-fullscreen region
  capped to 480p ran a full 15s without hitting even the old fixed budget.

These compose: the resolution cap reduces bytes/frame, the dynamic budget scales how many bytes
are allowed in total — together they're the two levers for "how long can a GIF recording run."

Self-capture exclusion: unlike Linux, Windows can exclude a specific window from screen capture
without hiding it locally. `MainWindow.OnSourceInitialized` calls
`SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)` once, permanently — the pill/toast stay
on-screen and interactive for the user but are invisible to `ScreenRecorder`'s own `BitBlt` loop
and to any other capture tool (screenshot utilities, other recorders, screen share). Requires
Windows 10 2004+ (build 19041+), which matches this app's minimum target; on older builds the
call is a silent no-op and the pill simply appears in captures as before.

Known limitation to preserve, not silently "fix": region selection assumes a single, uniform DPI
scale; mixed-DPI multi-monitor setups can select an offset rectangle. Single-display capture is
the reliable path.
