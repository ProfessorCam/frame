using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Shapes;
using Wpeek.Native;

namespace Wpeek;

/// <summary>
/// Full-virtual-desktop overlay. User drags a rectangle; <see cref="Region"/>
/// returns the selection in PHYSICAL pixels (ready for BitBlt). DialogResult
/// is true on a valid selection, false/null on cancel.
/// </summary>
public partial class RegionSelector : Window
{
    private Point _start;
    private bool _dragging;
    private readonly Rectangle _sel;
    private readonly Rectangle[] _dim = new Rectangle[4];

    // Physical virtual-screen origin (pixels) and DIP→pixel scale.
    private int _vx, _vy;
    private double _scaleX = 1, _scaleY = 1;

    /// <summary>Selection in physical pixels (virtual-screen coordinates).</summary>
    public Int32Rect Region { get; private set; }

    public RegionSelector()
    {
        InitializeComponent();

        for (int i = 0; i < 4; i++)
        {
            _dim[i] = new Rectangle { Fill = new SolidColorBrush(Color.FromArgb(0x73, 0, 0, 0)) };
            Root.Children.Add(_dim[i]);
        }
        _sel = new Rectangle
        {
            Stroke = new SolidColorBrush(Color.FromRgb(0xE8, 0x4C, 0x3D)),
            StrokeThickness = 2,
            Fill = Brushes.Transparent,
            Visibility = Visibility.Collapsed,
        };
        Root.Children.Add(_sel);
        DimLabel.SetValue(Panel.ZIndexProperty, 10);

        MouseLeftButtonDown += OnDown;
        MouseMove += OnMove;
        MouseLeftButtonUp += OnUp;
        KeyDown += (_, e) => { if (e.Key == Key.Escape) { DialogResult = false; Close(); } };
        Loaded += OnLoaded;
    }

    protected override void OnSourceInitialized(EventArgs e)
    {
        base.OnSourceInitialized(e);

        // Cover the whole virtual desktop in physical pixels, DPI-independent.
        _vx = NativeMethods.GetSystemMetrics(NativeMethods.SM_XVIRTUALSCREEN);
        _vy = NativeMethods.GetSystemMetrics(NativeMethods.SM_YVIRTUALSCREEN);
        int vw = NativeMethods.GetSystemMetrics(NativeMethods.SM_CXVIRTUALSCREEN);
        int vh = NativeMethods.GetSystemMetrics(NativeMethods.SM_CYVIRTUALSCREEN);

        var hwnd = new WindowInteropHelper(this).Handle;
        NativeMethods.SetWindowPos(hwnd, NativeMethods.HWND_TOPMOST, _vx, _vy, vw, vh,
            NativeMethods.SWP_SHOWWINDOW);

        var dpi = VisualTreeHelper.GetDpi(this);
        _scaleX = dpi.DpiScaleX;
        _scaleY = dpi.DpiScaleY;
    }

    private void OnLoaded(object sender, RoutedEventArgs e)
    {
        Hint.SetValue(Canvas.LeftProperty, (ActualWidth - Hint.ActualWidth) / 2);
        Hint.SetValue(Canvas.TopProperty, (ActualHeight - Hint.ActualHeight) / 2);
        LayoutDim(new Rect(0, 0, 0, 0));   // full dim initially
        Activate();
    }

    private void OnDown(object sender, MouseButtonEventArgs e)
    {
        _start = e.GetPosition(Root);
        _dragging = true;
        _sel.Visibility = Visibility.Visible;
        Hint.Visibility = Visibility.Collapsed;
        DimLabel.Visibility = Visibility.Visible;
    }

    private void OnMove(object sender, MouseEventArgs e)
    {
        if (!_dragging) return;
        var p = e.GetPosition(Root);
        var r = new Rect(_start, p);
        Canvas.SetLeft(_sel, r.X); Canvas.SetTop(_sel, r.Y);
        _sel.Width = r.Width; _sel.Height = r.Height;
        LayoutDim(r);

        int pw = (int)Math.Round(r.Width * _scaleX);
        int ph = (int)Math.Round(r.Height * _scaleY);
        DimLabel.Text = $"{pw} × {ph}";
        Canvas.SetLeft(DimLabel, r.X + r.Width / 2 - 24);
        Canvas.SetTop(DimLabel, r.Y + r.Height + 6);
    }

    private void OnUp(object sender, MouseButtonEventArgs e)
    {
        if (!_dragging) return;
        _dragging = false;
        var p = e.GetPosition(Root);
        var r = new Rect(_start, p);

        // DIP (relative to window) → physical pixels in virtual-screen space
        int x = _vx + (int)Math.Round(r.X * _scaleX);
        int y = _vy + (int)Math.Round(r.Y * _scaleY);
        int w = (int)Math.Round(r.Width * _scaleX) & ~1;   // even dims are encoder-friendly
        int h = (int)Math.Round(r.Height * _scaleY) & ~1;

        if (w >= 20 && h >= 20)
        {
            Region = new Int32Rect(x, y, w, h);
            DialogResult = true;
        }
        else
        {
            DialogResult = false;
        }
        Close();
    }

    // Four dim rectangles surrounding the (clear) selection.
    private void LayoutDim(Rect sel)
    {
        double W = ActualWidth, H = ActualHeight;
        Place(_dim[0], 0, 0, W, sel.Y);                                   // top
        Place(_dim[1], 0, sel.Y + sel.Height, W, H - sel.Y - sel.Height); // bottom
        Place(_dim[2], 0, sel.Y, sel.X, sel.Height);                      // left
        Place(_dim[3], sel.X + sel.Width, sel.Y, W - sel.X - sel.Width, sel.Height); // right
    }

    private static void Place(Rectangle r, double x, double y, double w, double h)
    {
        Canvas.SetLeft(r, x); Canvas.SetTop(r, y);
        r.Width = Math.Max(0, w); r.Height = Math.Max(0, h);
    }
}
