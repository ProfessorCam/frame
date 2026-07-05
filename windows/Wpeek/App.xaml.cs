using System.Windows;
using System.Windows.Threading;

namespace Wpeek;

public partial class App : Application
{
    public App()
    {
        // Never let an unexpected error kill the recorder silently.
        DispatcherUnhandledException += OnUnhandledException;
    }

    private void OnUnhandledException(object sender, DispatcherUnhandledExceptionEventArgs e)
    {
        MessageBox.Show(e.Exception.Message, "Frame — unexpected error",
            MessageBoxButton.OK, MessageBoxImage.Error);
        e.Handled = true;
    }
}
