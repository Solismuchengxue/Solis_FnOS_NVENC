import importlib.util
import math
import pathlib
import struct
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("wav_check", pathlib.Path(__file__).resolve().parents[1] / "scripts" / "wav_check.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture(channels=2, rate=48000, silence=False, extensible=False):
    frames = rate // 2
    pcm = b"".join(struct.pack("<h", 0 if silence else int(3000 * math.sin(2 * math.pi * 440 * n / rate)))
                   for n in range(frames) for _ in range(channels))
    code = 65534 if extensible else 1
    fmt = struct.pack("<HHIIHH", code, channels, rate, rate * channels * 2, channels * 2, 16)
    if extensible:
        fmt += struct.pack("<HHI", 22, 16, 0) + bytes.fromhex("0100000000001000800000aa00389b71")
    chunks = b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(pcm)) + pcm
    return b"RIFF" + struct.pack("<I", len(chunks) + 4) + b"WAVE" + chunks


class WavCheckTests(unittest.TestCase):
    def read(self, content):
        with tempfile.TemporaryDirectory(prefix="solis-wav-unit-") as directory:
            path = pathlib.Path(directory) / "fixture.wav"
            path.write_bytes(content)
            return module.load_wav(path)

    def test_stereo_pcm(self):
        got, _ = self.read(fixture())
        self.assertEqual((got["channels"], got["sample_rate"], got["frames"]), (2, 48000, 24000))

    def test_multichannel_extensible(self):
        got, _ = self.read(fixture(channels=6, extensible=True))
        self.assertEqual(got["channels"], 6)

    def test_silence_fails(self):
        with self.assertRaises(ValueError):
            self.read(fixture(silence=True))

    def test_wrong_rate_fails(self):
        with self.assertRaises(ValueError):
            self.read(fixture(rate=44100))

    def test_truncated_data_fails(self):
        with self.assertRaises(ValueError):
            self.read(fixture()[:-1])

    def test_invalid_header_fails(self):
        with self.assertRaises(ValueError):
            self.read(b"not an audio file")


unittest.main()
