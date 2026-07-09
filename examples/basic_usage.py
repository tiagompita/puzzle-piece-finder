"""
Basic usage examples for Puzzle Piece Finder.

This script demonstrates the core functionality of the puzzle solving system
using the programmatic API.
"""

import sys
import os
from PIL import Image

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from matching import multi_scale_template_match, basic_metrics
from features import dominant_color, color_distance


def example_1_basic_matching():
    """Example 1: Basic template matching between puzzle and piece."""
    print("=== Example 1: Basic Template Matching ===")
    
    # Load example images (adjust paths as needed)
    puzzle_path = "../images/puzzles/1186441_1.jpg"
    piece_path = "../images/pieces/piece_0.png"
    
    try:
        puzzle_img = Image.open(puzzle_path)
        piece_img = Image.open(piece_path)
        
        print(f"Puzzle size: {puzzle_img.size}")
        print(f"Piece size: {piece_img.size}")
        
        # Run template matching
        result = multi_scale_template_match(
            puzzle_img=puzzle_img,
            piece_img=piece_img,
            use_downscale=True,
            use_gpu=False  # Set to True if you have CUDA-enabled OpenCV
        )
        
        if "error" in result:
            print(f"Error: {result['error']}")
            return
            
        print(f"Best position: {result['best_position']}")
        print(f"Scale factor: {result['scale']:.3f}")
        print(f"Similarity: {result['refined_similarity']:.1%}")
        print(f"GPU used: {result['gpu_used']}")
        
    except FileNotFoundError as e:
        print(f"File not found: {e}")
    except Exception as e:
        print(f"Error: {e}")


def example_2_color_analysis():
    """Example 2: Color-based analysis of puzzle pieces."""
    print("\n=== Example 2: Color Analysis ===")
    
    # Analyze multiple pieces
    pieces_dir = "../images/pieces"
    
    try:
        piece_files = [f for f in os.listdir(pieces_dir) if f.endswith('.png')][:5]
        
        colors = []
        for piece_file in piece_files:
            piece_path = os.path.join(pieces_dir, piece_file)
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
        puzzle_path = "../images/puzzles/1186441_1.jpg"
        piece_path = "../images/pieces/piece_5.png"
        
        puzzle_img = Image.open(puzzle_path)
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
        puzzle_path = "../images/puzzles/1186441_1.jpg"
        pieces_dir = "../images/pieces"
        
        puzzle_img = Image.open(puzzle_path)
        piece_files = [f for f in os.listdir(pieces_dir) if f.endswith('.png')][:3]
        
        results = []
        
        for piece_file in piece_files:
            piece_path = os.path.join(pieces_dir, piece_file)
            piece_img = Image.open(piece_path)
            
            print(f"Processing {piece_file}...")
            
            result = multi_scale_template_match(
                puzzle_img=puzzle_img,
                piece_img=piece_img,
                use_downscale=True,
                num_pieces=24  # Hint: 24-piece puzzle
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
    print("3. Enable GPU acceleration if available")
