using System.Windows;
using System.Windows.Input;
using System.Windows.Threading;

namespace Wpeek;

/// <summary>Fullscreen countdown. DialogResult true when it reaches 0, false on Esc.</summary>
public partial class CountdownWindow : Window
{
    private int _remaining;
    private readonly DispatcherTimer _timer;

    public CountdownWindow(int seconds)
    {
        InitializeComponent();
        _remaining = seconds;
        Num.Text = _remaining.ToString();

        _timer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1) };
        _timer.Tick += Tick;
        KeyDown += (_, e) => { if (e.Key == Key.Escape) Cancel(); };
        Loaded += (_, _) => { Activate(); _timer.Start(); };
    }

    private void Tick(object? sender, EventArgs e)
    {
        _remaining--;
        if (_remaining <= 0)
        {
            _timer.Stop();
            DialogResult = true;
            Close();
        }
        else
        {
            Num.Text = _remaining.ToString();
        }
    }

    private void Cancel()
    {
        _timer.Stop();
        DialogResult = false;
        Close();
    }
}
