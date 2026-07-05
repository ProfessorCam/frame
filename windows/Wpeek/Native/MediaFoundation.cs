using System.Runtime.InteropServices;

namespace Wpeek.Native;

/// <summary>
/// Minimal Media Foundation interop for H.264/MP4 encoding via the in-box
/// Sink Writer. Only the surface the encoder needs is declared. All of this
/// ships with Windows (mfplat.dll / mfreadwrite.dll) — no external packages.
/// </summary>
internal static class MF
{
    // ── Functions ─────────────────────────────────────────────────────
    [DllImport("mfplat.dll")] public static extern int MFStartup(uint version, uint flags);
    [DllImport("mfplat.dll")] public static extern int MFShutdown();
    [DllImport("mfplat.dll")] public static extern int MFCreateMediaType(out IMFMediaType ppMFType);
    [DllImport("mfplat.dll")] public static extern int MFCreateMemoryBuffer(int cbMaxLength, out IMFMediaBuffer ppBuffer);
    [DllImport("mfplat.dll")] public static extern int MFCreateSample(out IMFSample ppIMFSample);

    [DllImport("mfreadwrite.dll")]
    public static extern int MFCreateSinkWriterFromURL(
        [MarshalAs(UnmanagedType.LPWStr)] string pwszOutputURL,
        IntPtr pByteStream, IntPtr pAttributes, out IMFSinkWriter ppSinkWriter);

    public const uint MF_VERSION = 0x00020070;              // MF_SDK_VERSION<<16 | MF_API_VERSION
    public const uint MFSTARTUP_FULL = 0;

    // 100-ns units
    public const long ONE_SECOND = 10_000_000L;

    // ── Attribute GUIDs ───────────────────────────────────────────────
    public static readonly Guid MF_MT_MAJOR_TYPE = new("48eba18e-f8c9-4687-bf11-0a74c9f96a8f");
    public static readonly Guid MF_MT_SUBTYPE = new("f7e34c9a-42e8-4714-b74b-cb29d72c35e5");
    public static readonly Guid MF_MT_AVG_BITRATE = new("20332624-fb0d-4d9e-bd0d-cbf6786c102e");
    public static readonly Guid MF_MT_INTERLACE_MODE = new("e2724bb8-e676-4806-b4b2-a8d6efb44ccd");
    public static readonly Guid MF_MT_FRAME_SIZE = new("1652c33d-d6b2-4012-b834-72030849a37d");
    public static readonly Guid MF_MT_FRAME_RATE = new("c459a2e8-3d2c-4e44-b132-fee5156c7bb0");
    public static readonly Guid MF_MT_PIXEL_ASPECT_RATIO = new("c6376a1e-8d0a-4027-be45-6d9a0ad39bb6");
    public static readonly Guid MF_MT_ALL_SAMPLES_INDEPENDENT = new("c9173739-5e56-461c-b713-46fb995cb95f");
    public static readonly Guid MF_MT_DEFAULT_STRIDE = new("644b4e48-1e02-4516-b0eb-c01ca9d49ac6");

    public static readonly Guid MFMediaType_Video = new("73646976-0000-0010-8000-00aa00389b71");
    public static readonly Guid MFVideoFormat_H264 = new("34363248-0000-0010-8000-00aa00389b71");
    public static readonly Guid MFVideoFormat_RGB32 = new("00000016-0000-0010-8000-00aa00389b71");

    public const uint MFVideoInterlace_Progressive = 2;

    // ── Helpers for packed size/ratio attributes ──────────────────────
    public static void SetSize(IMFMediaType t, Guid key, int a, int b)
        => t.SetUINT64(ref key, ((ulong)(uint)a << 32) | (uint)b);

