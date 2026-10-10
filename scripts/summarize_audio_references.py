"""Inspect independent decoder observations; no automatic codec-conformance verdict.

Requires NumPy already available in the caller's authorized local environment.
One bounded common lag per case is selected from startup PCM; no resampling,
channel gain correction or per-channel lag fitting is applied.
"""
import hashlib
import json
from pathlib import Path
import sys

import numpy as np


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pcm(path, channels):
    data = np.frombuffer(path.read_bytes(), dtype='<f4').astype(np.float64)
    assert data.size % channels == 0 and np.isfinite(data).all()
    return data.reshape(-1, channels)


def metrics(data, rate, frequencies):
    result = []
    t = np.arange(len(data)) / rate
    for ch, frequency in enumerate(frequencies):
        signal = data[:, ch]
        power = float(np.mean(signal * signal))
        sine = float(np.mean(signal * np.sin(2 * np.pi * frequency * t)))
        cosine = float(np.mean(signal * np.cos(2 * np.pi * frequency * t)))
        result.append({'rms': power ** .5, 'tone_fraction': 2 * (sine * sine + cosine * cosine) / power})
    return result


def lag_for(x, y):
    n = min(32768, len(x), len(y))
    x, y = x[:n], y[:n]
    length = 1 << (2 * n - 1).bit_length()
    cross = np.fft.irfft(np.sum(np.fft.rfft(x, length, axis=0) * np.conj(np.fft.rfft(y, length, axis=0)), axis=1), length)
    lags = np.arange(-4096, 4097)
    x0, y0 = np.maximum(lags, 0), np.maximum(-lags, 0)
    x1, y1 = n - y0, n - x0
    ex = np.r_[0, np.cumsum(np.sum(x*x, axis=1))]
    ey = np.r_[0, np.cumsum(np.sum(y*y, axis=1))]
    coefficient = cross[lags % length] / np.sqrt((ex[x1] - ex[x0]) * (ey[y1] - ey[y0]))
    best = int(np.argmax(coefficient))
    return int(lags[best]), float(coefficient[best])


def main():
    if len(sys.argv) != 4:
        raise SystemExit('Usage: summarize_audio_references.py PROJECT_ROOT TEST_RUN REFERENCE_RUN')
    root = Path(sys.argv[1]).resolve()
    test_run, ref_run = (Path(arg).resolve() for arg in sys.argv[2:])
    for path in (test_run, ref_run):
        assert path.is_relative_to(root / 'artifacts') and path.is_dir()
    rows = (ref_run / 'status.tsv').read_text().splitlines()[1:]
    results = []
    for row in rows:
        case, reference, code = row.split('\t')
        assert code == '0', (case, code)
        native_json = json.loads((test_run / 'results' / (case + '.new.json')).read_text())
        ref_json = json.loads((ref_run / 'results' / (case + '.json')).read_text())
        log = (ref_run / 'results' / (case + '.log')).read_text()
        assert 'REFERENCE_LIB=' in log and 'REFERENCE_MAP=' in log and 'libavcodec' not in log
        channels, rate = native_json['channels'], native_json['sample_rate']
        assert channels == ref_json['channels'] and rate == ref_json['sample_rate'] == 48000
        native_path = test_run / 'results' / (case + '.new.raw')
        ref_path = ref_run / 'results' / (case + '.raw')
        x, y = pcm(native_path, channels), pcm(ref_path, channels)
        assert len(x) == native_json['samples'] and len(y) == ref_json['samples']
        lag, startup_corr = lag_for(x, y)
        start, stop = 24000, 72000
        assert 0 <= start - lag and stop - lag <= len(y)
        xa, ya = x[start:stop], y[start-lag:stop-lag]
        frequencies = [60 if channels == 6 and ch == 3 else 440 + ch * 110 for ch in range(channels)]
        if case == 'aac_he_mono': frequencies = [440] * channels
        comparisons = []
        for ch in range(channels):
            a, b = xa[:, ch], ya[:, ch]
            mse = float(np.mean((a-b)**2))
            signal_power = float(np.mean(a*a))
            comparisons.append({'correlation': float(np.corrcoef(a, b)[0, 1]), 'normalized_rmse': (mse/signal_power)**.5,
                                'reference_native_rms_ratio': float(np.sqrt(np.mean(b*b)/signal_power))})
        results.append({'case': case, 'reference': reference, 'native': native_json, 'reference_output': ref_json,
                        'native_sha256': sha(native_path), 'reference_sha256': sha(ref_path),
                        'fixture_sha256': sha(test_run / 'fixtures' / (case + '.scfix')),
                        'startup_native_lag_samples': lag, 'startup_correlation': startup_corr,
                        'window': {'native_start_sample': start, 'samples': stop-start, 'reference_start_sample': start-lag},
                        'native_metrics': metrics(xa, rate, frequencies), 'reference_metrics': metrics(ya, rate, frequencies),
                        'comparisons': comparisons, 'classification': 'OBSERVATIONS_FOR_REVIEW; NOT_STANDARD_CONFORMANCE'})
    assert len(results) == 9
    output = {'schema': 1, 'numpy_version': np.__version__, 'method': 'startup normalized FFT correlation; bounded +-4096 common lag; middle 1s PCM; no channel gain correction',
              'independence': 'FDK AAC and VideoLAN libdca; neither process loads FFmpeg; AAC encoder shares FDK origin with reference decoder',
              'limitations': 'synthetic inputs; no reference flush; steady-state only; independent implementations are not a certified standards oracle',
              'summarizer_sha256': sha(Path(__file__).resolve()), 'cases': results}
    (ref_run / 'summary.json').write_text(json.dumps(output, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    for result in results:
        print(json.dumps({'case': result['case'], 'lag': result['startup_native_lag_samples'],
                          'min_corr': min(c['correlation'] for c in result['comparisons']),
                          'max_nrmse': max(c['normalized_rmse'] for c in result['comparisons']),
                          'native_metrics': result['native_metrics'], 'reference_metrics': result['reference_metrics']}))


if __name__ == '__main__':
    main()
