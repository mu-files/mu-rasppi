# mu-rasppi

Example scripts for capturing and converting raw camera data to DNG using [muimg](https://github.com/mu-files/mu-image).

## Scripts

| Script | Description | Audience |
|--------|-------------|----------|
| [`fits2dng.py`](fits2dng.py) | Convert FITS CFA files to DNG | Astrophotography |
| [`zwo_capture.py`](zwo_capture.py) | Live capture from ZWO ASI cameras to DNG | Astrophotography |
| [`picamera2_capture.py`](picamera2_capture.py) | Picamera2 capture & DNG benchmark | Raspberry Pi |

## Documentation

- **[Astronomy / ZWO](docs/README_astro.md)** — FITS conversion and ZWO ASI live capture
- **[Raspberry Pi Camera](docs/README_picamera2.md)** — Picamera2 benchmark & DNG writing

## Installation

```bash
git clone https://github.com/mu-files/mu-rasppi.git
cd mu-rasppi
python3 -m venv venv
pip install -e ".[astro]"   # FITS + ZWO support (astropy, zwoasi)
pip install -e ".[pi]"      # Raspberry Pi support (picamera2, PiDNG)
```

## License

MIT License - See LICENSE file for details.

## Credits

- **muimg**: https://github.com/mu-files/mu-image
- **PiDNG**: https://github.com/schoolpost/PiDNG
- **picamera2**: https://github.com/raspberrypi/picamera2
- **zwoasi**: https://github.com/python-zwo/python-zwoasi
