using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Media;
using System.Threading.Tasks;
using VozIA.Desktop.Services;

namespace VozIA.Desktop.Views;

public partial class LoginWindow : Window
{
    public LoginWindow()
    {
        InitializeComponent();
        Loaded += async (_, _) => await TryAutoLogin();
    }

    private async Task TryAutoLogin()
    {
        var creds = CredentialStore.Load();
        if (creds == null) return;

        TxtServer.Text = creds.Server;
        TxtUser.Text = creds.Username;
        TxtPass.Text = creds.Password;

        LblError.Text = "Reconectando...";
        LblError.Foreground = new SolidColorBrush(Color.Parse("#888"));
        BtnLogin.IsEnabled = false;

        App.Api.SetBaseUrl(creds.Server);
        var (ok, _) = await App.Api.LoginAsync(creds.Username, creds.Password);
        if (ok)
        {
            OpenMain();
        }
        else
        {
            LblError.Text = "Sessão expirada — entre novamente.";
            LblError.Foreground = new SolidColorBrush(Color.Parse("#ffb86c"));
            BtnLogin.IsEnabled = true;
        }
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
        LblError.Foreground = new SolidColorBrush(Color.Parse("#888"));

        App.Api.SetBaseUrl(server);
        var (ok, error) = await App.Api.LoginAsync(user, pass);

        if (ok)
        {
            CredentialStore.Save(server, user, pass);
            OpenMain();
        }
        else
        {
            LblError.Foreground = new SolidColorBrush(Color.Parse("#ff5555"));
            LblError.Text = error;
            BtnLogin.IsEnabled = true;
        }
    }

    private void OpenMain()
    {
        var main = new MainWindow();
        App.Main = main;
        main.Show();
        Close();
    }
}
