# .stk File Format Specification

The `.stk` file is a drum kit container format used by the SmplTrek hardware synthesizer. It bundles up to 15 WAV samples into a single file, along with metadata and internal path information.

## 1. Overall Structure

| Section | Offset (Hex) | Size (Bytes) | Description |
| :--- | :--- | :--- | :--- |
| **Main Header** | `0x0000` | 32 (`0x20`) | File magic, offsets, and global metadata. |
| **KTDT Chunk** | `0x0020` | 4228 (`0x1084`) | Metadata for 15 pads and the first sample's metadata block. |
| **Audio Section** | `0x10A4` | Variable | Concatenated `ISDT` blocks and `RIFF/WAVE` files. |

---

## 2. Main Header (32 bytes)

| Offset | Size | Type | Value / Description |
| :--- | :--- | :--- | :--- |
| `0x00` | 8 | Bytes | `"VDK0PR \x00"` (Magic signature) |
| `0x08` | 4 | Zeros | Reserved |
| `0x0C` | 4 | uint32_le | `0x00000010` (Offset to `KTDT` tag?) |
| `0x10` | 4 | Bytes | `"KTDT"` (Chunk Tag) |
| `0x14` | 4 | uint32_le | `0x00001084` (Size of the `KTDT` body) |
| `0x18` | 4 | Zeros | Reserved |
| `0x1C` | 4 | uint32_le | `0x00000001` (Version / Marker) |

---

## 3. KTDT Chunk Body (4228 bytes)

The `KTDT` body (starting at `0x20`) contains 15 pad entries, a 12-byte footer, and the metadata block for the first sample.

### 3.1 Pad Entries (15 × 280 bytes = 4200 bytes)
Each entry represents one of the 15 pads (0-14).

| Offset (rel) | Size | Type | Description |
| :--- | :--- | :--- | :--- |
| `0x000` | 256 | String | Internal Path: `SmplTrek/Pool/Audio/Drum/<KitTitle>/<Sample>.wav\x00` |
| `0x100` | 1 | int8 | Volume (0-100, default 100) |
| `0x101` | 1 | int8 | Pan (-64 to 63, default 0=center) |
| `0x102` | 1 | Zero | Reserved |
| `0x103` | 1 | uint8 | Reserved (Value `0x7F` seen in factory kits, maybe important for stability) |
| `0x104` | 4 | int32_le | Pitch (Cents, range -1200 to 1200) |
| `0x108` | 8 | Zeros | Padding |
| `0x110` | 1 | uint8 | FX Send (0-127, default 0) |
| `0x111` | 7 | Zeros | Reserved/Unused |

### 3.2 KTDT Footer (12 bytes)

Starts at offset `0x20 + 4200 = 0x1088`.

| Offset (rel) | Size | Type | Value / Description |
| :--- | :--- | :--- | :--- |
| `0x00` | 8 | Zeros | Padding |
| `0x08` | 4 | uint32_le | `0x00000064` (Likely a global volume/level parameter) |

### 3.3 First ISDT Block (16 bytes)

Starts at offset `0x20 + 4212 = 0x1094`. This is the `ISDT` block for **Sample 1** (Index 0). Its structure is identical to other `ISDT` blocks but it is embedded within the `KTDT` chunk.

---

## 4. ISDT Block (16 bytes)

Each WAV file in the kit is preceded by a 16-byte metadata block.

| Offset | Size | Type | Description |
| :--- | :--- | :--- | :--- |
| `0x00` | 4 | Bytes | `"ISDT"` |
| `0x04` | 4 | uint32_le | **ISDT Size Field** (See formula below) |
| `0x08` | 4 | uint32_le | Pad Index (0-14) |
| `0x0C` | 4 | uint32_le | `0x00000001` (Constant) |

### **The ISDT Size Formula**
The value in the `ISDT` size field (at offset `0x04`) is calculated relative to the subsequent WAV file:
`ISDT_SIZE_FIELD = WAV_FILE_TOTAL_SIZE + 10`
*Alternatively (based on RIFF size):*
`ISDT_SIZE_FIELD = RIFF_CHUNK_SIZE + 18`

---

## 5. Audio Section (Starting at 0x10A4)

The audio data consists of 15 WAV files concatenated. Each file (except the first) is preceded by two null bytes and an `ISDT` block.

### Layout:
1. **Sample 1 (Index 0):**
   - *ISDT for Sample 1 is already at `0x1094` (inside KTDT).*
   - Full `RIFF/WAVE` file data starting at `0x10A4`.
2. **Samples 2 to 15 (Index 1 to 14):**
   - 2 bytes: `0x00 0x00` (Alignment/Separator).
   - 16 bytes: `ISDT` block for this index.
   - Full `RIFF/WAVE` file data.
3. **End of File:**
   - 2 bytes: `0x00 0x00` (Footer/Alignment).

### WAV Requirements
The device expects a specific WAV structure for compatibility:
- **Format:** PCM Linear, 48 kHz, 16-bit. (Stereo or Mono).
- **Required Chunks:**
  - `fmt ` chunk.
  - `cue ` chunk (28 bytes).
  - `LIST` chunk (30 bytes, typically containing `adtllabl` with a `Tempo` string).
  - `data` chunk.

Example Extra Chunks (Hex):
```
cue: 63 75 65 20 1c 00 00 00 01 00 00 00 01 00 00 00 00 00 00 00 64 61 74 61 00 00 00 00 00 00 00 00 00 00 00 00
LIST: 4c 49 53 54 1e 00 00 00 61 64 74 6c 6c 61 62 6c 12 00 00 00 01 00 00 00 54 65 6d 70 6f 3a 20 30 30 30 2e 30 00 00
```
