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
        Stop();
        _cts = new CancellationTokenSource();
        var stream = await App.Api.GetSseStreamAsync();
        if (stream == null)
        {
            Console.WriteLine("[SSE] Falha ao conectar no stream");
            return;
        }
        Console.WriteLine("[SSE] Conectado");

        _ = Task.Run(async () =>
        {
            try
            {
                using var reader = new StreamReader(stream);
                while (!_cts.Token.IsCancellationRequested)
                {
                    var line = await reader.ReadLineAsync();
                    if (line == null) break;
                    if (string.IsNullOrWhiteSpace(line) || line.StartsWith(":")) continue;
                    if (!line.StartsWith("data:")) continue;

                    var json = line[5..].Trim();
                    if (string.IsNullOrEmpty(json)) continue;

                    try
                    {
                        var doc = JsonSerializer.Deserialize<JsonElement>(json);
                        var type = doc.GetProperty("type").GetString() ?? "";
                        var dataEl = doc.GetProperty("data");
                        // data can be string or object — serialize objects back to string
                        var data = dataEl.ValueKind == JsonValueKind.String
                            ? dataEl.GetString() ?? ""
                            : dataEl.GetRawText();
                        OnEvent?.Invoke(type, data);
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"[SSE] Parse error: {ex.Message} | {json[..Math.Min(json.Length, 100)]}");
                    }
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[SSE] Stream error: {ex.Message}");
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
