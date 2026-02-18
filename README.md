# STK Writer and Unpacker Tools
Utilities to pack and write stk files for use in Sonicware devices

## Disclaimer
This is not any sort of official Sonicware product. This script is provided for
educational and personal purposes only by a passionate Sonicware fan. Please support
the Sonicware community by purchasing official devices and/or support the developers
of Sonicware products.

## Features
- Packs up to 15 WAV files into a single `.stk` kit.
- Automatically converts audio to the required format (48kHz, 16-bit PCM, Stereo or Mono).
- Sets internal paths to `SmplTrek/Pool/Audio/Drum/` for maximum compatibility with SmplTrek.

## Usage

### Prerequisites
- Python 3.9 or later.

### Installation
No installation is required. Just run the script directly from the repository.

### Commands

You can pack WAV files either by specifying a folder or by listing individual files.

```bash
python3 stkpack.py --title "MyKit" --folder /path/to/wavs
```

or

```bash
python3 stkpack.py --title "MyKit" sample1.wav sample2.wav sample3.wav
```

#### Arguments
- `--title`: (Required) The title of the kit. This will be shown in the device UI and used for internal file naming.
- `--folder`: Path to a folder containing WAV files. The first 15 files (alphabetically) will be selected.
- `files`: Positional arguments for individual WAV files (up to 15).
- `-o`, `--output`: (Optional) The output path for the `.stk` file. Defaults to `{timestamp}_kit.stk`.
- `--stereo`: (Optional) Convert audio to stereo (default).
- `--mono`: (Optional) Convert audio to mono, this will save space.
- `--customize`: (Optional) Interactively adjust Volume, Pitch, Pan, and FX Send for each sample.

### Sample Invocations

**Using a folder of samples with interactive customization:**
```bash
python3 stkpack.py --title "MyKit" --folder "samples/" --customize
```
During customization, you can:
- Press **Enter** to accept the default value.
- Type a value and press **Enter** to change it.
- Press **p** then **Enter** to hear a preview of the current sample.

**Using specific files:**
```bash
python3 stkpack.py --title "CustomKit" kick.wav snare.wav hihat.wav -o "Custom.stk"
```

**Minimal invocation (outputs to current directory with timestamp):**
```bash
python3 stkpack.py --title "MyNewKit" --folder "samples/"
```
# Using with the ELZ_1 Play (v2)

Copy the generated `.stk` file to the `ELZ_1 play/Kit/` folder of the SD card. The original audio files do not need to
be separately copied as they are contained within the `stk` file. Eject the SD card from your PC then
insert the device into the Play. Power on the Play. The kitss will be found within the "CARD" type of kit selection when
using the STK_DRUMMER synth type.

## Unpacking

A `.stk` file can be unpacked into its source samples using the included `extract_wavs.py` script.