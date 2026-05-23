# Raspberry Pi DNG Writing Benchmark

Performance comparison of DNG writing libraries for Raspberry Pi cameras, demonstrating **muimg's speed, compression, and features** compared to PiDNG.

Tested on **Raspberry Pi 5 Model B** with Raspberry Pi HQ Camera (IMX477 sensor) capturing 4064×3040 pixel, 16-bit raw images.

## Benchmark Results

```
===================================================================================================================================
BENCHMARK RESULTS
===================================================================================================================================
Library  Compression            Work  Dest     Time(ms)     Size(MB)   Ratio    Throughput(MB/s) FPS     
-----------------------------------------------------------------------------------------------------------------------------------
pidng    uncompressed                 file       41.7± 3.4     23.52     1.0x           564.6   23.96
pidng    lj92                         file      422.8± 2.2     16.46     1.4x            55.7    2.37
muimg    uncompressed           w=1   file       25.2±15.1     23.57     1.0x           933.4   39.61
muimg    jpeg_lossless          w=1   file      620.4± 2.6     15.43     1.5x            38.0    1.61
muimg    jpeg_lossless          w=2   file      318.8± 0.8     15.43     1.5x            73.9    3.14
muimg    jpeg_lossless          w=4   file      171.2± 0.2     15.43     1.5x           137.6    5.84
muimg    jxl_lossless           w=1   file      575.6± 4.1      9.08     2.6x            40.9    1.74
muimg    jxl_lossless           w=2   file      336.9± 6.9      9.08     2.6x            69.9    2.97
muimg    jxl_lossless           w=4   file      265.9± 2.9      9.08     2.6x            88.6    3.76
muimg    jxl_lossy              w=1   file      923.4± 1.7      0.62    37.7x            25.5    1.08
muimg    jxl_lossy              w=2   file      583.1± 4.1      0.62    37.7x            40.4    1.72
muimg    jxl_lossy              w=4   file      486.6± 5.0      0.62    37.7x            48.4    2.05
muimg    uncompressed+preview   w=1   file      444.8± 2.7     23.74     1.0x            53.0    2.25
muimg    jxl_lossless+preview   w=4   file      693.2± 1.1      9.25     2.5x            34.0    1.44
muimg    jxl_lossy+preview      w=4   file      918.6± 6.1      0.80    29.5x            25.7    1.09
===================================================================================================================================
```

**Key Findings:**
- **muimg uncompressed is 1.7× faster** than PiDNG (25ms vs 42ms)
- **Multi-core compression scales well**: 4 workers achieve 3.6× speedup for JPEG lossless
- **JPEG XL lossless** provides 2.6× compression with reasonable speed (266ms with 4 workers)
- **JPEG XL lossy** achieves 38× compression for applications where slight quality loss is acceptable
- **Preview generation** adds ~430ms to render a color-corrected JPEG preview embedded in the DNG, enabling instant thumbnails in file browsers and photo applications

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
- Python 3.12+
- picamera2 installed system-wide

### Setup

```bash
# Clone this repository
git clone https://github.com/mu-files/mu-rasppi.git
cd mu-rasppi

# Create virtual environment with system site packages (for picamera2)
python3 -m venv --system-site-packages venv

# Install dependencies
venv/bin/pip install .
```

**Note**: muimg is installed directly from the main branch of the mu-image repository.

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
- **OS**: Debian GNU/Linux 13 (trixie) 64-bit

## License

MIT License - See LICENSE file for details.

## Credits

- **muimg**: https://github.com/mu-files/mu-image
- **PiDNG**: https://github.com/schoolpost/PiDNG
- **picamera2**: https://github.com/raspberrypi/picamera2
