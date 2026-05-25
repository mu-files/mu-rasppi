#!/usr/bin/env python3
"""Convert FITS files containing CFA/Bayer data to DNG.

FITS (Flexible Image Transport System) is the standard file format in
astronomy. This script reads CFA data from a FITS file and writes it
as a DNG using the muimg library.

Requires the [astro] optional dependency:
    pip install -e ".[astro]"
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

try:
    from astropy.io import fits as astropy_fits
except ImportError:
    print(
        "ERROR: astropy is required but not installed.\n"
        "Install with: pip install -e \".[astro]\"",
        file=sys.stderr,
    )
    sys.exit(1)

from muimg.dngio import (
    IfdDataSpec,
    PageEncoding,
    PreviewParams,
    PreviewScale,
    write_dng_from_array,
)
from muimg.tiff_metadata import MetadataTags
from tifffile import COMPRESSION


# =============================================================================
# FITS Header Inspection
# =============================================================================

def print_fits_info(fits_path: Path) -> None:
    """Print all FITS header keywords and HDU summary."""
    with astropy_fits.open(fits_path) as hdul:
        print(f"File: {fits_path}")
        print(f"HDU count: {len(hdul)}")
        print()

        for i, hdu in enumerate(hdul):
            hdu_type = type(hdu).__name__
            print(f"--- HDU {i} ({hdu_type}) ---")
            if hdu.data is not None:
                shape = hdu.data.shape
                dtype = hdu.data.dtype
                print(
                    f"  Data: shape={shape}  "
                    f"dtype={dtype}  "
                    f"min={hdu.data.min()}  "
                    f"max={hdu.data.max()}"
                )
            else:
                print("  Data: None")
            print()

            header = hdu.header
            print(f"  Header keywords ({len(header)}):")
            for key in header:
                if key in ("", "COMMENT", "HISTORY"):
                    continue
                val = header[key]
                comment = header.comments[key]
                if comment:
                    print(f"    {key:20s} = {val!r:>30s}  / {comment}")
                else:
                    print(f"    {key:20s} = {val!r:>30s}")
            print()


# =============================================================================
# Display properties computation
# =============================================================================

def compute_baseline_exposure(
    data: np.ndarray,
    white_level: int = 65535,
) -> float | None:
    """Estimate BaselineExposure (in EV) from raw CFA data.

    Algorithm:
        1. If >25% of pixels are above 0.975 * white_level, the image
           is blown out - just leave it corrupted
        2. Otherwise, find an EV shift that maps the median pixel
           value to white_level / 2.

    Args:
        data: 2D raw CFA array
        white_level: Sensor white level (ADU)

    Returns:
        BaselineExposure in EV, or None if no adjustment needed.
    """
    # Build histogram over raw values
    num_bins = min(white_level, 10000)
    hist, bin_edges = np.histogram(
        data.ravel(), bins=num_bins, range=(0, white_level),
    )
    cdf = np.cumsum(hist).astype(np.float64) / np.sum(hist)

    # If >25% of pixels are near clipping, image is already bright
    clip_threshold = 0.975 * white_level
    clip_idx = np.searchsorted(bin_edges[:-1], clip_threshold)
    fraction_bright = 1.0 - (cdf[clip_idx - 1] if clip_idx > 0 else 0.0)
    if fraction_bright > 0.25:
        return None

    # Find median from CDF (where CDF crosses 0.5)
    median_idx = np.searchsorted(cdf, 0.5)
    median_val = bin_edges[median_idx]
    if median_val <= 0:
        return None

    target = white_level * 0.06
    ev_shift = np.log2(target / median_val)
    return float(ev_shift)


def _add_xmp(tags: MetadataTags) -> None:
    """Add XMP rendering parameters to metadata.

    Supported XMP params (via add_supported_xmp_from_dict):
        # 'Temperature'          - White balance temperature in Kelvin
        # 'Tint'                 - White balance tint adjustment
        # 'Exposure2012'         - Exposure compensation in stops
        # 'ToneCurvePV2012'      - All channels tone curve
        # 'ToneCurvePV2012Red'   - Red channel tone curve
        # 'ToneCurvePV2012Green' - Green channel tone curve
        # 'ToneCurvePV2012Blue'  - Blue channel tone curve
    """

    # simple S-shaped contrast curve
    tone_curve = [
        (0.0, 0.0),
        (64 / 255, 32 / 255),
        (128 / 255, 128 / 255),
        (192 / 255, 224 / 255),
        (1.0, 1.0),
    ]

    from muimg.raw_render import add_supported_xmp_from_dict
    add_supported_xmp_from_dict(tags, {
        'ToneCurvePV2012': tone_curve,
    })

# =============================================================================
# FITS Metadata → DNG Tag Mapping
# =============================================================================

def _parse_fits_datetime(date_str: str) -> datetime | None:
    """Parse FITS DATE-OBS string to datetime.

    Handles common FITS date formats:
        YYYY-MM-DDTHH:MM:SS.sss
        YYYY-MM-DDTHH:MM:SS
        YYYY-MM-DD
    """
    formats = [
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None

# =============================================================================
# Camera-Specific Tag Builders
# =============================================================================

# ZWO ASI676MC gain table: (camera_gain, e-/ADU)
# Source: https://www.zwoastro.com/product/asi676mc/
_ASI676MC_GAIN_TABLE = np.array([
    [0, 2.55],
    [50, 1.50],
    [100, 0.85],
    [150, 0.50],
    [200, 0.30],
])

# ZWO ASI676MC blue white balance table: (wb_b, balance)
# Derived from piecewise calibration, neutral at wb_b=75 (app default)
_ASI676MC_WB_BLUE_TABLE = np.array([
    [1,   0.01],
    [50,  0.59],
    [55,  0.73],
    [65,  0.87],
    [75,  1.00],
    [100, 1.34],
])


def _gain_to_iso(gain: float, gain_table: np.ndarray) -> int:
    """Convert camera gain to ISO using e-/ADU gain table.

    Interpolates e-/ADU, then computes:
        ISO = 100 * (reference_e_per_adu / interpolated_e_per_adu)

    Args:
        gain: Camera gain value
        gain_table: Nx2 array of [[gain, e_per_adu], ...], gain ascending

    Returns:
        ISO speed rating (integer)
    """
    e = np.interp(gain, gain_table[:, 0], gain_table[:, 1])
    return int(100 * gain_table[0, 1] / e)


def _build_unique_camera_tags(tags: MetadataTags, header) -> None:
    """Add camera-specific tags based on INSTRUME header.

    Currently supported cameras:
        - ZWO ASI676MC
    """
    instrume = str(header.get("INSTRUME", "")).strip()
    gain = header.get("GAIN")

    if instrume == "ZWO ASI676MC":
        if gain is not None:
            iso = _gain_to_iso(float(gain), _ASI676MC_GAIN_TABLE)
            tags.add_tag("ISOSpeedRatings", iso)

        # Analog balance (white balance)
        wb_r = header.get("WB_RED")
        wb_b = header.get("WB_BLUE")
        if wb_r is not None and wb_b is not None:
            wb_r_neutral, wb_b_neutral = 80, 100
            red_balance = float(wb_r) / float(wb_r_neutral)
            blue_balance = float(
                np.interp(wb_b, _ASI676MC_WB_BLUE_TABLE[:, 0],
                          _ASI676MC_WB_BLUE_TABLE[:, 1])
            ) / float(
                np.interp(wb_b_neutral, _ASI676MC_WB_BLUE_TABLE[:, 0],
                          _ASI676MC_WB_BLUE_TABLE[:, 1])
            )
            tags.add_tag("AnalogBalance",
                         [red_balance, 1.0, blue_balance])
    else:
        # Fallback: use raw gain as ISO
        if gain is not None:
            print(f"  '{instrume}' not in camera fits2dng.py profiles: fallback to default gain")
            tags.add_tag("ISOSpeedRatings", int(gain))
        tags.add_tag("AnalogBalance", [1.0, 1.0, 1.0])


def build_metadata_tags(header, data: np.ndarray) -> MetadataTags:
    """Extract FITS header keywords and map to DNG/EXIF tags.

    Args:
        header: astropy FITS header object

    Returns:
        MetadataTags with mapped EXIF/DNG tags
    """
    tags = MetadataTags()

    # Camera model
    instrume = header.get("INSTRUME")
    if instrume:
        tags.add_tag("UniqueCameraModel", str(instrume))

    # Camera-specific tags (ISO, etc.)
    _build_unique_camera_tags(tags, header)

    # Software
    swcreate = header.get("SWCREATE")
    if swcreate:
        tags.add_tag("Software", str(swcreate))

    # Exposure time (seconds)
    exptime = header.get("EXPTIME")
    if exptime is not None:
        tags.add_tag("ExposureTime", float(exptime))

    # Date/time
    date_obs = header.get("DATE-OBS")
    if date_obs is not None:
        dt = _parse_fits_datetime(str(date_obs))
        if dt is not None:
            tags.add_time_tags(dt, "original")

    # Black level
    blklevel = header.get("PEDESTAL")
    if blklevel is not None:
        tags.add_tag("BlackLevel", int(blklevel))

    # White level
    whtlevel = header.get("CWHITE")
    if whtlevel is not None:
        tags.add_tag("WhiteLevel", int(whtlevel))

    # Linear tone curve (bypass Adobe Camera Raw default curve)
    tags.add_tag("ProfileToneCurve", [0.0, 0.0, 1.0, 1.0])

    # Code below here only controls display properties of the image. This code can be safely
    # removed and the equivalent can be done in post-processing (eg in Photoshop).
    # These represent an attempt to match the behavior of ASIFitsView. 
    wl = int(header.get("CWHITE", 65535))
    ev_shift = compute_baseline_exposure(data, wl)
    exptime = header.get("EXPTIME")
    if ev_shift is not None:
        tags.add_tag("BaselineExposure", ev_shift)

        # Add XMP rendering params only when image passes the auto test
        _add_xmp(tags)

    return tags


# =============================================================================
# FITS → DNG Conversion
# =============================================================================

def convert_fits_to_dng(
    fits_path: Path,
    output_path: Path,
    bayer_pattern: str = "RGGB",
    compression: COMPRESSION = COMPRESSION.NONE,
    compression_args: dict | None = None,
    num_workers: int = 1,
    preview: bool = False,
) -> None:
    """Convert a FITS CFA file to DNG.

    Args:
        fits_path: Input FITS file path
        output_path: Output DNG file path
        bayer_pattern: Bayer pattern (RGGB, BGGR, GRBG, GBRG)
        compression: tifffile COMPRESSION enum value
        compression_args: Optional dict of compression arguments
        num_workers: Number of compression workers
        preview: Generate JPEG preview
    """
    # Read FITS data
    with astropy_fits.open(fits_path) as hdul:
        data = hdul[0].data
        header = hdul[0].header

    if data is None:
        print(f"ERROR: No data in primary HDU of {fits_path}", file=sys.stderr)
        sys.exit(1)

    # Validate 2D CFA
    if data.ndim != 2:
        print(
            f"ERROR: Expected 2D CFA data, got {data.ndim}D "
            f"(shape={data.shape})",
            file=sys.stderr,
        )
        sys.exit(1)

    # Check for BAYERPAT header override
    fits_pattern = header.get("BAYERPAT")
    if fits_pattern:
        bayer_pattern = str(fits_pattern).strip().upper()
        print(f"  Using Bayer pattern from FITS header: {bayer_pattern}")

    print(f"  Input:  {fits_path}")
    print(f"  Shape:  {data.shape}")
    print(f"  Dtype:  {data.dtype}")
    print(f"  Range:  {data.min()} .. {data.max()}")
    print(f"  Pattern: {bayer_pattern}")
    print(f"  Output: {output_path}")

    # Build metadata from FITS headers
    extra_tags = build_metadata_tags(header, data)

    # Build encoding
    encoding = PageEncoding(
        compression=compression,
        compression_args=compression_args,
        tile_size=(256, 256) if compression != COMPRESSION.NONE else None,
    )

    data_spec = IfdDataSpec(
        data=data,
        photometric="CFA",
        cfa_pattern=bayer_pattern,
        encoding=encoding,
        extratags=extra_tags,
    )

    # Preview params
    preview_params = None
    if preview:
        preview_params = PreviewParams(
            scale=PreviewScale.QUARTER,
            compression=COMPRESSION.JPEG,
        )

    write_dng_from_array(
        destination_file=output_path,
        data_spec=data_spec,
        preview=preview_params,
        num_compression_workers=num_workers,
    )

    file_size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  Written: {file_size_mb:.2f} MB")


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Convert FITS CFA data to DNG"
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Input FITS file path",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Output DNG path (default: input with .dng extension)",
    )
    parser.add_argument(
        "--pattern",
        choices=["RGGB", "BGGR", "GRBG", "GBRG"],
        default="RGGB",
        help="Bayer pattern (default: RGGB)",
    )
    parser.add_argument(
        "--compression",
        choices=[
            "uncompressed",
            "jpeg_lossless",
            "jxl_lossless",
            "jxl_lossy",
        ],
        default="uncompressed",
        help="Compression type (default: uncompressed)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of compression workers (default: 1)",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Generate JPEG preview",
    )
    parser.add_argument(
        "--info",
        action="store_true",
        help="Print FITS header info and exit (no conversion)",
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"ERROR: File not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    if args.info:
        print_fits_info(args.input)
        return

    output = args.output
    if output is None:
        output = args.input.with_suffix(".dng")

    # Map compression name to tifffile COMPRESSION
    compression_map = {
        "uncompressed": COMPRESSION.NONE,
        "jpeg_lossless": COMPRESSION.JPEG,
        "jxl_lossless": COMPRESSION.JPEGXL_DNG,
        "jxl_lossy": COMPRESSION.JPEGXL_DNG,
    }
    compression = compression_map[args.compression]

    # Set compression args
    if args.compression == "jpeg_lossless":
        compression_args = {'lossless': True}
    elif args.compression == "jxl_lossless":
        compression_args = {'distance': 0.0, 'effort': 2}
    elif args.compression == "jxl_lossy":
        compression_args = {'distance': 0.5, 'effort': 4}
    else:
        compression_args = None

    convert_fits_to_dng(
        fits_path=args.input,
        output_path=output,
        bayer_pattern=args.pattern,
        compression=compression,
        compression_args=compression_args,
        num_workers=args.workers,
        preview=args.preview,
    )


if __name__ == "__main__":
    main()
