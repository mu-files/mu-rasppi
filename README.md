# Raspberry Pi DNG Writing Benchmark

Performance comparison of DNG writing libraries for Raspberry Pi cameras, demonstrating **muimg's speed, compression, and features** compared to PiDNG.

Tested on **Raspberry Pi 5 Model B** with Raspberry Pi HQ Camera (IMX477 sensor) capturing 4064×3040 pixel, 16-bit raw images.

## Benchmark Results

```
Library  Compression            Work   Time(ms)    FPS   Size(MB)  Ratio
-------------------------------------------------------------------------
pidng    uncompressed                   39.9±3.4  25.08    23.52    1.0x
pidng    lj92                          429.2±2.8   2.33    17.21    1.4x
muimg    uncompressed           w=1     21.6±12.2 46.19    23.57    1.0x
muimg    jpeg_lossless          w=1    639.2±3.4   1.56    16.45    1.4x
muimg    jpeg_lossless          w=2    329.1±1.4   3.04    16.45    1.4x
muimg    jpeg_lossless          w=4    175.3±1.3   5.70    16.45    1.4x
muimg    jxl_lossless           w=1    588.8±2.3   1.70     9.89    2.4x
muimg    jxl_lossless           w=2    356.6±2.4   2.80     9.89    2.4x
muimg    jxl_lossless           w=4    271.6±3.6   3.68     9.89    2.4x
muimg    jxl_lossy              w=1   1028.2±3.9   0.97     1.14   20.7x
muimg    jxl_lossy              w=2    618.6±2.8   1.62     1.14   20.7x
muimg    jxl_lossy              w=4    509.4±5.1   1.96     1.14   20.7x
muimg    uncompressed+preview   w=1    447.9±3.5   2.23    23.80    1.0x
muimg    jxl_lossless+preview   w=4    701.4±4.1   1.43    10.12    2.3x
muimg    jxl_lossy+preview      w=4    943.6±3.2   1.06     1.37   17.2x
```

**Key Findings:**
- **muimg uncompressed is 1.8× faster** than PiDNG (22ms vs 40ms)
- **Multi-core compression scales well**: 4 workers achieve 3.6× speedup for JPEG lossless
- **JPEG XL lossless** provides 2.4× compression with reasonable speed (272ms with 4 workers)
- **JPEG XL lossy** achieves 21× compression for applications where slight quality loss is acceptable
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
venv/bin/python picamera2_capture.py --mode benchmark --iterations 10

# Single capture with preview generation
venv/bin/python picamera2_capture.py -v --mode single --preview
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
