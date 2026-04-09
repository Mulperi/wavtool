#!/usr/bin/env python3

import os
import subprocess
import sys
import shutil
import re
import wave
import struct
import argparse


# ----------------------------
# SoX check
# ----------------------------
def check_sox():
    if not shutil.which("sox"):
        print("ERROR: SoX not found.")
        print("Install: brew install sox / apt install sox")
        sys.exit(1)


# ----------------------------
# helpers
# ----------------------------
def ask_yes_no(q, default_yes=True):
    while True:
        print("\n" + q)
        print("  1) Yes")
        print("  2) No")
        d = "1" if default_yes else "2"
        a = input(f"Select [{d}]: ").strip()
        if a == "":
            a = d
        if a == "1":
            return True
        if a == "2":
            return False


def ask_choice(q, options, default_key=None):
    print("\n" + q)
    for k, v in options.items():
        print(f"  {k}) {v}")
    while True:
        if default_key is None:
            a = input("Select: ").strip()
        else:
            a = input(f"Select [{default_key}]: ").strip()
            if a == "":
                a = default_key
        if a in options:
            return options[a]
        print("Invalid")


def clean_name(filename):
    name = os.path.splitext(os.path.basename(filename))[0]
    name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    return name[:40]


# ----------------------------
# MOD EXPORT (simple container)
# ----------------------------
def wav_to_mod_sample(wav_path):
    with wave.open(wav_path, "rb") as wf:
        nch = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        nframes = wf.getnframes()
        data = wf.readframes(nframes)

    if sampwidth not in (1, 2):
        raise ValueError("Unsupported sample width: %d" % sampwidth)

    # Convert to mono 16-bit signed in Python, then to 8-bit signed.
    # WAV 8-bit is unsigned; WAV 16-bit is signed little-endian.
    if sampwidth == 1:
        samples = [b - 128 for b in data]
    else:
        # 16-bit signed little-endian
        samples = [s[0] for s in struct.iter_unpack("<h", data)]

    if nch > 1:
        # Average channels per frame
        mono = []
        step = nch
        for i in range(0, len(samples), step):
            frame = samples[i:i+step]
            if not frame:
                break
            mono.append(int(sum(frame) / len(frame)))
        samples = mono

    # Convert 16-bit signed range to 8-bit signed
    if sampwidth == 2:
        out = bytearray(len(samples))
        for i, s in enumerate(samples):
            v = int(round(s / 256.0))
            if v < -128:
                v = -128
            elif v > 127:
                v = 127
            out[i] = (v + 256) % 256
        data = bytes(out)
    else:
        # Already in 8-bit signed from bias
        data = bytes((s + 256) % 256 for s in samples)

    # Ensure even length (MOD sample lengths are in words)
    if len(data) % 2 != 0:
        data += b"\x00"

    return data


def write_mod(output_path, samples):
    # samples: list of dicts with keys {name, data}
    header = bytearray(1084)
    header[0:20] = b"WAV2MOD EXPORT".ljust(20, b"\x00")

    # Sample headers (31 * 30 bytes)
    offset = 20
    for s in samples[:31]:
        name = s["name"].encode("ascii", errors="ignore")[:22]
        header[offset:offset+22] = name.ljust(22, b"\x00")
        offset += 22

        length_words = len(s["data"]) // 2
        if length_words > 0xFFFF:
            length_words = 0xFFFF
        header[offset:offset+2] = length_words.to_bytes(2, "big")
        offset += 2

        header[offset] = 0  # finetune
        offset += 1

        header[offset] = 64  # volume
        offset += 1

        # No loop: start 0, length 1 word (minimum)
        header[offset:offset+2] = (0).to_bytes(2, "big")
        offset += 2
        header[offset:offset+2] = (1).to_bytes(2, "big")
        offset += 2

    # Pad remaining sample headers if fewer than 31
    while offset < 20 + (31 * 30):
        header[offset:offset+30] = b"\x00" * 30
        offset += 30

    # Song length = 1 pattern, restart = 0
    header[950] = 1
    header[951] = 0

    # Pattern table (128 bytes), use pattern 0 for first entry
    for i in range(128):
        header[952 + i] = 0

    # Signature for 4-channel MOD
    header[1080:1084] = b"M.K."

    pattern_data = b"\x00" * 1024  # 1 empty pattern

    with open(output_path, "wb") as f:
        f.write(header)
        f.write(pattern_data)

        for s in samples[:31]:
            f.write(s["data"])


