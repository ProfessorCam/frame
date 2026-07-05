using System.IO;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using Wpeek.Capture;

namespace Wpeek.Encoding;

/// <summary>
/// Animated GIF encoder built entirely on in-box WPF imaging. WPF's
/// <see cref="GifBitmapEncoder"/> writes frames but omits the loop marker and
/// per-frame delays, so we post-process the byte stream to add both.
/// </summary>
public sealed class GifEncoder : IEncoder
{
    private readonly string _path;
    private readonly GifBitmapEncoder _gif = new();
    private int _fps = 30;

    public bool NeedsConvertNotice => true;

    public GifEncoder(string path) => _path = path;

    public void Begin(int width, int height, int fps) => _fps = Math.Clamp(fps, 5, 50);

    public void AddFrame(Frame frame)
    {
        var src = BitmapSource.Create(
            frame.Width, frame.Height, 96, 96, PixelFormats.Bgra32, null,
            frame.Bgra, frame.Width * 4);
        src.Freeze();
        _gif.Frames.Add(BitmapFrame.Create(src));
    }

    public string Finish()
    {
        using var ms = new MemoryStream();
        _gif.Save(ms);
        byte[] patched = GifPatcher.AddLoopAndDelays(ms.ToArray(), DelayCentiseconds(_fps));
        Directory.CreateDirectory(Path.GetDirectoryName(_path)!);
        File.WriteAllBytes(_path, patched);
        return _path;
    }

    public void Abort() { /* nothing persisted until Finish */ }

    // GIF delay granularity is 1/100 s; clamp so it stays >= 1.
    private static int DelayCentiseconds(int fps) => Math.Max(1, (int)Math.Round(100.0 / fps));
}

/// <summary>
/// Rewrites a GIF89a byte stream to (1) insert a NETSCAPE2.0 infinite-loop
/// application extension and (2) set the delay on every Graphic Control
/// Extension. Walks the real block structure; on any malformed input it
/// returns the original bytes unchanged (a non-looping GIF beats a corrupt one).
/// </summary>
internal static class GifPatcher
{
    public static byte[] AddLoopAndDelays(byte[] gif, int delayCs)
    {
        try
        {
            using var outMs = new MemoryStream(gif.Length + 32);
            int p = 0;

            // Header (6) + Logical Screen Descriptor (7)
            if (gif.Length < 13 || gif[0] != (byte)'G' || gif[1] != (byte)'I' || gif[2] != (byte)'F')
                return gif;
            outMs.Write(gif, 0, 13);
            byte packed = gif[10];
            p = 13;

            // Global Color Table, if present
            if ((packed & 0x80) != 0)
            {
                int gctSize = 3 * (1 << ((packed & 0x07) + 1));
                if (p + gctSize > gif.Length) return gif;
                outMs.Write(gif, p, gctSize);
                p += gctSize;
            }

            // NETSCAPE2.0 loop extension (loop forever)
            outMs.Write(new byte[]
            {
                0x21, 0xFF, 0x0B,
                (byte)'N', (byte)'E', (byte)'T', (byte)'S', (byte)'C', (byte)'A', (byte)'P', (byte)'E',
                (byte)'2', (byte)'.', (byte)'0',
                0x03, 0x01, 0x00, 0x00, 0x00
            }, 0, 19);

            // Walk the remaining blocks
            while (p < gif.Length)
            {
                byte b = gif[p];
                if (b == 0x3B) // Trailer
                {
                    outMs.WriteByte(b);
                    p++;
                    break;
                }
                if (b == 0x21) // Extension
                {
                    byte label = gif[p + 1];
                    if (label == 0xF9) // Graphic Control Extension — rewrite delay
                    {
                        // 0x21 0xF9 0x04 packed delayLo delayHi transIdx 0x00
                        outMs.WriteByte(0x21); outMs.WriteByte(0xF9); outMs.WriteByte(0x04);
                        outMs.WriteByte(gif[p + 3]);                    // disposal/packed
                        outMs.WriteByte((byte)(delayCs & 0xFF));        // delay low
                        outMs.WriteByte((byte)((delayCs >> 8) & 0xFF)); // delay high
                        outMs.WriteByte(gif[p + 6]);                    // transparent index
                        outMs.WriteByte(0x00);                          // block terminator
                        p += 8;
                    }
                    else // copy other extensions verbatim (header + data sub-blocks)
                    {
                        outMs.WriteByte(gif[p]); outMs.WriteByte(gif[p + 1]);
                        p += 2;
                        p = CopySubBlocks(gif, p, outMs);
                    }
                }
                else if (b == 0x2C) // Image Descriptor
                {
                    outMs.Write(gif, p, 10);
                    byte imgPacked = gif[p + 9];
                    p += 10;
                    if ((imgPacked & 0x80) != 0) // Local Color Table
                    {
                        int lctSize = 3 * (1 << ((imgPacked & 0x07) + 1));
                        outMs.Write(gif, p, lctSize);
                        p += lctSize;
                    }
                    outMs.WriteByte(gif[p]); // LZW minimum code size
                    p++;
                    p = CopySubBlocks(gif, p, outMs);
                }
                else
                {
                    // Unknown byte — bail out safely
                    return gif;
                }
            }
            return outMs.ToArray();
        }
        catch
        {
            return gif;
        }
    }

    // Copies a run of data sub-blocks (length-prefixed) including the 0x00 terminator.
    private static int CopySubBlocks(byte[] gif, int p, Stream outMs)
    {
        while (p < gif.Length)
        {
            byte len = gif[p];
            outMs.WriteByte(len);
            p++;
            if (len == 0) break;      // terminator
            outMs.Write(gif, p, len);
            p += len;
        }
        return p;
    }
}
