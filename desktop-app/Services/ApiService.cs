using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;

namespace VozIA.Desktop.Services;

public class ApiService
{
    private readonly HttpClient _http;
    private readonly CookieContainer _cookies = new();
    private string _baseUrl = "";

    public string BaseUrl => _baseUrl;

    public ApiService()
    {
        var handler = new HttpClientHandler { CookieContainer = _cookies };
        _http = new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(120) };
    }

    public void SetBaseUrl(string url)
    {
        _baseUrl = url.TrimEnd('/');
    }

    public async Task<(bool ok, string error)> LoginAsync(string username, string password)
    {
        try
        {
            var content = new FormUrlEncodedContent(new[]
            {
                new KeyValuePair<string, string>("username", username),
                new KeyValuePair<string, string>("password", password),
            });
            var res = await _http.PostAsync($"{_baseUrl}/login", content);
            // Flask login redirects on success
            if (res.IsSuccessStatusCode || res.StatusCode == HttpStatusCode.Redirect)
            {
                // Verify by calling /api/me
                var me = await _http.GetAsync($"{_baseUrl}/api/me");
                if (me.IsSuccessStatusCode) return (true, "");
            }
            return (false, "Usuário ou senha inválidos");
        }
        catch (Exception ex)
        {
            return (false, $"Erro de conexão: {ex.Message}");
        }
    }

    public async Task<JsonElement?> GetProvidersAsync()
    {
        try
        {
            var res = await _http.GetAsync($"{_baseUrl}/api/providers");
            if (!res.IsSuccessStatusCode) return null;
            var json = await res.Content.ReadAsStringAsync();
            return JsonSerializer.Deserialize<JsonElement>(json);
        }
        catch { return null; }
    }

    public async Task<JsonElement?> GetVoicesAsync()
    {
        try
        {
            var res = await _http.GetAsync($"{_baseUrl}/api/voices");
            if (!res.IsSuccessStatusCode) return null;
            var json = await res.Content.ReadAsStringAsync();
            return JsonSerializer.Deserialize<JsonElement>(json);
        }
        catch { return null; }
    }

    public async Task<JsonElement?> GetAgentAsync()
    {
        try
        {
            var res = await _http.GetAsync($"{_baseUrl}/api/agent");
            if (!res.IsSuccessStatusCode) return null;
            var json = await res.Content.ReadAsStringAsync();
            return JsonSerializer.Deserialize<JsonElement>(json);
        }
        catch { return null; }
    }

    public async Task<string?> SendAudioAsync(byte[] wavData, int? providerId, int? voiceId, string? screenshotB64 = null)
    {
        try
        {
            var content = new MultipartFormDataContent();
            content.Add(new ByteArrayContent(wavData), "audio", "rec.wav");
            if (providerId.HasValue)
                content.Add(new StringContent(providerId.Value.ToString()), "provider_id");
            if (voiceId.HasValue)
                content.Add(new StringContent(voiceId.Value.ToString()), "voice_id");
            if (!string.IsNullOrEmpty(screenshotB64))
                content.Add(new StringContent(screenshotB64), "screenshot");
            var res = await _http.PostAsync($"{_baseUrl}/api/audio", content);
            return await res.Content.ReadAsStringAsync();
        }
        catch (Exception ex)
        {
            return $"{{\"error\":\"{ex.Message}\"}}";
        }
    }

    public async Task<Stream?> GetSseStreamAsync()
    {
        try
        {
            var req = new HttpRequestMessage(HttpMethod.Get, $"{_baseUrl}/events");
            var res = await _http.SendAsync(req, HttpCompletionOption.ResponseHeadersRead);
            if (res.IsSuccessStatusCode)
                return await res.Content.ReadAsStreamAsync();
            return null;
        }
        catch { return null; }
    }
}