# ----------------------------
# SoX processing (FIXED ORDER)
# ----------------------------
def run_sox(in_path, out_path, cfg):
    def build_fx(allow_trim=True):
        fx = []

        # ----------------------------
        # MONO MODE
        # ----------------------------
        if cfg["mono_mode"] == "Mix (L+R combined)":
            fx += ["channels", "1"]
        elif cfg["mono_mode"] == "Left channel only":
            fx += ["remix", "1"]
        elif cfg["mono_mode"] == "Right channel only":
            fx += ["remix", "2"]

        # ----------------------------
        # normalization / gain
        # ----------------------------
        if cfg.get("normalize"):
            fx += ["gain", "-n"]
        elif cfg.get("gain_db") is not None:
            fx += ["gain", str(cfg["gain_db"])]

        # ----------------------------
        # high-frequency boost
        # ----------------------------
        if cfg.get("treble_boost"):
            fx += ["treble", str(cfg["treble_gain_db"]), str(cfg["treble_freq_hz"])]

        # ----------------------------
        # speed change (pitch + time)
        # ----------------------------
        if cfg.get("speed_up_2x"):
            fx += ["speed", "2.0"]

        # ----------------------------
        # anti-click fade
        # ----------------------------
        fade_map = {
            "Off (0 ms)": None,
            "Very short (5 ms)": 0.005,
            "Short (10 ms)": 0.01,
            "Medium (25 ms)": 0.025
        }

        fade_time = fade_map.get(cfg["fade_mode"])
        if fade_time:
            fx += ["fade", str(fade_time), "0", str(fade_time)]

        # ----------------------------
        # trim leading/trailing silence
        # ----------------------------
        if allow_trim and cfg.get("trim_silence"):
            thresh = cfg.get("trim_threshold_db", -40)
            min_sil = cfg.get("trim_min_silence", 0.05)
            try:
                with wave.open(in_path, "rb") as wf:
                    duration = wf.getnframes() / float(wf.getframerate())
            except Exception:
                duration = None
            if duration is None or duration >= (min_sil * 2):
                fx += ["silence", "1", str(min_sil), f"{thresh}d", "reverse",
                       "silence", "1", str(min_sil), f"{thresh}d", "reverse"]

        return fx

    def run_cmd(fx):
        cmd = ["sox"]
        if cfg.get("sox_quiet"):
            cmd += ["-V0"]
        cmd += [
            in_path,
            "-r", str(cfg["rate"]),
            "-c", "1",
            "-b", str(cfg["bits"]),
            out_path
        ] + fx

        if cfg["verbose"]:
            print("CMD:", " ".join(cmd))

        subprocess.run(cmd, check=True)

    fx = build_fx(allow_trim=True)
    run_cmd(fx)

    # If trim removed everything, rerun once without trimming
    try:
        if os.path.getsize(out_path) <= 44 and cfg.get("trim_silence"):
            if cfg["verbose"]:
                print("WARN: output empty after trim, retrying without trim")
            fx = build_fx(allow_trim=False)
            run_cmd(fx)
    except Exception:
        pass


