using System;
using System.IO;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace VozIA.Desktop.Services;

public class SseService
{
    private CancellationTokenSource? _cts;

    public event Action<string, string>? OnEvent; // (type, data)

    public async Task StartAsync()
    {
        _cts = new CancellationTokenSource();
        var stream = await App.Api.GetSseStreamAsync();
        if (stream == null) return;

        _ = Task.Run(async () =>
        {
            using var reader = new StreamReader(stream);
            string? eventType = null;
            while (!_cts.Token.IsCancellationRequested)
            {
                var line = await reader.ReadLineAsync();
                if (line == null) break;
                if (line.StartsWith("event:"))
                    eventType = line[6..].Trim();
                else if (line.StartsWith("data:") && eventType != null)
                {
                    var data = line[5..].Trim();
                    OnEvent?.Invoke(eventType, data);
                    eventType = null;
                }
            }
        }, _cts.Token);
    }

    public void Stop()
    {
        _cts?.Cancel();
        _cts?.Dispose();
        _cts = null;
    }
}
