# Astronomy: FITS to DNG & ZWO ASI Capture

Tools for converting astronomy camera data to Adobe DNG format using [muimg](https://github.com/mu-files/mu-image).

## fits2dng.py — Convert FITS to DNG

Converts FITS CFA (Color Filter Array) files to DNG with full metadata mapping.

### Features

- **Compression**: Support for Uncompressed, JPEG lossless, JPEG XL lossless/lossy DNGs
- **Preview**: Optional embedded JPEG preview for instant thumbnails
- **Camera-specific metadata**: Gain→ISO conversion, white balance (AnalogBalance) for ZWO ASI676MC


### Usage

```bash
# Basic conversion
python fits2dng.py input.FIT

# With compression and preview
python fits2dng.py input.FIT --compression jxl_lossless --preview

# Specify output path
python fits2dng.py input.FIT -o output.dng

# Print FITS header info (no conversion)
python fits2dng.py input.FIT --info
```

### Options

```
--pattern       Bayer pattern: RGGB, BGGR, GRBG, GBRG (default: RGGB)
--compression   uncompressed, jpeg_lossless, jxl_lossless, jxl_lossy
--workers       Number of compression workers (default: 1)
--preview       Generate embedded JPEG preview
-o, --output    Output DNG path (default: same name with .dng extension)
--info          Print FITS header and exit
```

### Supported Cameras

| Camera | ISO | White Balance | Notes |
|--------|-----|---------------|-------|
| ZWO ASI676MC | Gain table interpolation | Non-linear blue + linear red | Calibrated neutral at (80, 100) |
| Other | Raw gain value | Neutral (1, 1, 1) | Fallback for unknown cameras |

---

## zwo_capture.py — Live ZWO ASI Capture to DNG

Captures a single raw frame from a connected ZWO ASI camera and saves directly to DNG.

### Features

- Configurable exposure, gain, offset, white balance
- Optional compression and preview

### Usage

```bash
# Default capture (100ms, gain 50, WB 55/75)
python zwo_capture.py

# Custom settings with preview
python zwo_capture.py --exposure 500 --gain 100 --wb-r 55 --wb-b 75 --preview -o capture.dng

# With JPEG XL compression
python zwo_capture.py --exposure 1000 --gain 150 --compression jxl_lossless -o deep.dng
```

### Options

```
--exposure      Exposure time in milliseconds (default: 100)
--gain          Camera gain (default: 50)
--offset        Camera offset/black level (default: 1)
--wb-r          White balance red (default: 55)
--wb-b          White balance blue (default: 75)
--compression   uncompressed, jpeg_lossless, jxl_lossless, jxl_lossy
--workers       Number of compression workers (default: 1)
--preview       Generate embedded JPEG preview
-o, --output    Output DNG path (default: capture.dng)
```

### Working with the DNG in muimg

Use `muimg` to inspect and render the created DNGs:

```bash
# Inspect metadata
muimg dng metadata file.dng

# Render to TIFF with custom development parameters
muimg dng convert file.dng file.tif --temperature 5500 --tint 10 --exposure 1.5

# Batch convert a folder of DNGs to 16-bit TIFFs
muimg dng batch-convert ./captures/ ./output/ --format tif --bit-depth 16 \
    --temperature 5500 --tint 10 --exposure 1.5 --num-workers 4

# Batch convert with per-file settings from CSV
muimg dng batch-convert settings.csv ./output/ --format tif --bit-depth 16
```

The CSV file format for per-file settings:

```csv
filename,Temperature,Tint,Exposure2012,orientation
capture_001.dng,5500,10,1.5,
capture_002.dng,6500,0,2.0,
```

### SDK Setup

The ZWO ASI SDK library must be accessible. The script searches these locations:

1. `ZWO_ASI_LIB` environment variable
2. `/Applications/ASIStudio.app/Contents/Frameworks/libASICamera2.dylib` (macOS)
3. `/usr/local/lib/libASICamera2.so` (Linux)

## Installation

```bash
cd mu-rasppi
python3 -m venv venv
venv/bin/pip install -e ".[astro]"
```

This installs `muimg`, `astropy`, `numpy`, and `zwoasi`.

## DNG Output

The generated DNGs include:

- **UniqueCameraModel** — Camera name from FITS `INSTRUME` header or SDK
- **ExposureTime** — Exposure in seconds
- **ISOSpeedRatings** — Computed from gain using camera-specific e-/ADU table
- **AnalogBalance** — White balance per-channel multipliers
- **BlackLevel / WhiteLevel** — From FITS headers or camera offset
- **BaselineExposure** — Auto-calculated from image histogram
- **ProfileToneCurve** — Linear (bypasses Adobe Camera Raw default curve)
- **XMP ToneCurvePV2012** — S-curve contrast

### macOS Apple Silicon Note

The ZWO ASI SDK is x86_64-only. On Apple Silicon Macs you must create an x86_64 virtual environment that runs under Rosetta:

```bash
# Create x86_64 venv (requires x86 Python via Homebrew under Rosetta)
arch -x86_64 /usr/local/bin/python3 -m venv venv-x86
venv-x86/bin/pip install -e ".[astro]"

# Run capture under Rosetta
venv-x86/bin/python zwo_capture.py
```

If you don't have an x86_64 Python, install one with:

```bash
arch -x86_64 /usr/local/bin/brew install python@3.13
```

> **Note**: `fits2dng.py` does not require the ZWO SDK and works natively on Apple Silicon.