# ----------------------------
# MAIN WIZARD
# ----------------------------
def main():
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("-i", "--input", dest="input_path", help="Input folder")
    parser.add_argument("-o", "--output", dest="output_path", help="Output folder")
    parser.add_argument("-p", "--preset", action="store_true",
                        help="Use ProTracker-safe preset and skip prompts")
    parser.add_argument("--clean", action="store_true",
                        help="Delete existing output files before converting")
    args, _ = parser.parse_known_args()

    check_sox()

    print("=== WAV2MOD v6 FIXED ===\n")

    if args.input_path:
        inp = args.input_path
    elif args.preset:
        inp = "."
    else:
        inp = input("Input folder (. = current folder): ").strip()

    if args.output_path:
        out = args.output_path
    elif args.preset:
        out = "converted"
    else:
        out = input("Output folder [converted]: ").strip()
        if not out:
            out = "converted"

    if not os.path.isdir(inp):
        print("ERROR: input folder not found")
        sys.exit(1)

    if args.clean:
        try:
            if os.path.isdir(out):
                shutil.rmtree(out)
        except Exception:
            pass
    os.makedirs(out, exist_ok=True)

    # ----------------------------
    # preset
    # ----------------------------
    if args.preset:
        preset = True
    else:
        preset = ask_yes_no("Use ProTracker-safe preset?", default_yes=True)

    cfg = {}

    if preset:
        cfg = {
            "rate": 16574,
            "bits": 8,
            "mono_mode": "Mix (L+R combined)",
            "fade_mode": "Very short (5 ms)",
            "trim_silence": True,
            "trim_threshold_db": -40,
            "trim_min_silence": 0.05,
            "normalize": True,
            "gain_db": None,
            "treble_boost": False,
            "treble_gain_db": 3,
            "treble_freq_hz": 5000,
            "speed_up_2x": True,
            "sox_quiet": True,
            "verbose": False
        }
        print("\nPROTRACKER PRESET ACTIVE")

    else:
        rate = ask_choice("Sample rate:",
            {
                "1":"8287 (PAL C-3)",
                "2":"8363 (NTSC C-3)",
                "3":"11025",
                "4":"16574 (PAL C-4)",
                "5":"16726 (NTSC C-4)",
                "6":"22050",
                "7":"44100"
            },
            default_key="1")

        bits = ask_choice("Bit depth:",
            {"1":"8-bit","2":"16-bit"},
            default_key="1")

        mono_mode = ask_choice("Mono mode:",
            {
                "1":"Mix (L+R combined)",
                "2":"Left channel only",
                "3":"Right channel only"
            },
            default_key="1")

        fade_mode = ask_choice("Anti-click envelope:",
            {
                "1":"Off (0 ms)",
                "2":"Very short (5 ms)",
                "3":"Short (10 ms)",
                "4":"Medium (25 ms)"
            },
            default_key="2")

        trim_silence = ask_yes_no("Trim leading/trailing silence?", default_yes=True)
        trim_threshold_db = -40
        if trim_silence:
            th = ask_choice("Trim threshold (dB):",
                {"1":"-30","2":"-40","3":"-50","4":"-60"},
                default_key="2")
            trim_threshold_db = int(th)

        normalize = ask_yes_no("Normalize to full scale?", default_yes=True)
        gain_db = None
        if not normalize:
            g = ask_choice("Gain (dB):",
                {"1":"-3","2":"0","3":"+3","4":"+6"},
                default_key="2")
            gain_db = int(g)

        treble_boost = ask_yes_no("High-frequency boost?", default_yes=True)
        treble_gain_db = 0
        treble_freq_hz = 5000
        if treble_boost:
            tg = ask_choice("Treble boost (dB):",
                {"1":"+3","2":"+6","3":"+9"},
                default_key="1")
            treble_gain_db = int(tg.replace("+", ""))
            tf = ask_choice("Treble center (Hz):",
                {"1":"4000","2":"5000","3":"6000","4":"8000"},
                default_key="2")
            treble_freq_hz = int(tf)

        speed_up_2x = ask_yes_no("Speed up 2x (octave up, half length)?", default_yes=True)

        cfg = {
            "rate": int(rate.split()[0]),
            "bits": 8 if bits == "8-bit" else 16,
            "mono_mode": mono_mode,
            "fade_mode": fade_mode,
            "trim_silence": trim_silence,
            "trim_threshold_db": trim_threshold_db,
            "trim_min_silence": 0.05,
            "normalize": normalize,
            "gain_db": gain_db,
            "treble_boost": treble_boost,
            "treble_gain_db": treble_gain_db,
            "treble_freq_hz": treble_freq_hz,
            "speed_up_2x": speed_up_2x,
            "sox_quiet": ask_yes_no("Silence SoX warnings?", default_yes=True),
            "verbose": ask_yes_no("Verbose output?", default_yes=False)
        }

    if args.preset:
        export_mod = True
    else:
        export_mod = ask_yes_no("Export MOD sample container?", default_yes=True)

    mod_samples = []

    print("\n--- PROCESSING ---\n")

    files = [f for f in os.listdir(inp) if f.lower().endswith(".wav")]

    if not files:
        print("No WAV files found.")
        return

    for f in files:
        in_path = os.path.join(inp, f)
        name = clean_name(f)
        out_path = os.path.join(out, name + ".wav")

        try:
            run_sox(in_path, out_path, cfg)
            print("OK:", name)

            if export_mod:
                try:
                    data = wav_to_mod_sample(out_path)
                    mod_samples.append({
                        "name": name,
                        "data": data
                    })
                except Exception as e:
                    print("MOD SKIP:", name, "-", e)

        except subprocess.CalledProcessError:
            print("FAIL:", name)

    if export_mod:
        mod_path = os.path.join(out, "sample_pack.mod")
        write_mod(mod_path, mod_samples)
        print("\nMOD CREATED:", mod_path)

    print("\nDONE.")


if __name__ == "__main__":
    main()
