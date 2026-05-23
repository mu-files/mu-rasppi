# Raspberry Pi DNG Writing Benchmark

Performance comparison of DNG writing libraries for Raspberry Pi cameras, demonstrating **muimg's speed, compression, and features** compared to PiDNG.

Tested on **Raspberry Pi 5 Model B** with Raspberry Pi HQ Camera (IMX477 sensor) capturing 4064×3040 pixel, 16-bit raw images.

## Benchmark Results

```
Library  Compression            Work   Time(ms)    FPS   Size(MB)  Ratio
-------------------------------------------------------------------------
pidng    uncompressed                   41.7±3.4  23.96    23.52    1.0x
pidng    lj92                          422.8±2.2   2.37    16.46    1.4x
muimg    uncompressed           w=1     25.2±15.1 39.61    23.57    1.0x
muimg    jpeg_lossless          w=1    620.4±2.6   1.61    15.43    1.5x
muimg    jpeg_lossless          w=2    318.8±0.8   3.14    15.43    1.5x
muimg    jpeg_lossless          w=4    171.2±0.2   5.84    15.43    1.5x
muimg    jxl_lossless           w=1    575.6±4.1   1.74     9.08    2.6x
muimg    jxl_lossless           w=2    336.9±6.9   2.97     9.08    2.6x
muimg    jxl_lossless           w=4    265.9±2.9   3.76     9.08    2.6x
muimg    jxl_lossy              w=1    923.4±1.7   1.08     0.62   37.7x
muimg    jxl_lossy              w=2    583.1±4.1   1.72     0.62   37.7x
muimg    jxl_lossy              w=4    486.6±5.0   2.05     0.62   37.7x
muimg    uncompressed+preview   w=1    444.8±2.7   2.25    23.74    1.0x
muimg    jxl_lossless+preview   w=4    693.2±1.1   1.44     9.25    2.5x
muimg    jxl_lossy+preview      w=4    918.6±6.1   1.09     0.80   29.5x
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
