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

    private Thread? _thread;
    private volatile bool _running;
    private volatile bool _paused;

    public event Action? Started;
    public event Action<string>? Finished;   // final file path
    public event Action<string>? Failed;     // error message
    public event Action? Converting;         // long finalize (e.g. GIF)

    public bool IsPaused => _paused;

    public ScreenRecorder(Int32Rect region, int fps, bool cursor, IEncoder encoder)
    {
        _region = region;
        _fps = Math.Clamp(fps, 5, 60);
        _cursor = cursor;
        _encoder = encoder;
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
        int w = _region.Width, h = _region.Height;
        IntPtr screenDC = IntPtr.Zero, memDC = IntPtr.Zero, dib = IntPtr.Zero, oldObj = IntPtr.Zero;
        IntPtr bits = IntPtr.Zero;

        try
        {
            screenDC = NativeMethods.GetDC(NativeMethods.GetDesktopWindow());
            memDC = NativeMethods.CreateCompatibleDC(screenDC);

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
            Started?.Invoke();

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

                // Blit region → memory DIB
                NativeMethods.BitBlt(memDC, 0, 0, w, h, screenDC, _region.X, _region.Y,
                                     NativeMethods.SRCCOPY | NativeMethods.CAPTUREBLT);
                if (_cursor) DrawCursor(memDC);

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
            if (_encoder.NeedsConvertNotice) Converting?.Invoke();
            string path = _encoder.Finish();
            Finished?.Invoke(path);
        }
        catch (Exception ex)
        {
            try { _encoder.Abort(); } catch { /* ignore */ }
            Failed?.Invoke(ex.Message);
        }
        finally
        {
            if (oldObj != IntPtr.Zero) NativeMethods.SelectObject(memDC, oldObj);
            if (dib != IntPtr.Zero) NativeMethods.DeleteObject(dib);
            if (memDC != IntPtr.Zero) NativeMethods.DeleteDC(memDC);
            if (screenDC != IntPtr.Zero)
                NativeMethods.ReleaseDC(NativeMethods.GetDesktopWindow(), screenDC);
        }
    }

    private void DrawCursor(IntPtr memDC)
    {
        var ci = new NativeMethods.CURSORINFO { cbSize = Marshal.SizeOf<NativeMethods.CURSORINFO>() };
        if (!NativeMethods.GetCursorInfo(ref ci) || ci.flags != NativeMethods.CURSOR_SHOWING)
            return;
        if (!NativeMethods.GetIconInfo(ci.hCursor, out var ii))
            return;
        try
        {
            int x = ci.ptScreenPos.X - _region.X - ii.xHotspot;
            int y = ci.ptScreenPos.Y - _region.Y - ii.yHotspot;
            NativeMethods.DrawIconEx(memDC, x, y, ci.hCursor, 0, 0, 0,
                                     IntPtr.Zero, NativeMethods.DI_NORMAL);
        }
        finally
        {
            if (ii.hbmMask != IntPtr.Zero) NativeMethods.DeleteObject(ii.hbmMask);
            if (ii.hbmColor != IntPtr.Zero) NativeMethods.DeleteObject(ii.hbmColor);
        }
    }
}
