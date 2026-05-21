#!/usr/bin/env python3
"""Benchmark picamera2 capture with PiDNG vs muimg DNG writing.

Captures a single raw image using picamera2 and benchmarks saving it with
different libraries and compression methods.

This script is designed to be simple and self-contained for sharing with
the Raspberry Pi community.
"""

import argparse
import io
import json
import time
from contextlib import redirect_stderr
from datetime import datetime
from pathlib import Path

import numpy as np
from picamera2 import Picamera2, MappedArray


# =============================================================================
# muimg DNG Writer (Main Function)
# =============================================================================

def write_muimg(cfa_data: np.ndarray, output, compression,
                compression_args=None, camera_model=None, num_workers=1,
                preview: bool = False):
    """Write DNG using muimg library.
    
    Args:
        cfa_data: CFA array - can be uint8 (packed) or uint16 (unpacked)
        output: Output path (str/Path) or BytesIO
        compression: tifffile COMPRESSION enum value
        compression_args: Optional dict of compression arguments
        camera_model: PiDNG camera model (Picamera2Camera instance)
        num_workers: Number of compression workers
        preview: If True, generate a JPEG-compressed 1/4 scale preview
    """
    from muimg.dngio import write_dng_from_array, IfdDataSpec, PageEncoding
    from muimg.tiff_metadata import MetadataTags
    from tifffile import COMPRESSION
    
    # Unpack uint8 to uint16 if needed
    if cfa_data.dtype == np.uint8:
        cfa_data = cfa_data.view(np.uint16).reshape(cfa_data.shape[0], cfa_data.shape[1] // 2)
    
    # Extract tags from camera model
    extra_tags = MetadataTags()
    bits_per_sample = 12
    cfa_pattern = "RGGB"  # Default
    
    if camera_model is not None:
        for tag_obj in camera_model.tags.list():
            extra_tags.add_tag(tag_obj.TagId, tag_obj.rawValue)
        bits_per_sample = extra_tags.get_tag("BitsPerSample") or 12
        cfa_pattern = extra_tags.get_tag("CFAPattern") or "RGGB"
        
        # For IMX477 (HQ Camera): set default crop to exclude optical black columns
        # Full sensor: 4064x3040, Cropped area: 4056x3040 (skip 8 cols on right side)
        if cfa_data.shape[1] == 4064:
            extra_tags.add_tag("DefaultCropOrigin", [0, 0])  # H, V offset
            extra_tags.add_tag("DefaultCropSize", [4056, 3040])  # H, V size
    
    # For JXL compression, convert to 16-bit (if not already)
    if compression == COMPRESSION.JPEGXL_DNG and bits_per_sample != 16:
        cfa_data, bits_per_sample = convert_to_16bit_for_jxl(
            cfa_data, bits_per_sample, extra_tags
        )
    
    # Create encoding if compression is specified
    # Only use tiling for compressed formats (enables parallel compression)
    encoding = PageEncoding(
        compression=compression,
        compression_args=compression_args,
        tile_size= (256, 256) if compression != COMPRESSION.NONE else None
    )
    
    data_spec = IfdDataSpec(
        data=cfa_data,
        photometric="CFA",
        bits_per_sample=bits_per_sample,
        cfa_pattern=cfa_pattern,
        encoding=encoding,
        extratags=extra_tags,
    )
    
    # Create preview params if requested
    preview_params = None
    if preview:
        from muimg.dngio import PreviewParams, PreviewScale
        preview_params = PreviewParams(scale=PreviewScale.QUARTER, compression=COMPRESSION.JPEG)
    
    write_dng_from_array(
        destination_file=output,
        data_spec=data_spec,
        preview=preview_params,
        num_compression_workers=num_workers,
    )


# =============================================================================
# muimg Helper Functions
# =============================================================================

def convert_to_16bit_for_jxl(cfa_data, bits_per_sample, extra_tags):
    """Convert CFA data and metadata from current bit depth to 16-bit for JXL.
    
    Note: For 9 <= bits_per_sample <= 15 and JXL, Photoshop has a bug decoding 
    the DNGs. muimg can encode and decode using JXL with these bit counts, but 
    if you want to read the DNG in Photoshop then conversion to 16-bit is required.
    
    Args:
        cfa_data: CFA array (H, W) as uint16
        bits_per_sample: Current bit depth (e.g., 12)
        extra_tags: MetadataTags object to update
        
    Returns:
        tuple: (converted_cfa_data, new_bits_per_sample)
    """
    from muimg.raw_render import convert_dtype
    
    # Convert data from current bit depth to 16-bit
    cfa_data = convert_dtype(cfa_data, np.uint16, src_bits_per_element=bits_per_sample)
    
    # Scale metadata proportionally (same as convert_dtype does for values)
    source_max = (1 << bits_per_sample) - 1
    dest_max = (1 << 16) - 1
    
    # Read and scale BlackLevel
    black_level = extra_tags.get_tag("BlackLevel")
    if black_level is not None:
        # Handle array, list, tuple, or scalar
        if isinstance(black_level, (list, tuple, np.ndarray)):
            scaled_black = [int(b * dest_max / source_max) for b in black_level]
        else:
            scaled_black = int(black_level * dest_max / source_max)
        extra_tags.add_tag("BlackLevel", scaled_black)
    
    # Read and scale WhiteLevel
    white_level = extra_tags.get_tag("WhiteLevel")
    if white_level is not None:
        # Handle array, list, tuple, or scalar
        if isinstance(white_level, (list, tuple, np.ndarray)):
            scaled_white = [int(w * dest_max / source_max) for w in white_level]
        else:
            scaled_white = int(white_level * dest_max / source_max)
        extra_tags.add_tag("WhiteLevel", scaled_white)
    
    return cfa_data, 16


# =============================================================================
# PiDNG Wrapper
# =============================================================================

def write_pidng(cfa_data: np.ndarray, output, compress: bool = False, 
                camera_model=None):
    """Write DNG using PiDNG library.
    
    Args:
        cfa_data: CFA array (H, W) as uint16
        output: Output path (str/Path) or BytesIO
        compress: Use LJ92 compression
        camera_model: PiDNG camera model (e.g., Picamera2Camera instance)
    """
    from pidng.core import PICAM2DNG
    
    # PICAM2DNG expects the camera model to be set up with format and metadata
    r = PICAM2DNG(camera_model)
    r.options(compress=compress)
    
    # PiDNG only supports file output, not BytesIO
    if isinstance(output, io.BytesIO):
        raise NotImplementedError("PiDNG does not support BytesIO output")
    
    r.convert(cfa_data, filename=str(output))

# =============================================================================
# Camera Initialization and Capture
# =============================================================================

def capture():
    """Initialize picamera2, capture raw image, and create camera model.
    
    Returns:
        tuple: (cfa_data, camera_model)
            - cfa_data: Raw CFA array (uint16)
            - camera_model: PiDNG camera model
    """
    # Initialize and configure picamera2
    print("Initializing picamera2...")
    picam2 = Picamera2()
    
    # Configure for raw capture (uncompressed format)
    raw_config = {'format': 'SBGGR12'}
    config = picam2.create_still_configuration(raw=raw_config, buffer_count=2)
    picam2.configure(config)
    
    print("  Configuration:")
    print(f"    Raw format: {raw_config['format']}")
    print()
    
    # Start camera
    picam2.start()
    
    # Wait for camera to stabilize
    print("Waiting for camera to stabilize...")
    time.sleep(1)
    print()
    
    # Capture raw image
    print("Capturing raw image...")
    with picam2.captured_request() as request:
        # Extract raw array
        with MappedArray(request, 'raw') as m:
            cfa_data = m.array.copy()
        
        # Get metadata
        metadata = request.get_metadata()
        
        # Get format configuration
        fmt_dict = picam2.camera_configuration()['raw']
    
    # Stop camera (we only need one capture)
    picam2.stop()
    
    # Display capture info
    width = cfa_data.shape[1]
    if cfa_data.dtype == np.uint8:
        width //= 2  # Packed uint8: 2 bytes per pixel
    # Parse bit depth from format string (e.g., "SBGGR12" -> 12)
    fmt_str = fmt_dict.get('format', 'unknown')
    bpp = int(''.join(filter(str.isdigit, fmt_str))) if any(c.isdigit() for c in fmt_str) else 'unknown'
    
    print(f"  Image size: {width}x{cfa_data.shape[0]}")
    print(f"  Format: {fmt_str}")
    print(f"  Bit depth: {bpp}")
    print(f"  Data type: {cfa_data.dtype} ({'packed' if cfa_data.dtype == np.uint8 else 'unpacked'})")
    print(f"  Value range: {cfa_data.min()}-{cfa_data.max()}")
    print(f"  Raw size: {cfa_data.nbytes / (1024 * 1024):.2f} MB")
    print()
    
    # Create PiDNG camera model from picamera2 metadata
    from pidng.camdefs import Picamera2Camera
    camera_model = Picamera2Camera(fmt_dict, metadata, model="Picamera2 Benchmark")
    print(f"Camera model: {camera_model.model}")
    print()
    
    return cfa_data, camera_model

# =============================================================================
# Benchmark Runner
# =============================================================================

def run_benchmark(cfa_data, camera_model, scenarios, iterations=10):
    """Run benchmark for all scenarios.
    
    Args:
        cfa_data: CFA array to write (uint8 packed format)
        camera_model: PiDNG camera model
        scenarios: List of (library, compression_name, destination, comp_obj, comp_args)
        iterations: Number of iterations per scenario
        
    Returns:
        List of result dictionaries
    """
    from pathlib import Path
    from tifffile import COMPRESSION
    
    results = []
    raw_size_mb = cfa_data.nbytes / (1024 * 1024)
    
    for scenario in scenarios:
        library = scenario[0]
        compression_name = scenario[1]
        destination = scenario[2]
        comp_obj = scenario[3]
        comp_args = scenario[4] if len(scenario) > 4 else None
        num_workers = scenario[5] if len(scenario) > 5 else 1
        preview = scenario[6] if len(scenario) > 6 else None
        workers_str = f"w={num_workers}" if library == "muimg" else ""
        print(f"  {library:5s} | {compression_name:22s} | {workers_str:4s} | {destination:7s} ... ", 
              end="", flush=True)
        
        times = []
        file_size = 0
        kept_file = None
        
        for j in range(iterations):
            if destination == "file":
                # Include worker count in filename for muimg tests
                if library == "muimg" and num_workers > 1:
                    output = Path(f"results/test_{library}_{compression_name}_w{num_workers}_{j}.dng")
                else:
                    output = Path(f"results/test_{library}_{compression_name}_{j}.dng")
            else:
                output = io.BytesIO()
            
            start = time.perf_counter()
            
            # Write DNG (each function handles data format internally)
            if library == "pidng":
                compress = (compression_name == "lj92")
                write_pidng(cfa_data, output, compress=compress, 
                           camera_model=camera_model)
            elif library == "muimg":
                write_muimg(cfa_data, output, compression=comp_obj, 
                           compression_args=comp_args, camera_model=camera_model,
                           num_workers=num_workers, preview=preview)
            else:
                raise ValueError(f"Unknown library: {library}")
            
            elapsed = time.perf_counter() - start
            times.append(elapsed)
            
            # Measure file size
            if destination == "file":
                file_size = output.stat().st_size
                # Keep only the last file, delete previous ones
                if kept_file is not None and kept_file.exists():
                    kept_file.unlink()
                kept_file = output
            else:
                file_size = len(output.getvalue())
        
        times_arr = np.array(times)
        file_size_mb = file_size / (1024 * 1024)
        compression_ratio = raw_size_mb / file_size_mb if file_size_mb > 0 else 0
        
        mean_time_sec = np.mean(times_arr)
        frames_per_sec = 1.0 / mean_time_sec if mean_time_sec > 0 else 0
        
        result = {
            'library': library,
            'compression': compression_name,
            'num_workers': num_workers if library == "muimg" else None,
            'destination': destination,
            'mean_time_ms': float(np.mean(times_arr) * 1000),
            'std_time_ms': float(np.std(times_arr) * 1000),
            'min_time_ms': float(np.min(times_arr) * 1000),
            'max_time_ms': float(np.max(times_arr) * 1000),
            'file_size_mb': float(file_size_mb),
            'compression_ratio': float(compression_ratio),
            'throughput_mbs': float(raw_size_mb / mean_time_sec),
            'frames_per_sec': float(frames_per_sec),
            'iterations': iterations
        }
        results.append(result)
        
        print(f"{result['mean_time_ms']:6.1f}ms ± {result['std_time_ms']:4.1f}ms | "
              f"{file_size_mb:5.2f}MB | {compression_ratio:5.1f}x | "
              f"{result['throughput_mbs']:6.1f}MB/s | {frames_per_sec:5.2f}fps")
    
    return results


# =============================================================================
# Results Formatting
# =============================================================================

def print_results_table(results):
    """Print formatted results table."""
    print("\n" + "=" * 131)
    print("BENCHMARK RESULTS")
    print("=" * 131)
    print(f"{'Library':<8} {'Compression':<22} {'Work':<5} {'Dest':<8} {'Time(ms)':<12} "
          f"{'Size(MB)':<10} {'Ratio':<8} {'Throughput(MB/s)':<16} {'FPS':<8}")
    print("-" * 131)
    
    for r in results:
        workers = f"w={r['num_workers']}" if r['num_workers'] else ""
        print(f"{r['library']:<8} {r['compression']:<22} {workers:<5} {r['destination']:<8} "
              f"{r['mean_time_ms']:6.1f}±{r['std_time_ms']:4.1f}  "
              f"{r['file_size_mb']:8.2f}  {r['compression_ratio']:6.1f}x  "
              f"{r['throughput_mbs']:14.1f}  {r['frames_per_sec']:6.2f}")
    
    print("=" * 131)


def save_results_json(results, output_path):
    """Save results to JSON file."""
    output = {
        'timestamp': datetime.now().isoformat(),
        'results': results
    }
    
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\nResults saved to: {output_path}")


# =============================================================================
# Single Capture Mode
# =============================================================================

def run_single_mode(cfa_data, camera_model, compression_name, compression,
                   compression_args, num_workers, preview, output_path):
    """Run single capture scenario.
    
    Args:
        cfa_data: Raw CFA data
        camera_model: PiDNG camera model
        compression_name: Name for display
        compression: tifffile COMPRESSION enum
        compression_args: Compression arguments dict
        num_workers: Number of workers
        preview: Enable preview generation
        output_path: Output file path
    """
    print(f"\nSingle capture: {compression_name}")
    print(f"  Workers: {num_workers}")
    print(f"  Preview: {'yes' if preview else 'no'}")
    print(f"  Output: {output_path}")
    print()
    
    # Run capture
    write_muimg(
        cfa_data, output_path, compression,
        compression_args=compression_args,
        camera_model=camera_model,
        num_workers=num_workers,
        preview=preview
    )
    
    # Print file info
    file_size_mb = output_path.stat().st_size / (1024 * 1024)
    raw_size_mb = cfa_data.nbytes / (1024 * 1024)
    print(f"\nOutput file: {output_path}")
    print(f"  Size: {file_size_mb:.2f} MB")
    print(f"  Compression ratio: {raw_size_mb/file_size_mb:.1f}x")


# =============================================================================
# Benchmark Mode
# =============================================================================

def run_benchmark_mode(cfa_data, camera_model, iterations=10):
    """Run full benchmark with all scenarios.
    
    Args:
        cfa_data: Raw CFA data
        camera_model: PiDNG camera model
        iterations: Number of iterations per scenario
    """
    from tifffile import COMPRESSION
    
    # Define test scenarios
    scenarios = [
        # (library, compression_name, destination, comp_obj, compression_args, num_workers, preview)
        
        # PiDNG tests (file only)
        ("pidng", "uncompressed", "file", None, None, 1),
        ("pidng", "lj92", "file", None, None, 1),
        
        # muimg tests - 
        ("muimg", "uncompressed", "file", COMPRESSION.NONE, None, 1),
        ("muimg", "jpeg_lossless", "file", COMPRESSION.JPEG, {'lossless': True}, 1),
        ("muimg", "jpeg_lossless", "file", COMPRESSION.JPEG, {'lossless': True}, 2),
        ("muimg", "jpeg_lossless", "file", COMPRESSION.JPEG, {'lossless': True}, 4),
        
        # muimg tests - JXL
        ("muimg", "jxl_lossless", "file", COMPRESSION.JPEGXL_DNG, 
         {'distance': 0.0, 'effort': 2}, 1),
        ("muimg", "jxl_lossless", "file", COMPRESSION.JPEGXL_DNG, 
         {'distance': 0.0, 'effort': 2}, 2),
        ("muimg", "jxl_lossless", "file", COMPRESSION.JPEGXL_DNG, 
         {'distance': 0.0, 'effort': 2}, 4),
        ("muimg", "jxl_lossy", "file", COMPRESSION.JPEGXL_DNG, 
         {'distance': 0.5, 'effort': 4}, 1),
        ("muimg", "jxl_lossy", "file", COMPRESSION.JPEGXL_DNG, 
         {'distance': 0.5, 'effort': 4}, 2),
        ("muimg", "jxl_lossy", "file", COMPRESSION.JPEGXL_DNG, 
         {'distance': 0.5, 'effort': 4}, 4),
        
        # muimg tests - with preview
        ("muimg", "uncompressed+preview", "file", COMPRESSION.NONE, None, 1, True),
        ("muimg", "jxl_lossless+preview", "file", COMPRESSION.JPEGXL_DNG,
         {'distance': 0.0, 'effort': 2}, 4, True),
        ("muimg", "jxl_lossy+preview", "file", COMPRESSION.JPEGXL_DNG,
         {'distance': 0.5, 'effort': 4}, 4, True),
    ]
    
    print(f"Running {len(scenarios)} test scenarios ({iterations} iterations each)...")
    print()
    
    # Run benchmarks
    results = run_benchmark(cfa_data, camera_model, scenarios, iterations)
    
    # Print results
    print_results_table(results)
    
    # Save results to JSON
    output_path = Path("results/benchmark_picamera2_results.json")
    save_results_json(results, output_path)


# =============================================================================
# Main
# =============================================================================

def main():
    """Run picamera2 capture and DNG writing benchmark."""
    parser = argparse.ArgumentParser(
        description="Capture raw image from picamera2 and write DNG with various options"
    )
    parser.add_argument(
        "-v", "--verbose", action="count", default=0,
        help="Increase verbosity (use -v or -vv for more detail)"
    )
    parser.add_argument(
        "--mode",
        choices=["benchmark", "single"],
        default="single",
        help="Run mode: single capture or benchmark (default: single)"
    )
    parser.add_argument(
        "--compression",
        choices=["uncompressed", "jpeg_lossless", "jxl_lossless", "jxl_lossy"],
        default="uncompressed",
        help="Compression type for single mode (default: uncompressed)"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of compression workers for single mode (default: 1)"
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Enable preview generation for single mode"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("capture.dng"),
        help="Output file path for single mode (default: capture.dng)"
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=10,
        help="Number of iterations for benchmark mode (default: 10)"
    )
    args = parser.parse_args()
    
    # Create results directory
    Path("results").mkdir(exist_ok=True)
    
    print("=" * 90)
    print("Picamera2 DNG Capture and Writing Benchmark: PiDNG vs muimg")
    print("=" * 90)
    print()
    
    # Initialize camera and capture
    cfa_data, camera_model = capture()
    
    # Run in selected mode
    if args.mode == "single":
        # Map compression name to tifffile COMPRESSION
        from tifffile import COMPRESSION
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
        
        run_single_mode(
            cfa_data, camera_model,
            args.compression, compression, compression_args,
            args.workers, args.preview, args.output
        )
    else:
        run_benchmark_mode(cfa_data, camera_model, args.iterations)


if __name__ == "__main__":
    import logging
    import sys
    
    # Parse args first to get verbose level
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-v", "--verbose", action="count", default=0)
    args, _ = parser.parse_known_args()
    
    # Set logging level based on verbosity
    if args.verbose >= 2:
        level = logging.DEBUG
    elif args.verbose >= 1:
        level = logging.INFO
    else:
        level = logging.WARNING
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Set picamera2 logging to match command line verbosity
    picamera2_logger = logging.getLogger('picamera2')
    picamera2_logger.setLevel(level)
    
    main()
