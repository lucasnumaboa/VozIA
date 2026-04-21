using System;
using System.IO;
using System.Text.Json;

namespace VozIA.Desktop.Services;

public record SavedCredentials(string Server, string Username, string Password);

public static class CredentialStore
{
    private static readonly string _dir = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "VozIA");
    private static readonly string _file = Path.Combine(_dir, "credentials.json");

    public static SavedCredentials? Load()
    {
        try
        {
            if (!File.Exists(_file)) return null;
            var json = File.ReadAllText(_file);
            return JsonSerializer.Deserialize<SavedCredentials>(json);
        }
        catch { return null; }
    }

    public static void Save(string server, string username, string password)
    {
        try
        {
            Directory.CreateDirectory(_dir);
            var json = JsonSerializer.Serialize(new SavedCredentials(server, username, password));
            File.WriteAllText(_file, json);
        }
        catch (Exception ex)
        {
            Console.WriteLine($"[Credentials] Erro ao salvar: {ex.Message}");
        }
    }

    public static void Delete()
    {
        try { if (File.Exists(_file)) File.Delete(_file); } catch { }
    }
}
