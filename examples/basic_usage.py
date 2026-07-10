"""
Basic usage examples for Puzzle Piece Finder.

This script demonstrates the core functionality of the puzzle solving system
using the programmatic API. Run it from the repository root:

    python examples/basic_usage.py
"""

import os
import sys

# Python only puts this script's own directory (examples/) on sys.path, not
# the repo root, so `import src...` would fail when this file is run directly
# (`python examples/basic_usage.py`). Add the repo root once, up front, so the
# rest of the file can use plain `from src.xxx import ...` imports that match
# how the rest of the codebase (and its relative imports) are structured.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from PIL import Image

from src.matching import multi_scale_template_match, basic_metrics
from src.features import dominant_color, color_distance

# Real example data shipped with the repo: a full puzzle photo and individual
# piece photos (raw .DNG files, openable directly via PIL on this machine).
PUZZLE_PATH = os.path.join(_REPO_ROOT, "images", "puzzles", "PuzzleOriginal.jpeg")
PIECES_DIR = os.path.join(_REPO_ROOT, "images", "pieces")


def _list_piece_files():
    """Return sorted .dng piece file names found in PIECES_DIR."""
    return sorted(f for f in os.listdir(PIECES_DIR) if f.lower().endswith(".dng"))


def example_1_basic_matching():
    """Example 1: Basic template matching between puzzle and piece."""
    print("=== Example 1: Basic Template Matching ===")

    piece_files = _list_piece_files()
    if not piece_files:
        print(f"No piece files found in {PIECES_DIR}")
        return
    piece_path = os.path.join(PIECES_DIR, piece_files[0])

    try:
        puzzle_img = Image.open(PUZZLE_PATH)
        piece_img = Image.open(piece_path)

        print(f"Puzzle size: {puzzle_img.size}")
        print(f"Piece size: {piece_img.size}")

        # Run template matching
        result = multi_scale_template_match(
            puzzle_img=puzzle_img,
            piece_img=piece_img,
            use_downscale=True,
        )

        if "error" in result:
            print(f"Error: {result['error']}")
            return

        print(f"Best position: {result['best_position']}")
        print(f"Scale factor: {result['scale']:.3f}")
        print(f"Similarity: {result['refined_similarity']:.1%}")

    except FileNotFoundError as e:
        print(f"File not found: {e}")
    except Exception as e:
        print(f"Error: {e}")


def example_2_color_analysis():
    """Example 2: Color-based analysis of puzzle pieces."""
    print("\n=== Example 2: Color Analysis ===")

    try:
        piece_files = _list_piece_files()[:5]

        colors = []
        for piece_file in piece_files:
            piece_path = os.path.join(PIECES_DIR, piece_file)
            piece_img = Image.open(piece_path)

            dom_color = dominant_color(piece_img)
            colors.append((piece_file, dom_color))

            print(f"{piece_file}: RGB{dom_color}")

        # Find most similar colors
        print("\nColor similarities:")
        for i, (file1, color1) in enumerate(colors):
            for j, (file2, color2) in enumerate(colors[i+1:], i+1):
                distance = color_distance(color1, color2)
                print(f"{file1} <-> {file2}: distance = {distance:.1f}")

    except Exception as e:
        print(f"Error in color analysis: {e}")


def example_3_metrics_analysis():
    """Example 3: Comprehensive metrics analysis."""
    print("\n=== Example 3: Metrics Analysis ===")

    try:
        piece_files = _list_piece_files()
        if not piece_files:
            print(f"No piece files found in {PIECES_DIR}")
            return
        piece_path = os.path.join(PIECES_DIR, piece_files[0])

        puzzle_img = Image.open(PUZZLE_PATH)
        piece_img = Image.open(piece_path)

        # Get comprehensive metrics
        metrics = basic_metrics(
            puzzle_img=puzzle_img,
            piece_img=piece_img,
            real_width_cm=25.0,  # Example: 25cm wide puzzle
            real_height_cm=18.0  # Example: 18cm tall puzzle
        )

        print("Comprehensive Metrics:")
        print(f"  Puzzle size: {metrics['puzzle_size']}")
        print(f"  Piece size: {metrics['piece_size']}")
        print(f"  Area ratio: {metrics['area_ratio']:.1%}")
        print(f"  Color distance: {metrics['color_distance']:.1f}")

        if 'scale_px_per_cm_avg' in metrics:
            print(f"  Scale: {metrics['scale_px_per_cm_avg']:.1f} px/cm")

        if 'piece_real_size_cm' in metrics:
            real_w, real_h = metrics['piece_real_size_cm']
            print(f"  Piece real size: {real_w:.1f}cm x {real_h:.1f}cm")

    except Exception as e:
        print(f"Error in metrics analysis: {e}")


def example_4_batch_processing():
    """Example 4: Process multiple pieces against same puzzle."""
    print("\n=== Example 4: Batch Processing ===")

    try:
        piece_files = _list_piece_files()[:3]
        if not piece_files:
            print(f"No piece files found in {PIECES_DIR}")
            return

        puzzle_img = Image.open(PUZZLE_PATH)

        results = []

        for piece_file in piece_files:
            piece_path = os.path.join(PIECES_DIR, piece_file)
            piece_img = Image.open(piece_path)

            print(f"Processing {piece_file}...")

            result = multi_scale_template_match(
                puzzle_img=puzzle_img,
                piece_img=piece_img,
                use_downscale=True,
                num_pieces=len(_list_piece_files()),  # Hint: loose pieces available
            )

            if "error" not in result:
                results.append({
                    'file': piece_file,
                    'position': result['best_position'],
                    'similarity': result['refined_similarity'],
                    'scale': result['scale']
                })

        # Sort by similarity
        results.sort(key=lambda x: x['similarity'], reverse=True)

        print("\nResults (sorted by similarity):")
        for r in results:
            print(f"  {r['file']}: {r['similarity']:.1%} at {r['position']}")

    except Exception as e:
        print(f"Error in batch processing: {e}")


if __name__ == "__main__":
    print("Puzzle Piece Finder - Usage Examples")
    print("=" * 50)

    # Run all examples
    example_1_basic_matching()
    example_2_color_analysis()
    example_3_metrics_analysis()
    example_4_batch_processing()

    print("\n" + "=" * 50)
    print("Examples completed!")
    print("\nNext steps:")
    print("1. Try the GUI: python -m src.gui")
    print("2. Experiment with your own puzzle images")
    print("3. Try automatic segmentation: src.segmentation.segment_pieces_from_file")
