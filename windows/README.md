# Frame for Windows

A native, dependency-free port of Frame for **Windows 11** (x64). Same idea as the
Linux tool — a wide, flat, translucent macOS-style "pill" that records a screen
region to **GIF** or **MP4** — but built entirely on APIs already in Windows.

## No major dependencies

Everything the recorder needs ships with Windows:

| Concern | Mechanism (all in-box) |
|---|---|
| Screen capture | GDI `BitBlt` + cursor overlay (`user32`/`gdi32`) |
| GIF encoding | WPF `GifBitmapEncoder` + a loop/delay patch |
| MP4 (H.264) | Media Foundation Sink Writer (`mfplat`/`mfreadwrite`) |
| UI | WPF (frameless, translucent, `Topmost`) |
| Settings | JSON in `%APPDATA%\frame\config.json` |

The published binary is a **single self-contained `frame.exe`** — the .NET runtime is
bundled inside it, so the end user installs nothing.

## Build

Requires the **.NET 8 SDK** (build-time only). From this `windows/` folder:

```powershell
./build-windows.ps1
```

Output: `Wpeek/bin/Release/net8.0-windows10.0.19041.0/win-x64/publish/frame.exe`.
Copy it anywhere and run.

## Use

1. Launch **frame.exe** — the pill appears (drag it anywhere).
2. Pick **GIF** or **MP4**, a delay, and (via ⚙) cursor + frame rate.
3. Click **Record**, then drag to select a region (works across all monitors).
4. **Pause/Resume** (or `Space`), **Stop** (or `Esc`).
5. File is saved to `%USERPROFILE%\Videos\`, with **Open / Reveal / Copy path** actions.

## Notes / on-device verification

This tool was written to be self-contained and correct, but must be **built and
smoke-tested on Windows 11** (there is no Windows host in the authoring
environment). When you first build, verify in this order:

1. **App + pill UI** launch, drag, minimize/restore, format/delay/settings persistence.
2. **Region selector** rubber-band + `W×H` label; single-monitor first.
3. **Capture exclusion** — with the pill positioned over the selected region, confirm
   it does not appear in a recording, and confirm it also doesn't appear in an
   unrelated screenshot/screen-share tool (`SetWindowDisplayAffinity` in
   `MainWindow.xaml.cs` `OnSourceInitialized`). If it fails silently pre-19041, the
   pill will simply appear in captures as normal — not a hard failure.
4. **GIF** recording (the primary path) — open the result; confirm it loops and plays
   at roughly the chosen frame rate.
5. **MP4** recording — the Media Foundation Sink Writer path is the most
   interop-heavy piece. If the video is vertically flipped, flip the sign of
   `MF_MT_DEFAULT_STRIDE` in `Encoding/Mp4Encoder.cs`. If a frame is captured but
   MP4 fails, GIF remains a working fallback.
6. **Resolution cap** — record a large/near-fullscreen region in GIF at each resolution setting.
   Native on a large region will hit `GifEncoder`'s in-memory budget within roughly 5-10s (this
   is expected — that's what the resolution cap is for); 480p/720p/1080p on the same region
   should run substantially longer without erroring. Confirmed on-device: a ~1490×990 region
   failed at 5.7s at Native and ran a full 15s cleanly at 480p.
7. **Multi-monitor / mixed-DPI**: region selection assumes a uniform DPI scale; on
   mixed-DPI setups the selected rectangle may be offset — capture on a single
   display is the reliable path for v1.

## Layout

```
windows/Wpeek/
  MainWindow.xaml(.cs)     the pill (idle / recording / toast)
  RegionSelector.xaml(.cs) full-desktop drag-to-select overlay
  CountdownWindow.xaml(.cs)pre-record countdown
  Capture/ScreenRecorder   GDI capture loop + pause + orchestration
  Encoding/GifEncoder      animated GIF (loop + per-frame delays)
  Encoding/Mp4Encoder      H.264/MP4 via Media Foundation
  Native/*                 P/Invoke for GDI + Media Foundation
  Config.cs                JSON settings
```
