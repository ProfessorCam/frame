using System.Diagnostics;
using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Threading;
using Wpeek.Capture;
using Wpeek.Encoding;

namespace Wpeek;

public partial class MainWindow : Window
{
    private readonly Config _cfg = Config.Load();
    private ScreenRecorder? _recorder;
    private DispatcherTimer? _timer;
    private int _seconds;
    private string? _lastSaved;

    private Popup? _settingsPopup;
    private CheckBox? _cursorCheck;
    private ComboBox? _fpsBox;

    public MainWindow()
    {
        InitializeComponent();
        RestoreSettings();
        BuildSettingsPopup();

        PreviewKeyDown += (_, e) =>
        {
            if (e.Key == Key.Escape) OnEscape();
            else if (e.Key == Key.Space && _recorder != null) TogglePause();
        };
    }

    // ── Settings restore / persistence ────────────────────────────────
    private void RestoreSettings()
    {
        (_cfg.Format == OutputFormat.Gif ? FmtGif : FmtMp4).IsChecked = true;
        DelayBox.SelectedIndex = _cfg.Delay switch { 3 => 1, 5 => 2, 10 => 3, _ => 0 };
    }

    private void BuildSettingsPopup()
    {
        _cursorCheck = new CheckBox { Content = "Capture cursor", Foreground = Brushes.White, IsChecked = _cfg.Cursor };
        _cursorCheck.Checked += (_, _) => { _cfg.Cursor = true; _cfg.Save(); };
        _cursorCheck.Unchecked += (_, _) => { _cfg.Cursor = false; _cfg.Save(); };

        _fpsBox = new ComboBox { Width = 90, Margin = new Thickness(0, 6, 0, 0) };
        foreach (var f in new[] { 15, 24, 30 }) _fpsBox.Items.Add(new ComboBoxItem { Content = $"{f} fps", Tag = f });
        _fpsBox.SelectedIndex = _cfg.Framerate switch { 15 => 0, 24 => 1, _ => 2 };
        _fpsBox.SelectionChanged += (_, _) =>
        {
            if (_fpsBox.SelectedItem is ComboBoxItem it && it.Tag is int f) { _cfg.Framerate = f; _cfg.Save(); }
        };

        var panel = new StackPanel { Margin = new Thickness(12) };
        panel.Children.Add(_cursorCheck);
        panel.Children.Add(new TextBlock { Text = "Frame rate", Foreground = Brushes.White, Margin = new Thickness(0, 10, 0, 0) });
        panel.Children.Add(_fpsBox);

        _settingsPopup = new Popup
        {
            PlacementTarget = GearBtn,
            Placement = PlacementMode.Bottom,
            StaysOpen = false,
            AllowsTransparency = true,
            Child = new Border
            {
                Background = (Brush)FindResource("PillBg"),
                BorderBrush = (Brush)FindResource("PillBorder"),
                BorderThickness = new Thickness(1),
                CornerRadius = new CornerRadius(12),
                Child = panel,
            },
        };
    }

    private void Gear_Click(object sender, RoutedEventArgs e)
    {
        if (_settingsPopup != null) _settingsPopup.IsOpen = !_settingsPopup.IsOpen;
    }

    // ── Idle controls ─────────────────────────────────────────────────
    private void Pill_Drag(object sender, MouseButtonEventArgs e)
    {
        if (e.ButtonState == MouseButtonState.Pressed) DragMove();
    }

    private void Fmt_Click(object sender, RoutedEventArgs e)
    {
        var btn = (ToggleButton)sender;
        FmtGif.IsChecked = btn == FmtGif;
        FmtMp4.IsChecked = btn == FmtMp4;
        _cfg.Format = btn == FmtMp4 ? OutputFormat.Mp4 : OutputFormat.Gif;
        _cfg.Save();
    }

    private void Delay_Changed(object sender, SelectionChangedEventArgs e)
    {
        if (DelayBox.SelectedItem is ComboBoxItem it && int.TryParse((string)it.Tag, out var d))
        {
            _cfg.Delay = d; _cfg.Save();
        }
    }

    private void Close_Click(object sender, RoutedEventArgs e) => Close();

    private void OnEscape()
    {
        if (_recorder != null) _recorder.Stop();
        else Close();
    }

    // ── Record flow ───────────────────────────────────────────────────
    private void Record_Click(object sender, RoutedEventArgs e)
    {
        HideToast();
        Hide();                       // don't let the pill sit over the selection
        Dispatcher.BeginInvoke(SelectAndRecord, DispatcherPriority.Background);
    }

    private void SelectAndRecord()
    {
        var selector = new RegionSelector();
        bool ok = selector.ShowDialog() == true;
        Show();
        Activate();
        if (!ok) { ShowToast("Selection cancelled", ToastKind.Info); return; }

        var region = selector.Region;
        if (_cfg.Delay > 0)
        {
            var cd = new CountdownWindow(_cfg.Delay);
            if (cd.ShowDialog() != true) { ShowToast("Cancelled", ToastKind.Info); return; }
        }
        StartRecording(region);
    }

