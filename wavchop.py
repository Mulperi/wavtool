#!/usr/bin/env python3

import os
import shutil
import subprocess
import sys
import argparse


def check_sox():
    if not shutil.which("sox"):
        print("ERROR: SoX not found.")
        print("Install: brew install sox / apt install sox")
        sys.exit(1)


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


def ask_yes_no(q, default_yes=True):
    print("\n" + q)
    print("  1) Yes")
    print("  2) No")
    d = "1" if default_yes else "2"
    while True:
        a = input(f"Select [{d}]: ").strip()
        if a == "":
            a = d
        if a == "1":
            return True
        if a == "2":
            return False


def main():
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("-i", "--input", dest="input_path", help="Input file")
    parser.add_argument("-o", "--output", dest="output_path", help="Output folder")
    parser.add_argument("--prefix", dest="prefix", help="Output name prefix")
    parser.add_argument("-p", "--preset", action="store_true",
                        help="Use defaults and skip prompts")
    parser.add_argument("--clean", action="store_true",
                        help="Delete existing output files before chopping")
    parser.add_argument("--threshold", dest="threshold",
                        help="Silence threshold dB (e.g. -40)")
    parser.add_argument("--min-sil", dest="min_sil",
                        help="Minimum silence length in seconds (e.g. 0.05)")
    parser.add_argument("--keep-sil", dest="keep_sil", choices=["on", "off"],
                        help="Keep trailing silence on slices (on/off)")
    parser.add_argument("--verbose", dest="verbose", choices=["on", "off"],
                        help="Verbose SoX output (on/off)")
    parser.add_argument("--remove-empty", dest="remove_empty", choices=["on", "off"],
                        help="Remove empty slices (on/off)")
    args, _ = parser.parse_known_args()

    check_sox()
    print("=== WAVCHOP v1 ===\n")
    print("Tip: Place your input .wav in this folder or enter a full path.\n")

    default_inp = ""
    for f in os.listdir("."):
        if f.lower().endswith(".wav") and os.path.isfile(f):
            default_inp = f
            break

    if default_inp:
        inp_prompt = f"Input file [{default_inp}]: "
    else:
        inp_prompt = "Input file: "

    if args.input_path:
        inp = args.input_path
    elif args.preset and default_inp:
        inp = default_inp
    else:
        inp = input(inp_prompt).strip()
    if not inp and default_inp:
        inp = default_inp
    default_out = "chopped"
    out_prompt = f"Output folder [{default_out}]: "
    if args.output_path:
        out = args.output_path
    elif args.preset:
        out = default_out
    else:
        out = input(out_prompt).strip()
    if not out:
        out = default_out

    if not os.path.isfile(inp):
        print("ERROR: input file not found")
        sys.exit(1)

    if args.clean:
        try:
            if os.path.isdir(out):
                shutil.rmtree(out)
        except Exception:
            pass
    os.makedirs(out, exist_ok=True)

    if args.preset:
        thresh = "-40"
        min_sil = "0.05"
        keep_sil = False
    else:
        if args.threshold:
            thresh = args.threshold
        else:
            thresh = ask_choice("Silence threshold (dB):",
                {"1":"-30","2":"-40","3":"-50","4":"-60"},
                default_key="2")
        if args.min_sil:
            min_sil = args.min_sil
        else:
            min_sil = ask_choice("Minimum silence length (sec):",
                {"1":"0.05","2":"0.1","3":"0.2","4":"0.5"},
                default_key="1")
        if args.keep_sil:
            keep_sil = (args.keep_sil == "on")
        else:
            keep_sil = ask_yes_no("Keep the silence at the end of each chop?", default_yes=False)

    if args.threshold:
        thresh = args.threshold
    if args.min_sil:
        min_sil = args.min_sil
    if args.keep_sil:
        keep_sil = (args.keep_sil == "on")

    default_prefix = "chop"
    prefix_prompt = f"Output name prefix [{default_prefix}]: "
    if args.prefix:
        prefix = args.prefix
    elif args.preset:
        prefix = default_prefix
    else:
        prefix = input(prefix_prompt).strip()
        if not prefix:
            prefix = default_prefix
    pattern = os.path.join(out, prefix + "-%d.wav")

    if args.preset:
        verbose = False
        cleanup = True
    else:
        if args.verbose:
            verbose = (args.verbose == "on")
        else:
            verbose = ask_yes_no("Verbose SoX output?", default_yes=False)
        if args.remove_empty:
            cleanup = (args.remove_empty == "on")
        else:
            cleanup = ask_yes_no("Remove empty slices?", default_yes=True)

    if args.verbose:
        verbose = (args.verbose == "on")
    if args.remove_empty:
        cleanup = (args.remove_empty == "on")

    silence_args = ["silence"]
    if keep_sil:
        silence_args += ["-l"]
    silence_args += [
        "1", str(min_sil), f"{thresh}d",
        "1", str(min_sil), f"{thresh}d",
        ":",
        "newfile",
        ":",
        "restart"
    ]

    cmd = [
        "sox",
        "-V3" if verbose else "-V0",
        inp,
        pattern
    ] + silence_args

    print("\nCMD:", " ".join(cmd))
    subprocess.run(cmd, check=True)

    # List outputs for debugging
    created = []
    for f in os.listdir(out):
        if f.startswith(prefix + "-") and f.lower().endswith(".wav"):
            p = os.path.join(out, f)
            try:
                created.append((f, os.path.getsize(p)))
            except Exception:
                pass
    if created:
        print("\nCreated slices:")
        for f, sz in sorted(created):
            print(f"  {f} ({sz} bytes)")
    else:
        print("\nNo slices created.")

    if cleanup:
        # Remove empty/zero-length outputs by file size only.
        # Some SoX WAV variants don't parse with Python's wave module.
        removed = 0
        for f in os.listdir(out):
            if not f.startswith(prefix + "-") or not f.lower().endswith(".wav"):
                continue
            p = os.path.join(out, f)
            try:
                if os.path.getsize(p) <= 60:
                    os.remove(p)
                    removed += 1
            except Exception:
                pass

        if removed:
            print(f"\nRemoved {removed} empty slice(s).")
    print("\nDONE.")


if __name__ == "__main__":
    main()
