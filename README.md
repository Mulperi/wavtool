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

## wavtool.py
Runs:
1. `wavchop.py` (auto defaults, no prompts)
2. `wav2mod.py` (ProTracker preset, no prompts)

Flags:
- `-i/--input`: input file for chopping
- `--prefix`: output name prefix for chops (e.g., `drums-1.wav`)
- `--chop-out`: output folder for chopped files (default `chopped`)
- `--convert-out`: output folder for converted files (default `converted`)
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
- `-p/--preset`: use defaults and skip prompts
- `--clean`: delete output folder before slicing

## wav2mod.py
Converts WAV files to tracker-friendly WAVs and can export a sample-pack MOD.

Amiga preset defaults:
- Sample rate: `16574 Hz (PAL C-4)`
- Bit depth: `8-bit`
- Mono mix: L+R
- Fade: very short (5 ms)
- Trim silence: on (`-40 dB`, `0.05 s`)
- Normalize: on
- Treble boost: off
- Speed up 2x (octave up, half length): on
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
- `--clean`: delete output folder before converting

## Notes
- If trimmed output becomes empty, `wav2mod.py` retries once without trimming.
- PT2/ProTracker playback does not store sample rate; pitch depends on the note you play.

