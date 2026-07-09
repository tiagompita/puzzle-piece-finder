# 🧩 Puzzle Piece Finder

An intelligent recognition and localization system for puzzle pieces using advanced computer vision algorithms.

<div align="center">

![Python](https://img.shields.io/badge/Python-3.8+-blue?style=for-the-badge&logo=python)
![OpenCV](https://img.shields.io/badge/OpenCV-4.0+-green?style=for-the-badge&logo=opencv)
![Pillow](https://img.shields.io/badge/Pillow-8.0+-orange?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-red?style=for-the-badge)

[![GitHub stars](https://img.shields.io/github/stars/BravooZ/puzzle-piece-finder?style=social)](https://github.com/BravooZ/puzzle-piece-finder/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/BravooZ/puzzle-piece-finder?style=social)](https://github.com/BravooZ/puzzle-piece-finder/network)
[![GitHub issues](https://img.shields.io/github/issues/BravooZ/puzzle-piece-finder)](https://github.com/BravooZ/puzzle-piece-finder/issues)
[![GitHub pull requests](https://img.shields.io/github/issues-pr/BravooZ/puzzle-piece-finder)](https://github.com/BravooZ/puzzle-piece-finder/pulls)

</div>

## 📖 About The Project

This project implements an automated system for solving physical puzzles through image analysis. The system can:
- **Locate individual pieces** within the complete puzzle
- **Calculate similarity** between pieces and puzzle regions
- **Optimize matching** with multi-scale and GPU acceleration
- **Intuitive graphical interface** for easy usage
- **Detailed metrics analysis** for each piece

### 🎯 Key Features

- **Multi-scale Template Matching**: Optimized algorithms to find pieces at different scales
- **GPU/CUDA Support**: Hardware acceleration for fast processing
- **Tkinter Graphical Interface**: Complete GUI with result visualization
- **Similarity Analysis**: Advanced metrics for color and shape correspondence
- **Overlap Detection**: Automatic identification of conflicts between pieces
- **Result Export**: Data saving in JSON format

## 📁 Project Structure

```
puzzle_piece_finder/
├── src/                          # Main source code
│   ├── acquisition.py            # Image loading and preprocessing
│   ├── features.py               # Image feature extraction
│   ├── matching.py               # Matching and comparison algorithms
│   ├── gui.py                    # Graphical user interface
│   ├── main.py                   # Main script (CLI)
│   ├── segmentation.py           # Segmentation module (in development)
│   └── visualization.py          # Visualization functions (in development)
├── images/                       # Example data
│   ├── puzzles/                  # Complete puzzle images
│   └── pieces/                   # Individual piece images
│       ├── piece_0.png → piece_23.png  # 24 example pieces
│       └── puzzle.json           # Piece metadata
├── data/                         # Processed data and cache
├── notebooks/                    # Jupyter notebooks for analysis
├── requirements.txt              # Python dependencies
└── README.md                     # This file
```

## 🚀 Installation and Setup

### Prerequisites

- **Python 3.8+**
- **Pip** (Python package manager)
- **Git** (for repository cloning)

### 1. Clone the Repository

```bash
git clone https://github.com/BravooZ/puzzle-piece-finder.git
cd puzzle-piece-finder
```

### 2. Create Virtual Environment

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Linux/macOS
python -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Main Dependencies

```
Pillow>=8.0.0          # Image manipulation
opencv-python>=4.5.0   # Computer vision
numpy>=1.21.0          # Numerical computing
tkinter                # Graphical interface (included with Python)
```

## 💻 How to Use

### Graphical Interface (Recommended)

```bash
python -m src.gui
```

The graphical interface offers:
- **Visual loading** of puzzles and pieces
- **Real-time parameter configuration**
- **Result visualization** with overlays
- **Individual or batch matching** controls
- **Automatic statistical analysis**

### Command Line Interface

```bash
python -m src.main
```

For programmatic usage:

```python
from src.acquisition import load_puzzle, load_piece
from src.matching import multi_scale_template_match

# Load images
puzzle_img = load_puzzle()
piece_img = load_piece()

# Execute matching
result = multi_scale_template_match(
    puzzle_img=puzzle_img,
    piece_img=piece_img,
    use_gpu=True,
    use_downscale=True
)

print(f"Best position: {result['best_position']}")
print(f"Similarity: {result['refined_similarity']:.2%}")
```

## 🔧 Advanced Features

### GPU Acceleration (CUDA)

To enable GPU acceleration, you need OpenCV compiled with CUDA:

#### Check CUDA Support
```python
import cv2
print("CUDA enabled:", cv2.cuda.getCudaEnabledDeviceCount() > 0)
```

#### OpenCV-CUDA Installation (Windows)
1. **Install NVIDIA CUDA Toolkit** (12.x recommended)
2. **Visual Studio Build Tools** with C++
3. **Compile OpenCV** with CUDA flags enabled

```bash
# Quick verification
python -c "import cv2; print('CUDA devices:', cv2.cuda.getCudaEnabledDeviceCount())"
```

### Performance Settings

#### For Large Puzzles (>2000px)
```python
result = multi_scale_template_match(
    puzzle_img=puzzle,
    piece_img=piece,
    use_downscale=True,    # Automatic downscaling
    use_gpu=True,          # If available
    method='SQDIFF_NORMED' # Fastest method
)
```

#### For Maximum Precision
```python
result = multi_scale_template_match(
    puzzle_img=puzzle,
    piece_img=piece,
    use_downscale=False,   # Full resolution
    num_pieces=24,         # Hint for better scale
    method='CCORR_NORMED'  # Most accurate method
)
```

## 📊 Results Analysis

### Available Metrics

- **Optimal Position**: Coordinates (x, y) of the best location
- **Scale Factor**: Scaling applied to the piece
- **Similarity**: 0-100% matching score
- **Coverage**: Percentage of puzzle area occupied
- **Overlap Detection**: Identification of conflicts

### Example Output

```json
{
  "best_position": [245, 167],
  "scale": 0.85,
  "refined_similarity": 0.847,
  "piece_size_final": [120, 98],
  "candidates_considered": 6,
  "gpu_used": true
}
```

## 🛠️ Development

### Modular Architecture

- **`acquisition.py`**: Data input and validation
- **`features.py`**: Visual feature extraction
- **`matching.py`**: Correspondence algorithms
- **`gui.py`**: Complete graphical interface
- **`main.py`**: Orchestration and CLI

### Implemented Algorithms

1. **Multi-scale Template Matching**
   - Automatic scale candidates
   - Full-resolution refinement
   - Downscaling optimization

2. **Feature Analysis**
   - Dominant colors
   - Area calculations
   - Real scale estimation

3. **Optimized Matching**
   - Configurable stride for speed
   - Hybrid GPU/CPU processing
   - Intermediate result caching

### Contributing

1. **Fork** the repository
2. **Create** a branch for your feature (`git checkout -b feature/new-feature`)
3. **Commit** your changes (`git commit -m 'Add new feature'`)
4. **Push** to the branch (`git push origin feature/new-feature`)
5. **Open** a Pull Request

## 📈 Roadmap

### In Development
- [ ] **Automatic segmentation** of pieces from complete puzzle
- [ ] **Edge analysis** for corner/border pieces
- [ ] **Color clustering** for intelligent grouping
- [ ] **Visual export** of results (annotated images)

### Future
- [ ] **Machine Learning** for piece classification
- [ ] **Advanced geometric shape analysis**
- [ ] **REST API** for external integration
- [ ] **Docker** containerization

## ⚡ Performance and Optimization

### Typical Benchmarks

| Configuration | Time (24 pieces) | GPU | Accuracy |
|---------------|------------------|-----|----------|
| CPU + Downscale | ~15s | ❌ | 85-90% |
| CPU Full-Res | ~45s | ❌ | 90-95% |
| GPU + Downscale | ~8s | ✅ | 85-90% |
| GPU Full-Res | ~20s | ✅ | 90-95% |

### Optimization Tips

- **Use downscaling** for puzzles >1500px
- **GPU recommended** for batches >10 pieces
- **Reduce scale candidates** for specific cases
- **Cache results** for repetitive analyses

## 🔍 Troubleshooting

### Common Issues

#### OpenCV/CUDA not working
```bash
# Check installation
python -c "import cv2; print(cv2.getBuildInformation())"
```

#### Insufficient memory
- Reduce image sizes
- Enable `use_downscale=True`
- Process pieces individually

#### Slow performance
- Check if GPU is being used
- Reduce sliding window `stride`
- Use optimized image format (PNG)

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
