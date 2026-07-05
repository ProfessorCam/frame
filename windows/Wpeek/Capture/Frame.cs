namespace Wpeek.Capture;

/// <summary>A single captured frame: top-down BGRA32 pixels + a timestamp.</summary>
public sealed class Frame
{
    public required byte[] Bgra { get; init; }   // length = Width * Height * 4
    public required int Width { get; init; }
    public required int Height { get; init; }
    public required TimeSpan Timestamp { get; init; }
}
