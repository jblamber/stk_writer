# stk_writer
A utility to pack and write stk files for use in Sonicware devices

## Features
- Packs up to 15 WAV files into a single `.stk` kit.
- Automatically converts audio to the required format (48kHz, 16-bit PCM, Stereo).
- Sets internal paths to `SmplTrek/Pool/Audio/Drum/` for compatibility with SmplTrek.

## Usage

### Prerequisites
- Python 3.9 or later.

### Installation
No installation is required. Just run the script directly from the repository.

### Commands

You can pack WAV files either by specifying a folder or by listing individual files.

```bash
python3 Pool/stkpack.py --title "MyKit" --folder /path/to/wavs
```

or

```bash
python3 Pool/stkpack.py --title "MyKit" sample1.wav sample2.wav sample3.wav
```

#### Arguments
- `--title`: (Required) The title of the kit. This will be shown in the device UI and used for internal file naming.
- `--folder`: Path to a folder containing WAV files. The first 15 files (alphabetically) will be selected.
- `files`: Positional arguments for individual WAV files (up to 15).
- `-o`, `--output`: (Optional) The output path for the `.stk` file. Defaults to `{timestamp}_kit.stk`.

### Sample Invocations

**Using a folder of samples:**
```bash
python3 Pool/stkpack.py --title "808Kit" --folder "Pool/Audio/Drum/01 - EPS 16+ 29" -o "MyKits/808.stk"
```

**Using specific files:**
```bash
python3 Pool/stkpack.py --title "CustomKit" kick.wav snare.wav hihat.wav -o "Custom.stk"
```

**Minimal invocation (outputs to current directory with timestamp):**
```bash
python3 Pool/stkpack.py --title "MyNewKit" --folder "samples/"
```
