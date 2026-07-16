using System;
using System.IO;
using System.Text;
using System.Threading;
using Wpeek.Capture;
using Wpeek.Encoding;

// Exercises the real encoders using Frame's exact threading pattern:
// the encoder object is constructed on the UI/STA thread (as MainWindow.StartRecording
// does), then Begin/AddFrame/Finish are driven from a background capture thread
// (as ScreenRecorder.CaptureLoop does). This is what used to throw.
internal static class Program
{
    private static int _fail;

    [STAThread]
    private static int Main()
    {
        string dir = Path.Combine(Path.GetTempPath(), "frame-tests");
        Directory.CreateDirectory(dir);
        string gifPath = Path.Combine(dir, "test.gif");
        string mp4Path = Path.Combine(dir, "test.mp4");
        foreach (var p in new[] { gifPath, mp4Path })
            if (File.Exists(p)) File.Delete(p);

        Console.WriteLine($"UI thread = {Environment.CurrentManagedThreadId} (STA)\n");

        // Constructed here, on the UI thread — exactly as the app does.
        Drive("GIF", new GifEncoder(gifPath), gifPath);
        Drive("MP4", new Mp4Encoder(mp4Path), mp4Path);

        CheckGif(gifPath);

        Console.WriteLine(_fail == 0 ? "\nALL TESTS PASSED" : $"\n{_fail} TEST(S) FAILED");
        return _fail == 0 ? 0 : 1;
    }

    private static void Drive(string name, IEncoder enc, string path)
    {
        const int w = 64, h = 48, fps = 15;
        Exception? err = null;

        var t = new Thread(() =>
        {
            try
            {
                enc.Begin(w, h, fps);
                for (int i = 0; i < 10; i++)
                {
                    var buf = new byte[w * h * 4];
                    for (int p = 0; p < buf.Length; p += 4)
                    {
                        buf[p] = (byte)(i * 25);            // B
                        buf[p + 1] = (byte)(255 - i * 25);  // G
                        buf[p + 2] = 0x40;                  // R
                        buf[p + 3] = 0xFF;                  // A
                    }
                    enc.AddFrame(new Frame
                    {
                        Bgra = buf, Width = w, Height = h,
                        Timestamp = TimeSpan.FromMilliseconds(i * 1000.0 / fps),
                    });
                }
                enc.Finish();
            }
            catch (Exception ex) { err = ex; }
        }) { IsBackground = true, Name = "frame-capture" };

        t.Start();
        t.Join();

        if (err != null) Fail($"{name}: threw {err.GetType().Name}: {err.Message}");
        else if (!File.Exists(path)) Fail($"{name}: produced no file");
        else if (new FileInfo(path).Length < 100) Fail($"{name}: file suspiciously small");
        else Pass($"{name}: 10 frames from capture thread -> {new FileInfo(path).Length:N0} bytes");
    }

    private static void CheckGif(string path)
    {
        if (!File.Exists(path)) { Fail("GIF: file missing"); return; }
        byte[] b = File.ReadAllBytes(path);

        if (b.Length > 3 && b[0] == 'G' && b[1] == 'I' && b[2] == 'F') Pass("GIF: valid GIF magic");
        else { Fail("GIF: bad magic"); return; }

        if (Find(b, Encoding.ASCII.GetBytes("NETSCAPE2.0")) >= 0) Pass("GIF: NETSCAPE2.0 loop block present");
        else Fail("GIF: NETSCAPE2.0 loop block missing (would not loop)");

        // Every Graphic Control Extension should carry our non-zero delay.
        int gce = 0, zero = 0;
        for (int i = 0; i + 8 < b.Length; i++)
            if (b[i] == 0x21 && b[i + 1] == 0xF9 && b[i + 2] == 0x04)
            {
                gce++;
                if ((b[i + 4] | (b[i + 5] << 8)) == 0) zero++;
            }
        if (gce == 0) Fail("GIF: no Graphic Control Extensions found");
        else if (zero > 0) Fail($"GIF: {zero}/{gce} frames have a zero delay");
        else Pass($"GIF: all {gce} frames carry a non-zero delay");
    }

    private static int Find(byte[] hay, byte[] needle)
    {
        for (int i = 0; i + needle.Length <= hay.Length; i++)
        {
            bool hit = true;
            for (int j = 0; j < needle.Length; j++)
                if (hay[i + j] != needle[j]) { hit = false; break; }
            if (hit) return i;
        }
        return -1;
    }

    private static void Pass(string m) => Console.WriteLine($"  PASS  {m}");
    private static void Fail(string m) { _fail++; Console.WriteLine($"  FAIL  {m}"); }
}
