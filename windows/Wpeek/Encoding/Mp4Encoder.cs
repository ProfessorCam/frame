using System.IO;
using System.Runtime.InteropServices;
using Wpeek.Capture;
using Wpeek.Native;

namespace Wpeek.Encoding;

/// <summary>
/// H.264/MP4 encoder via the in-box Media Foundation Sink Writer. Input frames
/// are top-down BGRA (RGB32); MF transcodes to H.264. Timestamps advance one
/// frame-duration per received frame, so paused time is naturally excised.
/// </summary>
public sealed class Mp4Encoder : IEncoder
{
    private readonly string _path;
    private MF.IMFSinkWriter? _writer;
    private int _stream;
    private int _w, _h, _fps;
    private long _frameDuration;   // 100-ns units
    private long _time;
    private bool _mfStarted;

    public bool NeedsConvertNotice => false;

    public Mp4Encoder(string path) => _path = path;

    public void Begin(int width, int height, int fps)
    {
        _w = width; _h = height;
        _fps = Math.Clamp(fps, 5, 60);
        _frameDuration = MF.ONE_SECOND / _fps;

        Check(MF.MFStartup(MF.MF_VERSION, MF.MFSTARTUP_FULL));
        _mfStarted = true;

        Directory.CreateDirectory(Path.GetDirectoryName(_path)!);
        Check(MF.MFCreateSinkWriterFromURL(_path, IntPtr.Zero, IntPtr.Zero, out _writer));

        // Output: H.264
        Check(MF.MFCreateMediaType(out var outType));
        SetGuid(outType, MF.MF_MT_MAJOR_TYPE, MF.MFMediaType_Video);
        SetGuid(outType, MF.MF_MT_SUBTYPE, MF.MFVideoFormat_H264);
        SetU32(outType, MF.MF_MT_AVG_BITRATE, Bitrate(_w, _h, _fps));
        SetU32(outType, MF.MF_MT_INTERLACE_MODE, MF.MFVideoInterlace_Progressive);
        SetSize(outType, MF.MF_MT_FRAME_SIZE, _w, _h);
        SetSize(outType, MF.MF_MT_FRAME_RATE, _fps, 1);
        SetSize(outType, MF.MF_MT_PIXEL_ASPECT_RATIO, 1, 1);
        Check(_writer!.AddStream(outType, out _stream));

        // Input: RGB32 (top-down)
        Check(MF.MFCreateMediaType(out var inType));
        SetGuid(inType, MF.MF_MT_MAJOR_TYPE, MF.MFMediaType_Video);
        SetGuid(inType, MF.MF_MT_SUBTYPE, MF.MFVideoFormat_RGB32);
        SetU32(inType, MF.MF_MT_INTERLACE_MODE, MF.MFVideoInterlace_Progressive);
        SetU32(inType, MF.MF_MT_DEFAULT_STRIDE, (uint)(_w * 4));   // positive => top-down
        SetSize(inType, MF.MF_MT_FRAME_SIZE, _w, _h);
        SetSize(inType, MF.MF_MT_FRAME_RATE, _fps, 1);
        SetSize(inType, MF.MF_MT_PIXEL_ASPECT_RATIO, 1, 1);
        Check(_writer.SetInputMediaType(_stream, inType, IntPtr.Zero));

        Check(_writer.BeginWriting());

        Marshal.ReleaseComObject(outType);
        Marshal.ReleaseComObject(inType);
    }

    public void AddFrame(Frame frame)
    {
        if (_writer == null) return;
        int len = frame.Bgra.Length;

        Check(MF.MFCreateMemoryBuffer(len, out var buf));
        Check(buf.Lock(out var ptr, out _, out _));
        Marshal.Copy(frame.Bgra, 0, ptr, len);
        buf.Unlock();
        buf.SetCurrentLength(len);

        Check(MF.MFCreateSample(out var sample));
        sample.AddBuffer(buf);
        sample.SetSampleTime(_time);
        sample.SetSampleDuration(_frameDuration);
        Check(_writer.WriteSample(_stream, sample));
        _time += _frameDuration;

        Marshal.ReleaseComObject(sample);
        Marshal.ReleaseComObject(buf);
    }

    public string Finish()
    {
        if (_writer != null)
        {
            Check(_writer.DoFinalize());
            Marshal.ReleaseComObject(_writer);
            _writer = null;
        }
        if (_mfStarted) { MF.MFShutdown(); _mfStarted = false; }
        return _path;
    }

    public void Abort()
    {
        try { if (_writer != null) { Marshal.ReleaseComObject(_writer); _writer = null; } } catch { }
        try { if (_mfStarted) { MF.MFShutdown(); _mfStarted = false; } } catch { }
        try { if (File.Exists(_path)) File.Delete(_path); } catch { }
    }

    // ── helpers ───────────────────────────────────────────────────────
    private static uint Bitrate(int w, int h, int fps)
        => (uint)Math.Clamp((long)(w * h * fps * 0.12), 1_500_000, 24_000_000);

    private static void SetGuid(MF.IMFMediaType t, Guid key, Guid val)
        => Check(t.SetGuid(ref key, ref val));

    private static void SetU32(MF.IMFMediaType t, Guid key, uint v)
        => Check(t.SetUINT32(ref key, v));

    private static void SetSize(MF.IMFMediaType t, Guid key, int a, int b)
        => Check(t.SetUINT64(ref key, ((ulong)(uint)a << 32) | (uint)b));

    private static void Check(int hr)
    {
        if (hr < 0) Marshal.ThrowExceptionForHR(hr);
    }
}
