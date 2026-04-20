using System;
using System.Collections.Concurrent;
using System.IO;
using System.Threading;
using NAudio.Wave;

namespace VozIA.Desktop.Services;

public class AudioPlayerService
{
    private readonly ConcurrentDictionary<int, byte[]> _queue = new();
    private int _total;
    private bool _started;
    private bool _allReceived;
    private int _startAfter = 2;

    public void Reset()
    {
        _queue.Clear();
        _total = 0;
        _started = false;
        _allReceived = false;
        _startAfter = 2;
    }

    public void EnqueueChunk(int index, int total, string audioB64, bool isLast, int? startAfter)
    {
        var data = Convert.FromBase64String(audioB64);
        _queue[index] = data;
        _total = total;
        if (isLast) _allReceived = true;
        if (index == 0 && startAfter.HasValue) _startAfter = startAfter.Value;

        if (!_started && (_queue.Count >= _startAfter || _allReceived))
        {
            _started = true;
            ThreadPool.QueueUserWorkItem(_ => PlayChain(0));
        }
    }

    private void PlayChain(int idx)
    {
        if (idx >= _total) return;
        if (!_queue.TryRemove(idx, out var wavData))
        {
            Thread.Sleep(80);
            PlayChain(idx);
            return;
        }
        try
        {
            using var ms = new MemoryStream(wavData);
            using var reader = new WaveFileReader(ms);
            using var waveOut = new WaveOutEvent();
            waveOut.Init(reader);
            waveOut.Play();
            while (waveOut.PlaybackState == PlaybackState.Playing)
                Thread.Sleep(20);
        }
        catch { /* skip broken chunk */ }
        PlayChain(idx + 1);
    }
}
