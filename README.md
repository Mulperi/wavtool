# WAV2MOD + WAVCHOP Toolkit

This toolkit was created with the help of an AI assistant.

## Overview
This repo provides three scripts:
- `wav2mod.py`: Convert WAV files to tracker-friendly WAVs and optionally pack them into a ProTracker-compatible MOD sample container.
- `wavchop.py`: Auto-slice a long WAV into multiple files based on silence detection.
- `wavtool.py`: Hands-off pipeline that runs chopping first, then conversion with preset settings.

## Requirements
- Python 3
- SoX installed
  - macOS: `brew install sox`
  - Debian/Ubuntu: `apt install sox`

## Quick Start (Hands-Off)
Run the full pipeline with defaults:
```bash
python3 wavtool.py
```

Optional:
```bash
python3 wavtool.py --clean --prefix drums
```

Without any flags, `wavtool.py` will:
- Use the first `.wav` found in the current folder (for chopping)
- Chop into `chopped/` using `wavchop.py` preset defaults
- Convert into `converted/` using `wav2mod.py` preset defaults
- Export a MOD sample pack

## wavtool.py
Runs:
1. `wavchop.py` (auto defaults, no prompts)
2. `wav2mod.py` (ProTracker preset, no prompts)

Flags:
- `-i/--input`: input file for chopping
- `--prefix`: output name prefix for chops (e.g., `drums-1.wav`)
- `--chop-out`: output folder for chopped files (default `chopped`)
- `--convert-out`: output folder for converted files (default `converted`)
- `--threshold`: silence threshold in dB for chopping (e.g., `-40`)
- `--loops`: loop-point detection for MOD export (`on` or `off`)
- `--rate`: sample rate for conversion (e.g., `16574`)
- `--bits`: bit depth for conversion (`8` or `16`)
- `--mono`: mono mode for conversion (`mix`, `left`, `right`)
- `--fade`: anti-click envelope for conversion (`off`, `veryshort`, `short`, `medium`)
- `--trim`: trim silence for conversion (`on` or `off`)
- `--trim-threshold`: trim threshold dB for conversion (e.g., `-30`)
- `--trim-min`: trim minimum silence length for conversion (e.g., `0.05`)
- `--normalize`: normalize for conversion (`on` or `off`)
- `--gain`: gain dB for conversion (used if normalize off)
- `--treble`: treble boost for conversion (`on` or `off`)
- `--treble-gain`: treble boost dB for conversion
- `--treble-freq`: treble center frequency Hz for conversion
- `--speed`: speed up 2x for conversion (`on` or `off`)
- `--sox-quiet`: silence SoX warnings for conversion (`on` or `off`)
- `--verbose`: verbose output for conversion (`on` or `off`)
- `--export-mod`: export MOD container (`on` or `off`)
- `--clean`: delete output folders before running

## wavchop.py
Auto-slices based on silence detection.

Default behavior:
- Finds the first `.wav` in the current folder if no input is provided
- Output folder defaults to `chopped`
- Output name prefix defaults to `chop`
- Silence threshold default: `-30 dB`
- Minimum silence length default: `0.05 s`

Examples:
```bash
python3 wavchop.py
python3 wavchop.py -i mylong.wav -o chopped --prefix drums
python3 wavchop.py -p --clean
```

Flags:
- `-i/--input`: input WAV file
- `-o/--output`: output folder
- `--prefix`: output name prefix
- `--threshold`: silence threshold in dB (e.g., `-40`)
- `--min-sil`: minimum silence length in seconds (e.g., `0.05`)
- `--keep-sil`: keep trailing silence (`on` or `off`)
- `--verbose`: verbose SoX output (`on` or `off`)
- `--remove-empty`: remove empty slices (`on` or `off`)
- `-p/--preset`: use defaults and skip prompts
- `--clean`: delete output folder before slicing

## wav2mod.py
Converts WAV files to tracker-friendly WAVs and can export a sample-pack MOD.

Amiga preset defaults:
- Sample rate: `16574 Hz (PAL C-4)`
- Bit depth: `8-bit`
- Mono mix: L+R
- Fade: off
- Trim silence: on (`-30 dB`, `0.05 s`)
- Normalize: on
- Treble boost: off
- Speed up 2x (octave up, half length): on
- Loop find (basic zero-crossing): on
- SoX warnings: silenced
- MOD export: on

Examples:
```bash
python3 wav2mod.py
python3 wav2mod.py -i chopped -o converted -p --clean
```

Flags:
- `-i/--input`: input folder
- `-o/--output`: output folder
- `-p/--preset`: use preset and skip prompts
- `--loops`: loop-point detection for MOD export (`on` or `off`)
- `--rate`: sample rate (e.g., `16574`)
- `--bits`: bit depth (`8` or `16`)
- `--mono`: mono mode (`mix`, `left`, `right`)
- `--fade`: anti-click envelope (`off`, `veryshort`, `short`, `medium`)
- `--trim`: trim silence (`on` or `off`)
- `--trim-threshold`: trim threshold dB (e.g., `-30`)
- `--trim-min`: trim minimum silence length in seconds (e.g., `0.05`)
- `--normalize`: normalize (`on` or `off`)
- `--gain`: gain in dB (used if normalize off)
- `--treble`: high-frequency boost (`on` or `off`)
- `--treble-gain`: treble boost in dB (e.g., `3`)
- `--treble-freq`: treble center frequency in Hz (e.g., `5000`)
- `--speed`: speed up 2x (`on` or `off`)
- `--sox-quiet`: silence SoX warnings (`on` or `off`)
- `--verbose`: verbose output (`on` or `off`)
- `--export-mod`: export MOD container (`on` or `off`)
- `--clean`: delete output folder before converting

## Notes
- If trimmed output becomes empty, `wav2mod.py` retries once without trimming.
- PT2/ProTracker playback does not store sample rate; pitch depends on the note you play.
- Tip: If your samples have long decays, try lowering the chop threshold (e.g., `--threshold -50`) to avoid cutting tails too early.
