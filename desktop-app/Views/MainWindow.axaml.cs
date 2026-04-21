using System;
using System.ComponentModel;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Threading;
using VozIA.Desktop.Services;

namespace VozIA.Desktop.Views;

public partial class MainWindow : Window
{
    private readonly AudioService _audio = new();
    private readonly SseService _sse = new();
    private readonly AudioPlayerService _player = new();
    private bool _running;
    private bool _reallyClose;
    private string? _pendingScreenshot;

    // Provider/voice data
    private record ComboItem(int Id, string Name);
    private ComboItem[] _providers = Array.Empty<ComboItem>();
    private ComboItem[] _voices = Array.Empty<ComboItem>();

    public MainWindow()
    {
        InitializeComponent();
        Loaded += async (_, _) => await LoadData();
        _audio.OnSpeechComplete += OnSpeechComplete;
        _audio.OnSpeakingChanged += OnSpeakingChanged;
        _sse.OnEvent += OnSseEvent;
    }

    private async Task LoadData()
    {
        // Agent
        var agent = await App.Api.GetAgentAsync();
        if (agent.HasValue)
        {
            var name = agent.Value.GetProperty("agent_name").GetString();
            Dispatcher.UIThread.Post(() => LblAgent.Text = $"Agente: {name ?? "—"}");
        }

        // Providers
        var prov = await App.Api.GetProvidersAsync();
        if (prov.HasValue)
        {
            _providers = prov.Value.EnumerateArray()
                .Select(p => new ComboItem(p.GetProperty("id").GetInt32(),
                                           p.GetProperty("name").GetString() ?? "?"))
                .ToArray();
            Dispatcher.UIThread.Post(() =>
            {
                CbProvider.ItemsSource = _providers.Select(p => p.Name).ToArray();
                if (_providers.Length > 0) CbProvider.SelectedIndex = 0;
            });
        }

        // Voices
        var voices = await App.Api.GetVoicesAsync();
        if (voices.HasValue)
        {
            _voices = voices.Value.EnumerateArray()
                .Select(v => new ComboItem(v.GetProperty("id").GetInt32(),
                                           v.GetProperty("name").GetString() ?? "?"))
                .ToArray();
            Dispatcher.UIThread.Post(() =>
            {
                CbVoice.ItemsSource = _voices.Select(v => v.Name).ToArray();
                if (_voices.Length > 0) CbVoice.SelectedIndex = 0;
            });
        }
    }

    private int? SelectedProviderId =>
        CbProvider.SelectedIndex >= 0 && CbProvider.SelectedIndex < _providers.Length
            ? _providers[CbProvider.SelectedIndex].Id : null;

    private int? SelectedVoiceId =>
        CbVoice.SelectedIndex >= 0 && CbVoice.SelectedIndex < _voices.Length
            ? _voices[CbVoice.SelectedIndex].Id : null;

    private async void OnToggle(object? sender, RoutedEventArgs e)
    {
        if (!_running)
        {
            _running = true;
            BtnToggle.Content = "⏹ Parar";
            BtnToggle.Background = new Avalonia.Media.SolidColorBrush(
                Avalonia.Media.Color.Parse("#e74c3c"));
            SetStatus("Ouvindo...");
            _audio.Start();
            await _sse.StartAsync();
        }
        else
        {
            _running = false;
            _audio.Stop();
            _sse.Stop();
            BtnToggle.Content = "▶ Iniciar";
            BtnToggle.Background = new Avalonia.Media.SolidColorBrush(
                Avalonia.Media.Color.Parse("#6c5ce7"));
            SetStatus("Parado");
        }
    }

    private async void OnSpeechComplete(byte[] wavData)
    {
        if (!_running) return;
        Dispatcher.UIThread.Post(() => SetStatus("Processando..."));
        _player.Reset();
        var screenshot = _pendingScreenshot;
        _pendingScreenshot = null;
        await App.Api.SendAudioAsync(wavData, SelectedProviderId, SelectedVoiceId, screenshot);
    }

    private void OnSpeakingChanged(bool speaking)
    {
        if (!_running) return;
        if (speaking)
            _pendingScreenshot = ScreenCaptureService.CaptureScreenBase64();
        Dispatcher.UIThread.Post(() =>
            SetStatus(speaking ? "Gravando..." : "Processando..."));
    }

    private void OnSseEvent(string type, string data)
    {
        Dispatcher.UIThread.Post(() =>
        {
            switch (type)
            {
                case "status":
                    SetStatus(data switch
                    {
                        "listening" => "Ouvindo...",
                        "recording" => "Gravando...",
                        "processing" => "Processando...",
                        _ => data
                    });
                    break;
                case "transcript":
                    LblTranscript.Text = data;
                    break;
                case "ai_text":
                    LblAiText.Text = data;
                    break;
                case "wake_miss":
                    LblWakeHint.Text = $"Fale o nome \"{data}\" para que eu possa responder.";
                    LblWakeHint.IsVisible = true;
                    _ = HideWakeHintAsync();
                    BeepService.PlayBeep();
                    break;
                case "audio_chunk":
                    HandleAudioChunk(data);
                    break;
            }
        });
    }

    private void HandleAudioChunk(string jsonData)
    {
        try
        {
            var doc = JsonSerializer.Deserialize<JsonElement>(jsonData);
            var index = doc.GetProperty("index").GetInt32();
            var total = doc.GetProperty("total").GetInt32();
            var audio = doc.GetProperty("audio").GetString() ?? "";
            var last = doc.GetProperty("last").GetBoolean();
            int? startAfter = doc.TryGetProperty("start_after", out var sa) ? sa.GetInt32() : null;
            _player.EnqueueChunk(index, total, audio, last, startAfter);
        }
        catch { }
    }

    private async Task HideWakeHintAsync()
    {
        await Task.Delay(4000);
        Dispatcher.UIThread.Post(() => LblWakeHint.IsVisible = false);
    }

    private void SetStatus(string text) => LblStatus.Text = text;

    private void OnClosing(object? sender, WindowClosingEventArgs e)
    {
        if (!_reallyClose)
        {
            e.Cancel = true;
            Hide(); // minimize to tray
            return;
        }
        _audio.Dispose();
        _sse.Stop();
    }

    public void ForceClose()
    {
        _reallyClose = true;
        Close();
    }
}
