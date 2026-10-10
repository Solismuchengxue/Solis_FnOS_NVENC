"""Verify small raw AC4 packetization and saved-library decode evidence.

Elementary boundaries follow fixed FFmpeg 8.1.1 libavformat/ac4dec.c.
This checks the supplied expected duration, not AC4 standards conformance.
"""
import array
import hashlib
import json
import math
from pathlib import Path
import struct
import sys


def digest(data):
    return hashlib.sha256(data).hexdigest()


def raw_frames(data):
    assert 0 < len(data) < 1048576
    offset = 0
    if data.startswith(b'ID3'):
        assert len(data) >= 10 and data[3] in (3, 4) and data[5] == 0
        length = 0
        for value in data[6:10]:
            assert value < 128
            length = (length << 7) | value
        offset = 10 + length
    tag_bytes = offset
    frames = []
    while offset < len(data):
        assert len(data) - offset >= 4 and data[offset:offset+2] in (b'\xac\x40', b'\xac\x41')
        sync = data[offset:offset+2]
        header, length = 4, int.from_bytes(data[offset+2:offset+4], 'big')
        if length == 65535:
            assert len(data) - offset >= 7
            header, length = 7, int.from_bytes(data[offset+4:offset+7], 'big')
        end = offset + header + length
        assert length > 0 and end + (2 if sync == b'\xac\x41' else 0) <= len(data)
        frames.append(data[offset+header:end])
        offset = end + (2 if sync == b'\xac\x41' else 0)
    assert frames and len(frames) <= 1024 and offset == len(data)
    return tag_bytes, frames


def main():
    if len(sys.argv) != 5:
        raise SystemExit('Usage: summarize_ac4_probe.py PROJECT_ROOT RAW_SAMPLE AC4_RUN EXPECTED_SECONDS')
    root = Path(sys.argv[1]).resolve()
    sample, run = (Path(arg).resolve() for arg in sys.argv[2:4])
    assert sample.is_relative_to(root / 'artifacts') and run.is_relative_to(root / 'artifacts')
    duration = float(sys.argv[4]); assert 0 < duration <= 30
    source = sample.read_bytes()
    tag_bytes, frames = raw_frames(source)
    fixture = (run / 'ac4.scfix').read_bytes()
    assert fixture[:8] == b'SCFIX3\0\0' and len(fixture) >= 68
    parameters = struct.unpack_from('<15I', fixture, 8)
    assert parameters[1] == 1 and parameters[14] == 0
    offset = 68
    for frame in frames:
        size, = struct.unpack_from('<I', fixture, offset); offset += 4
        assert size == len(frame) and fixture[offset:offset+size] == frame
        offset += size
    assert fixture[offset:] == b'\0\0\0\0'
    imported = json.loads((run / 'import.json').read_text())
    assert imported['packets'] == len(frames) and imported['id3_bytes'] == tag_bytes
    rows = (run / 'status.tsv').read_text().splitlines()[1:]
    assert rows == ['new\t0', 'historical\t0']
    identities = {'new': '88e48674062ee5ef71864a2619324772bc856fec78c0d4793920fa7d4c15cd57',
                  'historical': '3d7e7e241715fb6a3468a4d47d0fdaef3e6b79cecc3d3bb1f6d3118fac265367'}
    observations = []
    for role in identities:
        stats = json.loads((run / (role+'.json')).read_text())
        log = (run / (role+'.log')).read_text()
        expected_path = '/input/artifacts/rebuild-20261009/run1/libavcodec.so.62' if role == 'new' else '/input/artifacts/candidate-lib/libavcodec.so.62'
        assert 'LOADED_LIB='+expected_path+'\n' in log and 'LOADED_SHA256='+identities[role]+'\n' in log
        assert 'LIB_MAP=' in log and expected_path in log
        assert stats['frames'] == stats['packets'] == len(frames)
        assert stats['channels'] == 2 and stats['sample_rate'] > 0 and stats['samples'] > 0
        seconds = stats['samples'] / stats['sample_rate']
        assert abs(seconds-duration) < .04
        pcm_bytes = (run / (role+'.raw')).read_bytes()
        assert len(pcm_bytes) == stats['bytes'] == stats['samples'] * stats['channels'] * 4
        assert digest(pcm_bytes) == stats['sha256']
        pcm = array.array('f', pcm_bytes)
        if sys.byteorder != 'little': pcm.byteswap()
        assert all(math.isfinite(value) for value in pcm)
        assert .001 < stats['rms'] < 1 and .01 < stats['peak'] < 1
        channel_rms = [math.sqrt(sum(float(v)*v for v in pcm[ch::2]) / stats['samples']) for ch in range(2)]
        assert min(channel_rms) > .001
        observations.append({'role': role, 'library_sha256': identities[role], 'decode': stats,
                             'duration_seconds': seconds, 'channel_rms': channel_rms})
    assert (run/'new.raw').read_bytes() == (run/'historical.raw').read_bytes()
    result = {'status': 'PASS_LOCAL_DECODE_AND_REGRESSION', 'source_bytes': len(source), 'source_sha256': digest(source),
              'id3_bytes': tag_bytes, 'packets': len(frames), 'fixture_sha256': digest(fixture),
              'expected_seconds_from_supplied_source': duration, 'observations': observations,
              'limits': 'one 6s official test segment; no independent AC4 decoder, auditory check, 48kHz resampling, demux/player or standards certification',
              'summarizer_sha256': digest(Path(__file__).read_bytes())}
    (run / 'summary.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
