using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Windows;
using Wpeek.Encoding;
using Wpeek.Native;

namespace Wpeek.Capture;

/// <summary>
/// Region screen recorder using GDI BitBlt on a background thread. Frames are
/// pushed to a pluggable <see cref="IEncoder"/>. Pause simply stops grabbing
/// frames (the output resumes seamlessly), mirroring the Linux valve behaviour.
/// </summary>
public sealed class ScreenRecorder
{
    private readonly Int32Rect _region;      // pixels in virtual-screen space
    private readonly int _fps;
    private readonly bool _cursor;
    private readonly IEncoder _encoder;
    private readonly int _outW, _outH;       // captured/encoded size, after the resolution cap

    private Thread? _thread;
    private volatile bool _running;
    private volatile bool _paused;

    public event Action? Started;
    public event Action<string>? Finished;   // final file path
    public event Action<string>? Failed;     // error message
    public event Action? Converting;         // long finalize (e.g. GIF)

    public bool IsPaused => _paused;

    /// <param name="maxHeight">
    /// Cap the captured/encoded height to this many pixels, scaling the width to
    /// match the selection's aspect ratio (0 = record at native selection size).
    /// Downscaling happens in the capture blit itself, not as a post-process, so it
    /// also cuts the per-frame memory and CPU cost proportionally — this is the
    /// main lever for keeping a large-region GIF recording under GifEncoder's
    /// in-memory budget (see MaxBytes in GifEncoder.cs).
    /// </param>
    public ScreenRecorder(Int32Rect region, int fps, bool cursor, IEncoder encoder, int maxHeight = 0)
    {
        _region = region;
        _fps = Math.Clamp(fps, 5, 60);
        _cursor = cursor;
        _encoder = encoder;

        if (maxHeight > 0 && region.Height > maxHeight)
        {
            double scale = (double)maxHeight / region.Height;
            _outH = maxHeight;
            _outW = Math.Max(2, (int)Math.Round(region.Width * scale) & ~1);
        }
        else
        {
            _outW = region.Width;
            _outH = region.Height;
        }
    }

    public void Start()
    {
        if (_running) return;
        _running = true;
        _thread = new Thread(CaptureLoop) { IsBackground = true, Name = "frame-capture" };
        _thread.Start();
    }

    public void Pause() => _paused = true;
    public void Resume() => _paused = false;

    public void Stop() => _running = false;   // loop exits and finalizes

