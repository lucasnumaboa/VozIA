using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Markup.Xaml;
using VozIA.Desktop.Services;
using VozIA.Desktop.Views;

namespace VozIA.Desktop;

public partial class App : Application
{
    public static ApiService Api { get; } = new();
    public static MainWindow? Main { get; set; }

    public override void Initialize() => AvaloniaXamlLoader.Load(this);

    public override void OnFrameworkInitializationCompleted()
    {
        if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
        {
            desktop.MainWindow = new LoginWindow();
            desktop.ShutdownMode = ShutdownMode.OnExplicitShutdown;
        }
        base.OnFrameworkInitializationCompleted();
    }

    public void OnTrayOpen(object? sender, System.EventArgs e)
    {
        if (Main != null)
        {
            Main.Show();
            Main.WindowState = WindowState.Normal;
            Main.Activate();
        }
    }

    public void OnTrayExit(object? sender, System.EventArgs e)
    {
        Main?.ForceClose();
        if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
            desktop.Shutdown();
    }
}