    // ── COM interfaces ────────────────────────────────────────────────
    // IMFAttributes must declare ALL 30 methods in exact vtable order, because
    // IMFMediaType and IMFSample inherit it — any missing slot misaligns the
    // derived interfaces' methods. Unused methods are single-slot placeholders.
    [ComImport, Guid("2cd2d921-c447-44a7-a13c-4adabfc247e3"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IMFAttributes
    {
        [PreserveSig] int GetItem(ref Guid key, IntPtr value);          // 1
        [PreserveSig] int GetItemType(ref Guid key, out int pType);     // 2
        [PreserveSig] int CompareItem();                                // 3
        [PreserveSig] int Compare();                                    // 4
        [PreserveSig] int GetUINT32(ref Guid key, out uint value);      // 5
        [PreserveSig] int GetUINT64(ref Guid key, out ulong value);     // 6
        [PreserveSig] int GetDouble();                                  // 7
        [PreserveSig] int GetGuid(ref Guid key, out Guid value);        // 8
        [PreserveSig] int GetStringLength();                            // 9
        [PreserveSig] int GetString();                                  // 10
        [PreserveSig] int GetAllocatedString();                         // 11
        [PreserveSig] int GetBlobSize();                                // 12
        [PreserveSig] int GetBlob();                                    // 13
        [PreserveSig] int GetAllocatedBlob();                           // 14
        [PreserveSig] int GetUnknown();                                 // 15
        [PreserveSig] int SetItem();                                    // 16
        [PreserveSig] int DeleteItem();                                 // 17
        [PreserveSig] int DeleteAllItems();                             // 18
        [PreserveSig] int SetUINT32(ref Guid key, uint value);          // 19
        [PreserveSig] int SetUINT64(ref Guid key, ulong value);         // 20
        [PreserveSig] int SetDouble(ref Guid key, double value);        // 21
        [PreserveSig] int SetGuid(ref Guid key, ref Guid value);        // 22
        [PreserveSig] int SetString();                                  // 23
        [PreserveSig] int SetBlob();                                    // 24
        [PreserveSig] int SetUnknown();                                 // 25
        [PreserveSig] int LockStore();                                  // 26
        [PreserveSig] int UnlockStore();                                // 27
        [PreserveSig] int GetCount();                                   // 28
        [PreserveSig] int GetItemByIndex();                             // 29
        [PreserveSig] int CopyAllItems();                               // 30
    }

    [ComImport, Guid("44ae0fa8-ea31-4109-8d2e-4cae4997c555"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IMFMediaType : IMFAttributes { }

    [ComImport, Guid("045fa593-8799-42b8-bc8d-8968c6453507"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IMFMediaBuffer
    {
        [PreserveSig] int Lock(out IntPtr ppbBuffer, out int pcbMaxLength, out int pcbCurrentLength);
        [PreserveSig] int Unlock();
        [PreserveSig] int GetCurrentLength(out int pcbCurrentLength);
        [PreserveSig] int SetCurrentLength(int cbCurrentLength);
        [PreserveSig] int GetMaxLength(out int pcbMaxLength);
    }

    [ComImport, Guid("c40a00f2-b93a-4d80-ae8c-5a1c634f58e4"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IMFSample : IMFAttributes
    {
        // Note: IMFSample extends IMFAttributes; only the methods we call follow.
        [PreserveSig] int GetSampleFlags(out uint pdwSampleFlags);
        [PreserveSig] int SetSampleFlags(uint dwSampleFlags);
        [PreserveSig] int GetSampleTime(out long phnsSampleTime);
        [PreserveSig] int SetSampleTime(long hnsSampleTime);
        [PreserveSig] int GetSampleDuration(out long phnsSampleDuration);
        [PreserveSig] int SetSampleDuration(long hnsSampleDuration);
        [PreserveSig] int GetBufferCount(out int pdwBufferCount);
        [PreserveSig] int GetBufferByIndex(int dwIndex, out IMFMediaBuffer ppBuffer);
        [PreserveSig] int ConvertToContiguousBuffer(out IMFMediaBuffer ppBuffer);
        [PreserveSig] int AddBuffer(IMFMediaBuffer pBuffer);
    }

    [ComImport, Guid("3137f1cd-fe5e-4805-a5d8-fb477448cb3d"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IMFSinkWriter
    {
        [PreserveSig] int AddStream(IMFMediaType pTargetMediaType, out int pdwStreamIndex);
        [PreserveSig] int SetInputMediaType(int dwStreamIndex, IMFMediaType pInputMediaType, IntPtr pEncodingParameters);
        [PreserveSig] int BeginWriting();
        [PreserveSig] int WriteSample(int dwStreamIndex, IMFSample pSample);
        [PreserveSig] int SendStreamTick(int dwStreamIndex, long llTimestamp);
        [PreserveSig] int PlaceMarker(int dwStreamIndex, IntPtr pvContext);
        [PreserveSig] int NotifyEndOfSegment(int dwStreamIndex);
        [PreserveSig] int Flush(int dwStreamIndex);
        [PreserveSig] int DoFinalize();
        [PreserveSig] int GetServiceForStream();
        [PreserveSig] int GetStatistics();
    }
}
