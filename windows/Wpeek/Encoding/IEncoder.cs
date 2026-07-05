using Wpeek.Capture;

namespace Wpeek.Encoding;

/// <summary>A sink that turns captured frames into a finished file.</summary>
public interface IEncoder
{
    /// <summary>True if finishing is slow enough to warrant a "Converting…" notice.</summary>
    bool NeedsConvertNotice { get; }

    void Begin(int width, int height, int fps);
    void AddFrame(Frame frame);

    /// <summary>Finalize and return the path of the written file.</summary>
    string Finish();

    /// <summary>Best-effort cleanup after an error.</summary>
    void Abort();
}
