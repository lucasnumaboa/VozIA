using Avalonia.Controls;
using Avalonia.Interactivity;
using System.Threading.Tasks;

namespace VozIA.Desktop.Views;

public partial class LoginWindow : Window
{
    public LoginWindow()
    {
        InitializeComponent();
    }

    private async void OnLogin(object? sender, RoutedEventArgs e)
    {
        var server = TxtServer.Text?.Trim() ?? "";
        var user = TxtUser.Text?.Trim() ?? "";
        var pass = TxtPass.Text?.Trim() ?? "";

        if (string.IsNullOrEmpty(server) || string.IsNullOrEmpty(user))
        {
            LblError.Text = "Preencha servidor e usuário.";
            return;
        }

        BtnLogin.IsEnabled = false;
        LblError.Text = "Conectando...";
        LblError.Foreground = new Avalonia.Media.SolidColorBrush(Avalonia.Media.Color.Parse("#888"));

        App.Api.SetBaseUrl(server);
        var (ok, error) = await App.Api.LoginAsync(user, pass);

        if (ok)
        {
            var main = new MainWindow();
            App.Main = main;
            main.Show();
            Close();
        }
        else
        {
            LblError.Foreground = new Avalonia.Media.SolidColorBrush(Avalonia.Media.Color.Parse("#ff5555"));
            LblError.Text = error;
            BtnLogin.IsEnabled = true;
        }
    }
}
