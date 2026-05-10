# Raspberry Pi DNG Writing Benchmark

Performance comparison of DNG writing libraries for Raspberry Pi cameras, demonstrating **muimg's speed, compression, and features** compared to PiDNG.

Tested on **Raspberry Pi 5 Model B** with Raspberry Pi HQ Camera (IMX477 sensor) capturing 4064×3040 pixel, 16-bit raw images.

## Benchmark Results

```
=============================================================================================================================
BENCHMARK RESULTS
=============================================================================================================================
Library  Compression      Work  Dest     Time(ms)     Size(MB)   Ratio    Throughput(MB/s) FPS     
-----------------------------------------------------------------------------------------------------------------------------
pidng    uncompressed           file       35.5± 3.2     23.52     1.0x           664.3   28.19
pidng    lj92                   file      434.9± 2.3     16.84     1.4x            54.2    2.30
muimg    uncompressed     w=1   file       17.3± 5.8     23.57     1.0x          1358.4   57.65
muimg    jpeg_lossless    w=1   file      638.0± 2.2     16.07     1.5x            36.9    1.57
muimg    jpeg_lossless    w=2   file      326.6± 1.0     16.07     1.5x            72.2    3.06
muimg    jpeg_lossless    w=4   file      177.3± 2.2     16.07     1.5x           132.9    5.64
muimg    jxl_lossless     w=1   file      583.5± 1.1      9.62     2.5x            40.4    1.71
muimg    jxl_lossless     w=2   file      355.8±10.2      9.62     2.5x            66.2    2.81
muimg    jxl_lossless     w=4   file      261.4± 3.8      9.62     2.5x            90.1    3.83
muimg    jxl_lossy        w=1   file      947.9±10.1      0.87    27.1x            24.9    1.05
muimg    jxl_lossy        w=2   file      554.7± 8.4      0.87    27.1x            42.5    1.80
muimg    jxl_lossy        w=4   file      452.8± 3.4      0.87    27.1x            52.0    2.21
=============================================================================================================================
```

**Key Findings:**
- **muimg uncompressed is 2× faster** than PiDNG (17.3ms vs 35.5ms)
- **Multi-core compression scales well**: 4 workers achieve 3.6× speedup for JPEG lossless
- **JPEG XL lossless** provides 2.5× compression with reasonable speed (261ms with 4 workers)
- **JPEG XL lossy** achieves 27× compression for applications where slight quality loss is acceptable

## PiDNG vs muimg Comparison

### PiDNG Advantages
- **Minimal dependencies**: Very small install footprint, ideal for embedded systems
- **Raspberry Pi optimized**: Designed specifically for Pi cameras

### muimg Advantages
- **Faster encoding**: 2× faster uncompressed writes, scales with multi-core compression
- **Full-featured encode pipeline**: 
  - Tiled compression for parallel processing
  - JPEG lossless compression
  - JPEG XL lossless and lossy compression
  - Multi-core compression engine
  - Trade-off speed/compression/quality based on your needs
- **Embedded preview support**: Can generate JPEG preview images in DNG files
- **Full-featured decode pipeline**: Can render DNGs from ANY camera, not just Raspberry Pi
- **Better compression**: JPEG XL lossless achieves 2.5× compression vs PiDNG's LJ92 at 1.4×

## Installation

### Prerequisites
- Raspberry Pi with camera (tested on HQ Camera with IMX477 sensor)
- Python 3.11+
- picamera2 installed system-wide

### Setup

```bash
# Clone this repository
git clone https://github.com/YOUR_USERNAME/mu-rasppi.git
cd mu-rasppi

# Create virtual environment with system site packages (for picamera2)
/usr/bin/python3 -m venv --system-site-packages venv

# Install dependencies
venv/bin/pip install -e .
```

**Note**: The muimg dependency uses the `rasppi-compat` branch due to:
- **Python 3.11 compatibility**: Latest tifffile (with DNG bug fixes) requires Python 3.12+, but Raspberry Pi OS uses Python 3.11
- **numpy version constraints**: Raspberry Pi requires numpy <2.0 for ARM compatibility

This is handled automatically in `pyproject.toml`.

## Usage

```bash
# Run benchmark (10 iterations per scenario)
venv/bin/python picamera2_capture.py

# Results are displayed in console and saved to:
# - results/benchmark_picamera2_results.json
# - results/test_*.dng (sample DNG files from each scenario)
```

## Example Code

The benchmark script demonstrates how to use muimg for DNG writing with the Raspberry Pi camera. The main function `write_muimg()` in [`picamera2_capture.py`](picamera2_capture.py) shows:

- Extracting camera metadata from PiDNG's camera model
- Setting up compression with tiling for parallel processing
- Handling camera-specific optimizations (e.g., IMX477 crop regions)
- Using multi-core compression workers for better performance
- Supporting multiple compression formats (uncompressed, JPEG lossless, JPEG XL)

See the complete implementation at the top of [`picamera2_capture.py`](picamera2_capture.py) starting at line 25.

## Hardware

- **Device**: Raspberry Pi 5 Model B Rev 1.0
- **Camera**: Raspberry Pi HQ Camera (IMX477 sensor)
- **Image Size**: 4064×3040 pixels, 16-bit raw
- **OS**: Raspberry Pi OS (64-bit)

## License

MIT License - See LICENSE file for details.

## Credits

- **muimg**: https://github.com/mu-files/mu-image
- **PiDNG**: https://github.com/schoolpost/PiDNG
- **picamera2**: https://github.com/raspberrypi/picamera2
