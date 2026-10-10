"""Real built-library/CLI tests; fixture framing oracle is independent of C demux code."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import unittest
import wave

P = argparse.ArgumentParser()
P.add_argument("--bin", required=True)
P.add_argument("--sample", required=True)
P.add_argument("--output", required=True)
ARGS, REST = P.parse_known_args()
BIN, SAMPLE, OUT = Path(ARGS.bin), Path(ARGS.sample), Path(ARGS.output)
OUT.mkdir(parents=True, exist_ok=False)

def crc16(data):
    reg = 0
    for byte in data:
        for bit in range(7, -1, -1):
            carry = ((reg >> 15) ^ (byte >> bit)) & 1
            reg = (reg << 1) & 65535
            if carry:
                reg ^= 0x8005
    return reg

def frame(payload, crc=False, extended=False):
    length = (b"\xff\xff" + len(payload).to_bytes(3, "big")) if extended else len(payload).to_bytes(2, "big")
    body = length + payload
    return (b"\xac\x41" if crc else b"\xac\x40") + body + (crc16(body).to_bytes(2, "big") if crc else b"")

def tag(body=b"", version=4, footer=False):
    n = len(body)
    header = b"ID3" + bytes((version, 0, 16 if footer else 0, (n >> 21) & 127, (n >> 14) & 127, (n >> 7) & 127, n & 127))
    return header + body + (b"3DI" + header[3:] if footer else b"")

class DemuxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = SAMPLE.read_bytes()
        assert hashlib.sha256(data).hexdigest() == "2c1b726a9d9bd08afd6d10a42d2933ae69b27ec8f0842d9476d2bcdb48f4c533"
        n = sum(data[6+i] << (21-7*i) for i in range(4))
        pos = 10 + n
        cls.packets, cls.payloads = [], []
        while pos < len(data):
            sync = data[pos:pos+2]
            assert sync in (b"\xac\x40", b"\xac\x41")
            size = int.from_bytes(data[pos+2:pos+4], "big"); header = 4
            if size == 65535:
                size = int.from_bytes(data[pos+4:pos+7], "big"); header = 7
            payload = data[pos+header:pos+header+size]
            assert len(payload) == size and size
            cls.packets.append((pos, size, hashlib.sha256(payload).hexdigest()))
            cls.payloads.append(payload)
            pos += header + size + (2 if sync == b"\xac\x41" else 0)
        assert pos == len(data) and len(cls.packets) == 150
        cls.payload = cls.payloads[0]
        cls.records = []

    def run_probe(self, name, data):
        path = OUT / (name + ".ac4")
        path.write_bytes(data)
        r = subprocess.run([str(BIN / "ac4_packet_probe"), str(path)], capture_output=True, text=True)
        (OUT / (name + ".stdout")).write_text(r.stdout)
        (OUT / (name + ".stderr")).write_text(r.stderr)
        self.records.append({"name":name,"exit":r.returncode,"input_sha256":hashlib.sha256(data).hexdigest()})
        return r

    def test_original_packet_identity(self):
        r = self.run_probe("original", SAMPLE.read_bytes())
        actual = [(int(a),int(b),c) for a,b,c in (line.split("\t") for line in r.stdout.splitlines())]
        self.assertEqual(r.returncode, 0)
        self.assertEqual(actual, self.packets)

    def test_positive_envelopes(self):
        self.assertEqual(crc16(b"123456789"), 0xFEE8)
        for version in (3,4):
            for crc in (False,True):
                for extended in (False,True):
                    name = f"v{version}_crc{int(crc)}_ext{int(extended)}"
                    head = tag(b"metadata of variable length",version)
                    r = self.run_probe(name, head + frame(self.payload,crc,extended))
                    with self.subTest(name=name):
                        self.assertEqual(r.returncode,0)
                        self.assertEqual(r.stdout.strip(),f"{len(head)}\t{len(self.payload)}\t{hashlib.sha256(self.payload).hexdigest()}")
        r = self.run_probe("footer",tag(b"metadata",footer=True)+frame(self.payload))
        self.assertEqual(r.returncode,0)
        r = self.run_probe("bare",frame(self.payload))
        self.assertEqual(r.returncode,0)

    def test_extended_large_payload(self):
        payload=bytes(range(256))*256
        for crc in (False,True):
            r=self.run_probe("large_extended_"+str(int(crc)),frame(payload,crc,True))
            self.assertEqual(r.returncode,0)
            self.assertEqual(r.stdout.strip(),f"0\t65536\t{hashlib.sha256(payload).hexdigest()}")

    def test_malformed_rejected(self):
        good = frame(self.payload)
        cases = {
            "empty":b"", "bad_sync":b"XX"+good[2:], "short_sync":b"\xac",
            "short_length":good[:3], "short_extended":b"\xac\x40\xff\xff\x00",
            "zero_length":b"\xac\x40\x00\x00", "short_payload":good[:-1],
            "missing_crc":frame(self.payload,True)[:-2],
            "bad_crc":frame(self.payload,True)[:-1]+bytes((frame(self.payload,True)[-1]^1,)),
            "wrong_crc_coverage":b"\xac\x41"+good[2:]+crc16(self.payload).to_bytes(2,"big"),
            "short_id3_header":b"ID3\x04", "short_id3_body":tag(b"abc")[:-1],
            "id3_bad_synchsafe":b"ID3\x04\x00\x00\x80\x00\x00\x00"+good,
            "id3_bad_version":tag(version=2)+good,
            "id3_reserved_flags":b"ID3\x04\x00\x01\x00\x00\x00\x00"+good,
            "id3_too_large":b"ID3\x04\x00\x00\x00\x40\x00\x01"+good,
            "bad_footer":tag(b"abc",footer=True)[:-1]+b"X"+good,
            "trailing_garbage":good+b"X", "second_bad_frame":good+b"XX\x00\x01Z",
        }
        for name,data in cases.items():
            with self.subTest(name=name):
                self.assertNotEqual(self.run_probe(name,data).returncode,0)

    def test_default_cli_full_six_seconds(self):
        target = OUT / "default.wav"
        command = [str(BIN/"ffmpeg"),"-nostdin","-hide_banner","-loglevel","error","-i",str(SAMPLE),"-c:a","pcm_s16le",str(target)]
        r = subprocess.run(command,capture_output=True,text=True)
        (OUT/"default.stderr").write_text(r.stderr)
        self.records.append({"name":"default_cli","argv":command,"exit":r.returncode})
        self.assertEqual(r.returncode,0)
        self.assertEqual(r.stderr,"")
        with wave.open(str(target)) as wav:
            self.assertEqual(wav.getnchannels(),2)
            self.assertEqual(wav.getnframes()/wav.getframerate(),6.0)

    def test_strict_cli_bad_input_nonzero(self):
        path=OUT/"strict_bad.ac4";path.write_bytes(frame(self.payload)[:-1])
        r=subprocess.run([str(BIN/"ffmpeg"),"-nostdin","-v","error","-xerror","-f","ac4","-i",str(path),"-c:a","pcm_s16le",str(OUT/"bad.wav")],capture_output=True,text=True)
        self.records.append({"name":"strict_cli_bad","exit":r.returncode})
        self.assertNotEqual(r.returncode,0)

    def test_checked_entry_defaults_and_negative_exit(self):
        entry=Path(__file__).resolve().parents[1]/"scripts/decode_ac4_checked.sh"
        target=OUT/"checked.wav"
        r=subprocess.run(["bash",str(entry),str(BIN),str(SAMPLE),str(target)],capture_output=True,text=True)
        self.records.append({"name":"checked_original","exit":r.returncode})
        self.assertEqual(r.returncode,0)
        with wave.open(str(target)) as wav:self.assertEqual(wav.getnframes()/wav.getframerate(),6.0)
        for name,data in (("checked_tail",frame(self.payload)+b"X"),("checked_crc",frame(self.payload,True)[:-1]+b"X")):
            path=OUT/(name+".ac4");path.write_bytes(data);output=OUT/(name+".wav")
            r=subprocess.run(["bash",str(entry),str(BIN),str(path),str(output)],capture_output=True,text=True)
            self.records.append({"name":name,"exit":r.returncode})
            self.assertNotEqual(r.returncode,0)
            self.assertFalse(output.exists())

    @classmethod
    def tearDownClass(cls):
        (OUT/"results.json").write_text(json.dumps(cls.records,indent=2)+"\n")

if __name__ == "__main__":
    unittest.main(argv=[__file__]+REST)
