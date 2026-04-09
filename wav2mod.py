#!/usr/bin/env python3

import os
import subprocess
import sys
import shutil
import re
import wave
import struct
import argparse
import math


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
def find_loop_points(samples, rate_hz):
    n = len(samples)
    if n < 200:
        return None

    zero = []
    for i in range(1, n):
        a = samples[i - 1]
        b = samples[i]
        if (a <= 0 and b > 0) or (a >= 0 and b < 0):
            zero.append(i)

    if len(zero) < 2:
        return None

    min_len = max(int(rate_hz * 0.05), 200)
    max_len = min(n - 1, int(rate_hz * 2.0))
    if max_len <= min_len:
        return None

    end_cut = n - max(512, n // 10)
    end_candidates = [i for i in zero if i >= end_cut]
    start_candidates = [i for i in zero if i <= n - min_len]

    if not end_candidates or not start_candidates:
        return None

    best = None
    best_score = None
    for end in end_candidates:
        max_start = end - min_len
        min_start = max(0, end - max_len)
        for start in start_candidates:
            if start < min_start or start > max_start:
                continue
            window = min(64, n - end - 1, n - start - 1)
            if window < 8:
                continue
            score = 0
            for k in range(window):
                score += abs(samples[start + k] - samples[end + k])
            if best_score is None or score < best_score:
                best_score = score
                best = (start, end - start)

    return best


def wav_to_mod_sample(wav_path, loop_find=False, rate_hz=11025):
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

    loop_start = 0
    loop_len = 0
    if loop_find:
        loop = find_loop_points(samples, rate_hz)
        if loop:
            loop_start, loop_len = loop
            if loop_start + loop_len > len(data):
                loop_start = 0
                loop_len = 0

    return {
        "data": data,
        "loop_start": loop_start,
        "loop_len": loop_len
    }


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

        # Loop points (in words). If none, use length 1 word.
        loop_start = s.get("loop_start", 0)
        loop_len = s.get("loop_len", 0)
        if loop_len < 2:
            loop_start_words = 0
            loop_len_words = 1
        else:
            loop_start_words = loop_start // 2
            loop_len_words = max(1, loop_len // 2)
        header[offset:offset+2] = loop_start_words.to_bytes(2, "big")
        offset += 2
        header[offset:offset+2] = loop_len_words.to_bytes(2, "big")
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

        # ----------------------------
        # speed change (pitch + time)
        # ----------------------------
        if cfg.get("speed_up_2x"):
            fx += ["speed", "2.0"]

        # ----------------------------
        # high-frequency boost
        # ----------------------------
        if cfg.get("treble_boost"):
            fx += ["treble", str(cfg["treble_gain_db"]), str(cfg["treble_freq_hz"])]

        # ----------------------------
        # normalization / gain (after trim)
        # ----------------------------
        if cfg.get("normalize"):
            fx += ["gain", "-n"]
        elif cfg.get("gain_db") is not None:
            fx += ["gain", str(cfg["gain_db"])]

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

        if cfg["verbose"] and not cfg.get("silent"):
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


def report_peak_dbfs(path, label):
    try:
        res = subprocess.run(
            ["sox", path, "-n", "stat"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
    except Exception:
        return

    max_amp = None
    for line in res.stderr.splitlines():
        line = line.strip()
        if line.startswith("Maximum amplitude:"):
            try:
                max_amp = float(line.split(":")[1].strip())
            except Exception:
                max_amp = None
            break

    if max_amp is None:
        return

    if max_amp <= 0:
        peak_db = "-inf"
    else:
        peak_db = f"{20.0 * math.log10(max_amp):.2f} dBFS"

    print(f"PEAK: {label} = {peak_db}")


# ----------------------------
# MAIN WIZARD
# ----------------------------
def main():
    def mono_label(v):
        return {
            "mix": "Mix (L+R combined)",
            "left": "Left channel only",
            "right": "Right channel only"
        }.get(v)

    def fade_label(v):
        return {
            "off": "Off (0 ms)",
            "veryshort": "Very short (5 ms)",
            "short": "Short (10 ms)",
            "medium": "Medium (25 ms)"
        }.get(v)

    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("-i", "--input", dest="input_path", help="Input folder")
    parser.add_argument("-o", "--output", dest="output_path", help="Output folder")
    parser.add_argument("-p", "--preset", action="store_true",
                        help="Use ProTracker-safe preset and skip prompts")
    parser.add_argument("--clean", action="store_true",
                        help="Delete existing output files before converting")
    parser.add_argument("--loops", dest="loops", choices=["on", "off"],
                        help="Loop-point detection for MOD export (on/off)")
    parser.add_argument("--rate", dest="rate", help="Sample rate (e.g. 16574)")
    parser.add_argument("--bits", dest="bits", choices=["8", "16"], help="Bit depth (8 or 16)")
    parser.add_argument("--mono", dest="mono", choices=["mix", "left", "right"],
                        help="Mono mode: mix/left/right")
    parser.add_argument("--fade", dest="fade", choices=["off", "veryshort", "short", "medium"],
                        help="Anti-click envelope")
    parser.add_argument("--trim", dest="trim", choices=["on", "off"],
                        help="Trim leading/trailing silence (on/off)")
    parser.add_argument("--trim-threshold", dest="trim_threshold",
                        help="Trim threshold dB (e.g. -30)")
    parser.add_argument("--trim-min", dest="trim_min",
                        help="Trim minimum silence length in seconds (e.g. 0.05)")
    parser.add_argument("--normalize", dest="normalize", choices=["on", "off"],
                        help="Normalize to full scale (on/off)")
    parser.add_argument("--gain", dest="gain", help="Gain in dB (used if normalize off)")
    parser.add_argument("--treble", dest="treble", choices=["on", "off"],
                        help="High-frequency boost (on/off)")
    parser.add_argument("--treble-gain", dest="treble_gain",
                        help="Treble boost in dB (e.g. 3)")
    parser.add_argument("--treble-freq", dest="treble_freq",
                        help="Treble center frequency in Hz (e.g. 5000)")
    parser.add_argument("--speed", dest="speed", choices=["on", "off"],
                        help="Speed up 2x (on/off)")
    parser.add_argument("--sox-quiet", dest="sox_quiet", choices=["on", "off"],
                        help="Silence SoX warnings (on/off)")
    parser.add_argument("--verbose", dest="verbose", choices=["on", "off"],
                        help="Verbose output (on/off)")
    parser.add_argument("--export-mod", dest="export_mod", choices=["on", "off"],
                        help="Export MOD sample container (on/off)")
    parser.add_argument("--report-peak", dest="report_peak", choices=["on", "off"],
                        help="Report peak level of converted WAVs (on/off)")
    parser.add_argument("--silent", action="store_true",
                        help="Suppress output (print only Done.)")
    args, _ = parser.parse_known_args()

    check_sox()

    def say(msg):
        if not args.silent:
            print(msg)

    say("=== WAV2MOD v6 FIXED ===\n")

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
            "trim_threshold_db": -30,
            "trim_min_silence": 0.05,
            "normalize": True,
            "gain_db": None,
            "treble_boost": False,
            "treble_gain_db": 3,
            "treble_freq_hz": 5000,
            "speed_up_2x": True,
            "loop_find": True,
            "sox_quiet": True,
            "verbose": False,
            "silent": args.silent,
            "report_peak": False
        }
        say("\nPROTRACKER PRESET ACTIVE")

    else:
        if args.rate:
            rate = args.rate
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
                default_key="4")

        if args.bits:
            bits = f"{args.bits}-bit"
        else:
            bits = ask_choice("Bit depth:",
                {"1":"8-bit","2":"16-bit"},
                default_key="1")

        if args.mono:
            mono_mode = mono_label(args.mono)
        else:
            mono_mode = ask_choice("Mono mode:",
                {
                    "1":"Mix (L+R combined)",
                    "2":"Left channel only",
                    "3":"Right channel only"
                },
                default_key="1")

        if args.fade:
            fade_mode = fade_label(args.fade)
        else:
            fade_mode = ask_choice("Anti-click envelope:",
                {
                    "1":"Off (0 ms)",
                    "2":"Very short (5 ms)",
                    "3":"Short (10 ms)",
                    "4":"Medium (25 ms)"
                },
                default_key="1")

        if args.trim:
            trim_silence = (args.trim == "on")
        else:
            trim_silence = ask_yes_no("Trim leading/trailing silence?", default_yes=True)
        if args.trim_threshold:
            trim_threshold_db = int(args.trim_threshold)
        else:
            trim_threshold_db = -30
            if trim_silence:
                th = ask_choice("Trim threshold (dB):",
                    {"1":"-30","2":"-40","3":"-50","4":"-60"},
                    default_key="1")
                trim_threshold_db = int(th)
        if args.trim_min:
            trim_min_silence = float(args.trim_min)
        else:
            trim_min_silence = 0.05

        if args.normalize:
            normalize = (args.normalize == "on")
        else:
            normalize = ask_yes_no("Normalize to full scale?", default_yes=True)
        gain_db = None
        if not normalize:
            if args.gain:
                gain_db = int(args.gain)
            else:
                g = ask_choice("Gain (dB):",
                    {"1":"-3","2":"0","3":"+3","4":"+6"},
                    default_key="2")
                gain_db = int(g)

        if args.treble:
            treble_boost = (args.treble == "on")
        else:
            treble_boost = ask_yes_no("High-frequency boost?", default_yes=False)
        treble_gain_db = int(args.treble_gain) if args.treble_gain else 3
        treble_freq_hz = int(args.treble_freq) if args.treble_freq else 5000
        if treble_boost and not args.treble_gain:
            tg = ask_choice("Treble boost (dB):",
                {"1":"+3","2":"+6","3":"+9"},
                default_key="1")
            treble_gain_db = int(tg.replace("+", ""))
        if treble_boost and not args.treble_freq:
            tf = ask_choice("Treble center (Hz):",
                {"1":"4000","2":"5000","3":"6000","4":"8000"},
                default_key="2")
            treble_freq_hz = int(tf)

        if args.speed:
            speed_up_2x = (args.speed == "on")
        else:
            speed_up_2x = ask_yes_no("Speed up 2x (octave up, half length)?", default_yes=True)

        if args.loops:
            loop_find = (args.loops == "on")
        else:
            loop_find = ask_yes_no("Find loop points (basic zero-crossing)?", default_yes=True)

        cfg = {
            "rate": int(str(rate).split()[0]),
            "bits": 8 if bits == "8-bit" else 16,
            "mono_mode": mono_mode,
            "fade_mode": fade_mode,
            "trim_silence": trim_silence,
            "trim_threshold_db": trim_threshold_db,
            "trim_min_silence": trim_min_silence,
            "normalize": normalize,
            "gain_db": gain_db,
            "treble_boost": treble_boost,
            "treble_gain_db": treble_gain_db,
            "treble_freq_hz": treble_freq_hz,
            "speed_up_2x": speed_up_2x,
            "loop_find": loop_find,
            "sox_quiet": (args.sox_quiet == "on") if args.sox_quiet else ask_yes_no("Silence SoX warnings?", default_yes=True),
            "verbose": (args.verbose == "on") if args.verbose else ask_yes_no("Verbose output?", default_yes=False),
            "silent": args.silent,
            "report_peak": (args.report_peak == "on") if args.report_peak else False
        }

    # Apply overrides in preset mode (or if flags provided)
    if args.rate:
        cfg["rate"] = int(str(args.rate).split()[0])
    if args.bits:
        cfg["bits"] = 8 if args.bits == "8" else 16
    if args.mono:
        cfg["mono_mode"] = mono_label(args.mono)
    if args.fade:
        cfg["fade_mode"] = fade_label(args.fade)
    if args.trim:
        cfg["trim_silence"] = (args.trim == "on")
    if args.trim_threshold:
        cfg["trim_threshold_db"] = int(args.trim_threshold)
    if args.trim_min:
        cfg["trim_min_silence"] = float(args.trim_min)
    if args.normalize:
        cfg["normalize"] = (args.normalize == "on")
    if args.gain:
        cfg["gain_db"] = int(args.gain)
    if args.treble:
        cfg["treble_boost"] = (args.treble == "on")
    if args.treble_gain:
        cfg["treble_gain_db"] = int(args.treble_gain)
    if args.treble_freq:
        cfg["treble_freq_hz"] = int(args.treble_freq)
    if args.speed:
        cfg["speed_up_2x"] = (args.speed == "on")
    if args.loops:
        cfg["loop_find"] = (args.loops == "on")
    if args.sox_quiet:
        cfg["sox_quiet"] = (args.sox_quiet == "on")
    if args.verbose:
        cfg["verbose"] = (args.verbose == "on")
    if args.report_peak:
        cfg["report_peak"] = (args.report_peak == "on")

    if args.loops:
        cfg["loop_find"] = (args.loops == "on")

    if args.export_mod:
        export_mod = (args.export_mod == "on")
    elif args.preset:
        export_mod = True
    else:
        export_mod = ask_yes_no("Export MOD sample container?", default_yes=True)

    mod_samples = []

    say("\n--- PROCESSING ---\n")

    files = [f for f in os.listdir(inp) if f.lower().endswith(".wav")]

    if not files:
        say("No WAV files found.")
        return

    for f in files:
        in_path = os.path.join(inp, f)
        name = clean_name(f)
        out_path = os.path.join(out, name + ".wav")

        try:
            run_sox(in_path, out_path, cfg)
            say(f"OK: {name}")
            if cfg.get("report_peak") and not cfg.get("silent"):
                report_peak_dbfs(out_path, name)

            if export_mod:
                try:
                    sample = wav_to_mod_sample(
                        out_path,
                        loop_find=cfg.get("loop_find"),
                        rate_hz=cfg["rate"]
                    )
                    mod_samples.append({
                        "name": name,
                        **sample
                    })
                except Exception as e:
                    say(f"MOD SKIP: {name} - {e}")

        except subprocess.CalledProcessError:
            say(f"FAIL: {name}")

    if export_mod:
        mod_path = os.path.join(out, "sample_pack.mod")
        write_mod(mod_path, mod_samples)
        say(f"\nMOD CREATED: {mod_path}")

    if args.silent:
        print("Conversion done.")
    else:
        print("\nDONE.")


if __name__ == "__main__":
    main()
