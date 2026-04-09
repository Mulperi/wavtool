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
    if args.clean:
        conv_cmd += ["--clean"]
    run(conv_cmd)


if __name__ == "__main__":
    main()
