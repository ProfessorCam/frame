using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Wpeek;

public enum OutputFormat { Gif, Mp4 }

/// <summary>
/// JSON-backed settings, mirroring the Linux tool's config. Persisted to
/// %APPDATA%\frame\config.json. Load/save are best-effort and never throw.
/// </summary>
public sealed class Config
{
    public OutputFormat Format { get; set; } = OutputFormat.Gif;
    public int Delay { get; set; } = 0;        // 0 | 3 | 5 | 10 seconds
    public int Monitor { get; set; } = 0;      // index into screen list
    public bool Cursor { get; set; } = true;
    public int Framerate { get; set; } = 30;   // 15 | 24 | 30

    [JsonIgnore]
    public static string Dir =>
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "frame");

    [JsonIgnore]
    public static string PathOnDisk => Path.Combine(Dir, "config.json");

    private static readonly JsonSerializerOptions Opts = new()
    {
        WriteIndented = true,
        Converters = { new JsonStringEnumConverter() },
    };

    public static Config Load()
    {
        try
        {
            if (File.Exists(PathOnDisk))
            {
                var cfg = JsonSerializer.Deserialize<Config>(File.ReadAllText(PathOnDisk), Opts);
                if (cfg != null) { cfg.Normalize(); return cfg; }
            }
        }
        catch { /* fall through to defaults */ }
        return new Config();
    }

    public void Save()
    {
        try
        {
            Directory.CreateDirectory(Dir);
            File.WriteAllText(PathOnDisk, JsonSerializer.Serialize(this, Opts));
        }
        catch { /* settings are best-effort */ }
    }

    private void Normalize()
    {
        if (Delay is not (0 or 3 or 5 or 10)) Delay = 0;
        if (Framerate is not (15 or 24 or 30)) Framerate = 30;
        if (Monitor < 0) Monitor = 0;
    }
}
