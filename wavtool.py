#!/usr/bin/env python3

import subprocess
import sys
import argparse


def run(cmd):
    print("CMD:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main():
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--prefix", dest="prefix", help="Chop output prefix")
    parser.add_argument("-i", "--input", dest="input_path", help="Input file for chopping")
    parser.add_argument("--chop-out", dest="chop_out", help="Chop output folder")
    parser.add_argument("--convert-out", dest="convert_out", help="Converted output folder")
    parser.add_argument("--clean", action="store_true",
                        help="Delete existing output files in chop/convert folders")
    parser.add_argument("--threshold", dest="threshold", help="Chop silence threshold (dB, e.g. -40)")
    parser.add_argument("--loops", dest="loops", choices=["on", "off"],
                        help="Loop-point detection for MOD export (on/off)")
    parser.add_argument("--rate", dest="rate", help="Sample rate for conversion (e.g. 16574)")
    parser.add_argument("--bits", dest="bits", choices=["8", "16"], help="Bit depth for conversion")
    parser.add_argument("--mono", dest="mono", choices=["mix", "left", "right"],
                        help="Mono mode for conversion")
    parser.add_argument("--fade", dest="fade", choices=["off", "veryshort", "short", "medium"],
                        help="Anti-click envelope for conversion")
    parser.add_argument("--trim", dest="trim", choices=["on", "off"],
                        help="Trim silence for conversion")
    parser.add_argument("--trim-threshold", dest="trim_threshold",
                        help="Trim threshold dB for conversion")
    parser.add_argument("--trim-min", dest="trim_min",
                        help="Trim minimum silence length for conversion")
    parser.add_argument("--normalize", dest="normalize", choices=["on", "off"],
                        help="Normalize for conversion")
    parser.add_argument("--gain", dest="gain", help="Gain dB for conversion (used if normalize off)")
    parser.add_argument("--treble", dest="treble", choices=["on", "off"],
                        help="Treble boost for conversion")
    parser.add_argument("--treble-gain", dest="treble_gain", help="Treble boost dB")
    parser.add_argument("--treble-freq", dest="treble_freq", help="Treble center frequency Hz")
    parser.add_argument("--speed", dest="speed", choices=["on", "off"],
                        help="Speed up 2x for conversion")
    parser.add_argument("--sox-quiet", dest="sox_quiet", choices=["on", "off"],
                        help="Silence SoX warnings for conversion")
    parser.add_argument("--verbose", dest="verbose", choices=["on", "off"],
                        help="Verbose output for conversion")
    parser.add_argument("--export-mod", dest="export_mod", choices=["on", "off"],
                        help="Export MOD container")
    args, _ = parser.parse_known_args()

    chop_out = args.chop_out if args.chop_out else "chopped"
    convert_out = args.convert_out if args.convert_out else "converted"

    # 1) Chop into ./chopped (uses wavchop preset, no prompts)
    chop_cmd = [sys.executable, "wavchop.py", "-o", chop_out, "-p"]
    if args.input_path:
        chop_cmd += ["-i", args.input_path]
    if args.prefix:
        chop_cmd += ["--prefix", args.prefix]
    if args.threshold:
        chop_cmd += ["--threshold", args.threshold]
    if args.clean:
        chop_cmd += ["--clean"]
    run(chop_cmd)

    # 2) Convert chopped -> converted using preset without prompts
    conv_cmd = [sys.executable, "wav2mod.py", "-i", chop_out, "-o", convert_out, "-p"]
    if args.loops:
        conv_cmd += ["--loops", args.loops]
    if args.rate:
        conv_cmd += ["--rate", args.rate]
    if args.bits:
        conv_cmd += ["--bits", args.bits]
    if args.mono:
        conv_cmd += ["--mono", args.mono]
    if args.fade:
        conv_cmd += ["--fade", args.fade]
    if args.trim:
        conv_cmd += ["--trim", args.trim]
    if args.trim_threshold:
        conv_cmd += ["--trim-threshold", args.trim_threshold]
    if args.trim_min:
        conv_cmd += ["--trim-min", args.trim_min]
    if args.normalize:
        conv_cmd += ["--normalize", args.normalize]
    if args.gain:
        conv_cmd += ["--gain", args.gain]
    if args.treble:
        conv_cmd += ["--treble", args.treble]
    if args.treble_gain:
        conv_cmd += ["--treble-gain", args.treble_gain]
    if args.treble_freq:
        conv_cmd += ["--treble-freq", args.treble_freq]
    if args.speed:
        conv_cmd += ["--speed", args.speed]
    if args.sox_quiet:
        conv_cmd += ["--sox-quiet", args.sox_quiet]
    if args.verbose:
        conv_cmd += ["--verbose", args.verbose]
    if args.export_mod:
        conv_cmd += ["--export-mod", args.export_mod]
    if args.clean:
        conv_cmd += ["--clean"]
    run(conv_cmd)


if __name__ == "__main__":
    main()
