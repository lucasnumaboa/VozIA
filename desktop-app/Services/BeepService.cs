using System;
using System.Threading;
using NAudio.Wave;
using NAudio.Wave.SampleProviders;

namespace VozIA.Desktop.Services;

public static class BeepService
{
    public static void PlayBeep(int frequencyHz = 480, int durationMs = 250, float volume = 0.18f)
    {
        ThreadPool.QueueUserWorkItem(_ =>
        {
            try
            {
                var signal = new SignalGenerator(44100, 1)
                {
                    Gain = volume,
                    Frequency = frequencyHz,
                    Type = SignalGeneratorType.Sin,
                };
                var take = signal.Take(TimeSpan.FromMilliseconds(durationMs));
                var fade = new FadeInOutSampleProvider(take, initiallySilent: false);
                fade.BeginFadeOut(durationMs * 0.4);

                using var wo = new WaveOutEvent();
                wo.Init(fade);
                wo.Play();
                while (wo.PlaybackState == PlaybackState.Playing)
                    Thread.Sleep(10);
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[Beep] {ex.Message}");
            }
        });
    }
}