    private void CaptureLoop()
    {
        int w = _outW, h = _outH;
        bool scaling = w != _region.Width || h != _region.Height;
        IntPtr screenDC = IntPtr.Zero, memDC = IntPtr.Zero, dib = IntPtr.Zero, oldObj = IntPtr.Zero;
        IntPtr bits = IntPtr.Zero;

        string? donePath = null;
        string? error = null;

        try
        {
            screenDC = NativeMethods.GetDC(NativeMethods.GetDesktopWindow());
            memDC = NativeMethods.CreateCompatibleDC(screenDC);
            if (scaling) NativeMethods.SetStretchBltMode(memDC, NativeMethods.COLORONCOLOR);

            var bmi = new NativeMethods.BITMAPINFOHEADER
            {
                biSize = (uint)Marshal.SizeOf<NativeMethods.BITMAPINFOHEADER>(),
                biWidth = w,
                biHeight = -h,           // top-down
                biPlanes = 1,
                biBitCount = 32,
                biCompression = NativeMethods.BI_RGB,
            };
            dib = NativeMethods.CreateDIBSection(screenDC, ref bmi, NativeMethods.DIB_RGB_COLORS,
                                                 out bits, IntPtr.Zero, 0);
            if (dib == IntPtr.Zero || bits == IntPtr.Zero)
                throw new InvalidOperationException("Could not allocate capture buffer.");
            oldObj = NativeMethods.SelectObject(memDC, dib);

            _encoder.Begin(w, h, _fps);
            Notify(Started);

            var sw = Stopwatch.StartNew();
            long frameTicks = TimeSpan.TicksPerSecond / _fps;
            long nextTick = 0;
            int stride = w * 4;
            var buffer = new byte[stride * h];
            TimeSpan encTime = TimeSpan.Zero;  // advances only while not paused

            while (_running)
            {
                long now = sw.Elapsed.Ticks;
                if (now < nextTick)
                {
                    int sleep = (int)((nextTick - now) / TimeSpan.TicksPerMillisecond);
                    if (sleep > 1) Thread.Sleep(sleep - 1);
                    continue;
                }
                nextTick += frameTicks;
                if (_paused) continue;

                // Blit region → memory DIB, downscaling in the same pass if a
                // resolution cap is in effect.
                if (scaling)
                {
                    NativeMethods.StretchBlt(memDC, 0, 0, w, h, screenDC, _region.X, _region.Y,
                                             _region.Width, _region.Height,
                                             NativeMethods.SRCCOPY | NativeMethods.CAPTUREBLT);
                }
                else
                {
                    NativeMethods.BitBlt(memDC, 0, 0, w, h, screenDC, _region.X, _region.Y,
                                         NativeMethods.SRCCOPY | NativeMethods.CAPTUREBLT);
                }
                if (_cursor) DrawCursor(memDC, w / (double)_region.Width, h / (double)_region.Height);

                Marshal.Copy(bits, buffer, 0, buffer.Length);

                var frame = new Frame
                {
                    Bgra = (byte[])buffer.Clone(),
                    Width = w,
                    Height = h,
                    Timestamp = encTime,
                };
                _encoder.AddFrame(frame);
                encTime += TimeSpan.FromTicks(frameTicks);
            }

            // Finalize (may take a moment for GIF palette work)
            if (_encoder.NeedsConvertNotice) Notify(Converting);
            donePath = _encoder.Finish();
        }
        catch (Exception ex)
        {
            try { _encoder.Abort(); } catch { /* ignore */ }
            error = ex.Message;
        }
        finally
        {
            if (oldObj != IntPtr.Zero) NativeMethods.SelectObject(memDC, oldObj);
            if (dib != IntPtr.Zero) NativeMethods.DeleteObject(dib);
            if (memDC != IntPtr.Zero) NativeMethods.DeleteDC(memDC);
            if (screenDC != IntPtr.Zero)
                NativeMethods.ReleaseDC(NativeMethods.GetDesktopWindow(), screenDC);
        }

        // Report outside the try/catch. Raising Failed from inside the catch let a
        // UI exception escape this background thread and take the process down; an
        // exception in Finished would also have been misreported as a capture failure.
        try
        {
            if (error != null) Failed?.Invoke(error);
            else Finished?.Invoke(donePath!);
        }
        catch { /* a broken UI callback must never kill the recorder */ }
    }

    // Marshalling to the UI thread can throw; capture must not die because the UI did.
    private static void Notify(Action? handler)
    {
        try { handler?.Invoke(); } catch { /* ignore */ }
    }

    private void DrawCursor(IntPtr memDC, double scaleX, double scaleY)
    {
        var ci = new NativeMethods.CURSORINFO { cbSize = Marshal.SizeOf<NativeMethods.CURSORINFO>() };
        if (!NativeMethods.GetCursorInfo(ref ci) || ci.flags != NativeMethods.CURSOR_SHOWING)
            return;
        if (!NativeMethods.GetIconInfo(ci.hCursor, out var ii))
            return;
        try
        {
            int cw = NativeMethods.GetSystemMetrics(NativeMethods.SM_CXCURSOR);
            int ch = NativeMethods.GetSystemMetrics(NativeMethods.SM_CYCURSOR);
            int x = (int)Math.Round((ci.ptScreenPos.X - _region.X) * scaleX - ii.xHotspot * scaleX);
            int y = (int)Math.Round((ci.ptScreenPos.Y - _region.Y) * scaleY - ii.yHotspot * scaleY);
            NativeMethods.DrawIconEx(memDC, x, y, ci.hCursor,
                                     (int)Math.Round(cw * scaleX), (int)Math.Round(ch * scaleY),
                                     0, IntPtr.Zero, NativeMethods.DI_NORMAL);
        }
        finally
        {
            if (ii.hbmMask != IntPtr.Zero) NativeMethods.DeleteObject(ii.hbmMask);
            if (ii.hbmColor != IntPtr.Zero) NativeMethods.DeleteObject(ii.hbmColor);
        }
    }
}
