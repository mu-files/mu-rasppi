#!/usr/bin/env python3
"""Capture a single raw frame from a ZWO ASI camera and save as DNG.

This script is designed to be simple and self-contained for sharing as an
example of ZWO camera capture to DNG using muimg.

Requirements:
    pip install numpy zwoasi muimg
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

try:
    import zwoasi as asi
except ImportError:
    print(
        "ERROR: zwoasi is required but not installed.\n"
        "Install with: pip install zwoasi",
        file=sys.stderr,
    )
    sys.exit(1)

from fits2dng import build_metadata_tags


# =============================================================================
# ZWO SDK Initialization
# =============================================================================

def find_sdk_library() -> str | None:
    """Search for the ZWO ASI SDK library in common locations."""
    # Check environment variable first
    env_path = os.environ.get("ZWO_ASI_LIB")
    if env_path and os.path.exists(env_path):
        return env_path

    possible_paths = [
        "/Applications/ASIStudio.app/Contents/Frameworks/libASICamera2.dylib",
        "/usr/local/lib/libASICamera2.so",
        "/opt/homebrew/lib/libASICamera2.dylib",
        os.path.expanduser(
            "~/Library/Application Support/ZWO/ASICamera/libASICamera2.dylib"
        ),
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return path
    return None


# =============================================================================
# DNG Metadata Builder
# =============================================================================

def build_metadata(camera_info: dict, metadata: dict, cfa_data: np.ndarray):
    """Build DNG metadata tags by constructing a FITS-like header and
    delegating to fits2dng.build_metadata_tags.

    Args:
        camera_info: Camera properties dict (Name, BayerPattern, etc.)
        metadata: Capture metadata dict (exposure_us, gain, wb_r, wb_b, etc.)
        cfa_data: Raw CFA array (needed for BaselineExposure calculation)

    Returns:
        MetadataTags object ready for DNG writing
    """
    # Map ZWO metadata to FITS-style header keys
    header = {
        "INSTRUME": camera_info.get("Name", "ZWO ASI Camera"),
        "GAIN": metadata.get("gain"),
        "WB_RED": metadata.get("wb_r"),
        "WB_BLUE": metadata.get("wb_b"),
        "EXPTIME": metadata.get("exposure_us", 0) / 1_000_000.0,
        "PEDESTAL": metadata.get("offset"),
        "CWHITE": 65535,
        "DATE-OBS": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
    }

    return build_metadata_tags(header, cfa_data)


# =============================================================================
# DNG Writer
# =============================================================================

def write_dng(cfa_data: np.ndarray, output: Path, tags, bayer_pattern: str,
              compression, compression_args=None, num_workers=1,
              preview: bool = False):
    """Write CFA data as DNG using muimg.

    Args:
        cfa_data: Raw CFA array (H, W) as uint16
        output: Output file path
        tags: MetadataTags object
        bayer_pattern: Bayer pattern string (e.g. "RGGB")
        compression: tifffile COMPRESSION enum value
        compression_args: Optional compression arguments
        num_workers: Number of compression workers
        preview: Generate JPEG preview
    """
    from muimg.dngio import (
        write_dng_from_array, IfdDataSpec, PageEncoding,
        PreviewParams, PreviewScale,
    )
    from tifffile import COMPRESSION

    encoding = PageEncoding(
        compression=compression,
        compression_args=compression_args,
        tile_size=(256, 256) if compression != COMPRESSION.NONE else None,
    )

    data_spec = IfdDataSpec(
        data=cfa_data,
        photometric="CFA",
        cfa_pattern=bayer_pattern,
        encoding=encoding,
        extratags=tags,
    )

    preview_params = None
    if preview:
        preview_params = PreviewParams(
            scale=PreviewScale.QUARTER,
            compression=COMPRESSION.JPEG,
        )

    write_dng_from_array(
        destination_file=output,
        data_spec=data_spec,
        preview=preview_params,
        num_compression_workers=num_workers,
    )


# =============================================================================
# Camera Capture
# =============================================================================

_BAYER_PATTERN_MAP = {
    0: "RGGB",  # ASI_BAYER_RG
    1: "BGGR",  # ASI_BAYER_BG
    2: "GRBG",  # ASI_BAYER_GR
    3: "GBRG",  # ASI_BAYER_GB
}


def capture(exposure_ms: float, gain: int, offset: int,
            wb_r: int, wb_b: int) -> tuple:
    """Initialize camera, capture one raw frame, return data and metadata.

    Args:
        exposure_ms: Exposure time in milliseconds
        gain: Camera gain (0-300 typical)
        offset: Camera offset/black level
        wb_r: White balance red
        wb_b: White balance blue

    Returns:
        tuple: (cfa_data, metadata, camera_info)
    """
    # Find and init SDK
    sdk_path = find_sdk_library()
    if not sdk_path:
        print("ERROR: ZWO ASI SDK library not found.", file=sys.stderr)
        print("  Set ZWO_ASI_LIB environment variable or install ASIStudio.",
              file=sys.stderr)
        sys.exit(1)

    asi.init(sdk_path)

    num_cameras = asi.get_num_cameras()
    if num_cameras == 0:
        print("ERROR: No ZWO cameras found.", file=sys.stderr)
        sys.exit(1)

    # Open first camera
    camera = asi.Camera(0)
    props = camera.get_camera_property()

    camera_info = {
        "Name": props["Name"],
        "MaxWidth": props["MaxWidth"],
        "MaxHeight": props["MaxHeight"],
        "BayerPattern": _BAYER_PATTERN_MAP.get(props.get("BayerPattern", 0), "RGGB"),
        "PixelSize": props.get("PixelSize", 0),
        "BitDepth": props.get("BitDepth", 16),
    }

    print(f"  Camera: {camera_info['Name']}")
    print(f"  Sensor: {camera_info['MaxWidth']}x{camera_info['MaxHeight']}")
    print(f"  Pixel size: {camera_info['PixelSize']}um")
    print(f"  Bayer: {camera_info['BayerPattern']}")
    print()

    # Configure camera
    camera.set_image_type(asi.ASI_IMG_RAW16)

    exposure_us = int(exposure_ms * 1000)
    camera.set_control_value(asi.ASI_EXPOSURE, exposure_us)
    camera.set_control_value(asi.ASI_GAIN, gain)
    camera.set_control_value(asi.ASI_OFFSET, offset)
    camera.set_control_value(asi.ASI_WB_R, wb_r)
    camera.set_control_value(asi.ASI_WB_B, wb_b)

    print(f"  Exposure: {exposure_ms}ms")
    print(f"  Gain: {gain}")
    print(f"  Offset: {offset}")
    print(f"  WB Red: {wb_r}, Blue: {wb_b}")
    print()

    # Capture
    print("  Capturing...")
    camera.start_exposure()

    # Wait for exposure
    if exposure_us > 100_000:
        time.sleep(exposure_us / 1_000_000 * 0.75)

    while camera.get_exposure_status() == asi.ASI_EXP_WORKING:
        time.sleep(0.001)

    status = camera.get_exposure_status()
    if status != asi.ASI_EXP_SUCCESS:
        camera.close()
        print(f"ERROR: Exposure failed with status {status}", file=sys.stderr)
        sys.exit(1)

    # Read data
    width, height, bins, img_type = camera.get_roi_format()
    buffer = bytearray(width * height * 2)
    data = camera.get_data_after_exposure(buffer)

    # Query actual hardware values
    hw_exposure, _ = camera.get_control_value(asi.ASI_EXPOSURE)
    hw_gain, _ = camera.get_control_value(asi.ASI_GAIN)
    hw_offset, _ = camera.get_control_value(asi.ASI_OFFSET)
    hw_wb_r, _ = camera.get_control_value(asi.ASI_WB_R)
    hw_wb_b, _ = camera.get_control_value(asi.ASI_WB_B)
    hw_temp, _ = camera.get_control_value(asi.ASI_TEMPERATURE)

    camera.close()

    # Reshape to 2D
    cfa_data = np.frombuffer(data, dtype=np.uint16).reshape(height, width)

    metadata = {
        "exposure_us": hw_exposure,
        "gain": hw_gain,
        "offset": hw_offset,
        "wb_r": hw_wb_r,
        "wb_b": hw_wb_b,
        "temperature_c": hw_temp / 10.0,
    }

    print(f"  Done. Shape: {cfa_data.shape}, Range: {cfa_data.min()}..{cfa_data.max()}")
    print(f"  Temperature: {metadata['temperature_c']:.1f}°C")
    print()

    return cfa_data, metadata, camera_info


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Capture a single raw frame from a ZWO ASI camera and save as DNG"
    )
    parser.add_argument(
        "--exposure",
        type=float,
        default=100.0,
        help="Exposure time in milliseconds (default: 100)",
    )
    parser.add_argument(
        "--gain",
        type=int,
        default=50,
        help="Camera gain (default: 50)",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=1,
        help="Camera offset/black level (default: 1)",
    )
    parser.add_argument(
        "--wb-r",
        type=int,
        default=55,
        help="White balance red (default: 55)",
    )
    parser.add_argument(
        "--wb-b",
        type=int,
        default=75,
        help="White balance blue (default: 75)",
    )
    parser.add_argument(
        "--compression",
        choices=["uncompressed", "jpeg_lossless", "jxl_lossless", "jxl_lossy"],
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
        help="Generate JPEG preview in the DNG",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=Path("capture.dng"),
        help="Output DNG path (default: capture.dng)",
    )
    args = parser.parse_args()

    from tifffile import COMPRESSION

    print("=" * 60)
    print("ZWO ASI Camera → DNG Capture")
    print("=" * 60)
    print()

    # Capture
    cfa_data, metadata, camera_info = capture(
        exposure_ms=args.exposure,
        gain=args.gain,
        offset=args.offset,
        wb_r=args.wb_r,
        wb_b=args.wb_b,
    )

    # Build metadata
    tags = build_metadata(camera_info, metadata, cfa_data)

    # Compression setup
    compression_map = {
        "uncompressed": COMPRESSION.NONE,
        "jpeg_lossless": COMPRESSION.JPEG,
        "jxl_lossless": COMPRESSION.JPEGXL_DNG,
        "jxl_lossy": COMPRESSION.JPEGXL_DNG,
    }
    compression = compression_map[args.compression]

    if args.compression == "jpeg_lossless":
        compression_args = {"lossless": True}
    elif args.compression == "jxl_lossless":
        compression_args = {"distance": 0.0, "effort": 2}
    elif args.compression == "jxl_lossy":
        compression_args = {"distance": 0.5, "effort": 4}
    else:
        compression_args = None

    # Write DNG
    print(f"Writing DNG: {args.output}")
    print(f"  Compression: {args.compression}")
    print(f"  Preview: {'yes' if args.preview else 'no'}")

    write_dng(
        cfa_data=cfa_data,
        output=args.output,
        tags=tags,
        bayer_pattern=camera_info["BayerPattern"],
        compression=compression,
        compression_args=compression_args,
        num_workers=args.workers,
        preview=args.preview,
    )

    file_size_mb = args.output.stat().st_size / (1024 * 1024)
    print(f"  Written: {file_size_mb:.2f} MB")
    print()
    print("Done.")


if __name__ == "__main__":
    main()