    private void StartRecording(System.Windows.Int32Rect region)
    {
        string path = OutputPath(_cfg.Format);
        IEncoder encoder = _cfg.Format == OutputFormat.Mp4 ? new Mp4Encoder(path) : new GifEncoder(path);
        var rec = new ScreenRecorder(region, _cfg.Framerate, _cfg.Cursor, encoder);

        rec.Started += () => Dispatcher.Invoke(() => EnterRecordingUi(region));
        rec.Converting += () => Dispatcher.Invoke(() => ShowToast("Converting…", ToastKind.Info));
        rec.Finished += p => Dispatcher.Invoke(() => OnFinished(p));
        rec.Failed += m => Dispatcher.Invoke(() => OnFailed(m));

        _recorder = rec;
        rec.Start();
    }

    private void EnterRecordingUi(System.Windows.Int32Rect region)
    {
        IdlePanel.Visibility = Visibility.Collapsed;
        RecPanel.Visibility = Visibility.Visible;
        SizeText.Text = $"{region.Width} × {region.Height}";
        PauseBtn.Content = "Pause";
        TimerText.Foreground = new SolidColorBrush(Color.FromRgb(0xFF, 0x45, 0x3A));
        _seconds = 0; TimerText.Text = "0:00";
        _timer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1) };
        _timer.Tick += (_, _) =>
        {
            if (_recorder is { IsPaused: false }) { _seconds++; TimerText.Text = $"{_seconds / 60}:{_seconds % 60:00}"; }
        };
        _timer.Start();
    }

    private void ExitRecordingUi()
    {
        _timer?.Stop(); _timer = null;
        _recorder = null;
        RecPanel.Visibility = Visibility.Collapsed;
        IdlePanel.Visibility = Visibility.Visible;
    }

    private void Pause_Click(object sender, RoutedEventArgs e) => TogglePause();

    private void TogglePause()
    {
        if (_recorder == null) return;
        if (_recorder.IsPaused)
        {
            _recorder.Resume();
            PauseBtn.Content = "Pause";
            TimerText.Foreground = new SolidColorBrush(Color.FromRgb(0xFF, 0x45, 0x3A));
        }
        else
        {
            _recorder.Pause();
            PauseBtn.Content = "Resume";
            TimerText.Foreground = new SolidColorBrush(Color.FromRgb(0xF5, 0xA6, 0x23));
        }
    }

    private void Stop_Click(object sender, RoutedEventArgs e) => _recorder?.Stop();

    private void OnFinished(string path)
    {
        ExitRecordingUi();
        _lastSaved = path;
        ShowToast($"Saved  {Path.GetFileName(path)}", ToastKind.Good, withActions: true);
    }

    private void OnFailed(string msg)
    {
        ExitRecordingUi();
        ShowToast($"Error: {msg}", ToastKind.Error);
    }

    // ── Toast ─────────────────────────────────────────────────────────
    private enum ToastKind { Info, Good, Error }

    private void ShowToast(string text, ToastKind kind, bool withActions = false)
    {
        ToastText.Text = text;
        ToastText.Foreground = kind switch
        {
            ToastKind.Good => (Brush)FindResource("Good"),
            ToastKind.Error => (Brush)FindResource("Accent"),
            _ => (Brush)FindResource("TextPrimary"),
        };
        ToastActions.Children.Clear();
        if (withActions)
        {
            ToastActions.Children.Add(MakeAction("Open", OpenSaved));
            ToastActions.Children.Add(MakeAction("Reveal", RevealSaved));
            ToastActions.Children.Add(MakeAction("Copy path", CopySaved));
        }
        Toast.Visibility = Visibility.Visible;
    }

    private void HideToast() => Toast.Visibility = Visibility.Collapsed;

    private Button MakeAction(string label, Action handler)
    {
        var b = new Button { Content = label, Style = (Style)FindResource("Flat"), Margin = new Thickness(6, 0, 0, 0) };
        b.Click += (_, _) => handler();
        return b;
    }

    private void OpenSaved()
    {
        if (_lastSaved != null && File.Exists(_lastSaved))
            Process.Start(new ProcessStartInfo(_lastSaved) { UseShellExecute = true });
    }

    private void RevealSaved()
    {
        if (_lastSaved != null && File.Exists(_lastSaved))
            Process.Start("explorer.exe", $"/select,\"{_lastSaved}\"");
    }

    private void CopySaved()
    {
        if (_lastSaved != null) { Clipboard.SetText(_lastSaved); ShowToast("Path copied", ToastKind.Good); }
    }

    // ── Paths ─────────────────────────────────────────────────────────
    private static string OutputPath(OutputFormat fmt)
    {
        string dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyVideos));
        Directory.CreateDirectory(dir);
        string ts = DateTime.Now.ToString("yyyy-MM-dd_HH-mm-ss");
        string ext = fmt == OutputFormat.Mp4 ? "mp4" : "gif";
        return Path.Combine(dir, $"frame_{ts}.{ext}");
    }
}
