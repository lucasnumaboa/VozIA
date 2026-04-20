using System;
using System.Collections.Generic;
using System.IO;
using NAudio.Wave;

namespace VozIA.Desktop.Services;

public class AudioService : IDisposable
{
    private WaveInEvent? _waveIn;
    private readonly List<byte> _buffer = new();
    private readonly object _lock = new();
    private bool _isSpeaking;
    private int _speechCount;
    private int _silenceCount;
    private readonly List<byte> _preBuffer = new();

    private const int SampleRate = 16000;
    private const int Channels = 1;
    private const int BitsPerSample = 16;
    private const float Threshold = 0.008f;
    private const int SpeechOnTicks = 3;
    private const int SilenceOffTicks = 22;
    private const int PreBufferMaxBytes = 5 * 2048 * 2; // ~5 frames

    public event Action<byte[]>? OnSpeechComplete;
    public event Action<bool>? OnSpeakingChanged;

    public void Start()
    {
        if (_waveIn != null) return;
        _waveIn = new WaveInEvent
        {
            WaveFormat = new WaveFormat(SampleRate, BitsPerSample, Channels),
            BufferMilliseconds = 128
        };
        _waveIn.DataAvailable += OnDataAvailable;
        _waveIn.StartRecording();
    }

    public void Stop()
    {
        if (_waveIn == null) return;
        _waveIn.StopRecording();
        _waveIn.DataAvailable -= OnDataAvailable;
        _waveIn.Dispose();
        _waveIn = null;
        _isSpeaking = false;
        _speechCount = 0;
        _silenceCount = 0;
        lock (_lock) { _buffer.Clear(); _preBuffer.Clear(); }
    }

    private void OnDataAvailable(object? sender, WaveInEventArgs e)
    {
        // Compute RMS
        float rms = 0;
        int samples = e.BytesRecorded / 2;
        for (int i = 0; i < e.BytesRecorded - 1; i += 2)
        {
            short sample = (short)(e.Buffer[i] | (e.Buffer[i + 1] << 8));
            float normalized = sample / 32768f;
            rms += normalized * normalized;
        }
        rms = MathF.Sqrt(rms / Math.Max(samples, 1));

        lock (_lock)
        {
            if (!_isSpeaking)
            {
                _preBuffer.AddRange(new ArraySegment<byte>(e.Buffer, 0, e.BytesRecorded));
                if (_preBuffer.Count > PreBufferMaxBytes)
                    _preBuffer.RemoveRange(0, _preBuffer.Count - PreBufferMaxBytes);
            }

            if (rms > Threshold)
            {
                _speechCount++;
                _silenceCount = 0;
                if (!_isSpeaking && _speechCount >= SpeechOnTicks)
                {
                    _isSpeaking = true;
                    _buffer.Clear();
                    _buffer.AddRange(_preBuffer);
                    _preBuffer.Clear();
                    OnSpeakingChanged?.Invoke(true);
                }
            }
            else
            {
                _silenceCount++;
                _speechCount = 0;
                if (_isSpeaking && _silenceCount >= SilenceOffTicks)
                {
                    _isSpeaking = false;
                    _silenceCount = 0;
                    var wavData = BuildWav(_buffer.ToArray());
                    _buffer.Clear();
                    OnSpeakingChanged?.Invoke(false);
                    OnSpeechComplete?.Invoke(wavData);
                }
            }

            if (_isSpeaking)
                _buffer.AddRange(new ArraySegment<byte>(e.Buffer, 0, e.BytesRecorded));
        }
    }

    private static byte[] BuildWav(byte[] pcmData)
    {
        using var ms = new MemoryStream();
        using (var writer = new BinaryWriter(ms))
        {
            int dataLen = pcmData.Length;
            writer.Write(new[] { 'R', 'I', 'F', 'F' });
            writer.Write(36 + dataLen);
            writer.Write(new[] { 'W', 'A', 'V', 'E' });
            writer.Write(new[] { 'f', 'm', 't', ' ' });
            writer.Write(16);
            writer.Write((short)1);
            writer.Write((short)Channels);
            writer.Write(SampleRate);
            writer.Write(SampleRate * Channels * BitsPerSample / 8);
            writer.Write((short)(Channels * BitsPerSample / 8));
            writer.Write((short)BitsPerSample);
            writer.Write(new[] { 'd', 'a', 't', 'a' });
            writer.Write(dataLen);
            writer.Write(pcmData);
        }
        return ms.ToArray();
    }

    public void Dispose()
    {
        Stop();
        GC.SuppressFinalize(this);
    }
}
