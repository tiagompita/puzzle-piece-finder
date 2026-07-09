# Quick Start Guide

This quick guide will help you start using Puzzle Piece Finder in just a few minutes.

## ⚡ Quick Installation

```bash
# 1. Clone the repository
git clone https://github.com/BravooZ/puzzle-piece-finder.git
cd puzzle-piece-finder

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the GUI
python -m src.gui
```

## 🎮 First Use

### Graphical Interface (Recommended)

1. **Run GUI**: `python -m src.gui`
2. **Load Puzzle**: Click "Load Puzzle" → select a complete puzzle image
3. **Load Pieces**: Click "Load Pieces" → select one or more piece images
4. **Execute Matching**: Click "Match" for one piece or "Match All Pieces" for all

### Command Line

```bash
# Run interactive CLI
python -m src.main

# Follow the on-screen instructions to:
# 1. Select puzzle image
# 2. Select piece image
# 3. View matching results
```

## 📊 Interpreting Results

### Main Metrics

- **Position**: Coordinates (x, y) where the piece was found
- **Similarity**: 0-100% correspondence (>80% is very good)
- **Scale**: Scaling factor applied to the piece
- **GPU**: Whether hardware acceleration was used

### Example Output

```
✅ Piece 1: pos=(245, 167), similarity=87.3%, scale=0.85
```

This means:
- The piece was found at position (245, 167)
- 87.3% confidence in matching (excellent)
- The piece was resized to 85% of original size

## 🔧 Important Settings

### For Better Performance
- ✅ Enable "Downscale" for large puzzles (>1500px)
- ✅ Use "GPU" if you have OpenCV with CUDA
- ✅ Set "#Pieces" with the actual number of pieces

### For Maximum Precision
- ❌ Disable "Downscale" for small puzzles
- ✅ Set real dimensions in cm
- ✅ Use high-quality images

## 🚨 Common Problems

### "GPU not available"
- Normal if you don't have CUDA installed
- System uses CPU automatically
- Performance is still good for most cases

### "Very low similarity (<50%)"
- Check if it's the correct piece
- Try adjusting "#Pieces"
- Piece might be at a very different scale

### GUI freezes during matching
- Use "Cancel" to interrupt
- Reduce image sizes
- Enable "Downscale"

## 📈 Next Steps

1. **Experiment** with your own puzzle images
2. **Set up GPU** following the guide in main README
3. **Explore** examples in `examples/basic_usage.py`
4. **Contribute** improvements following `CONTRIBUTING.md`

## 🆘 Need Help?

- **Bug or error**: [Open an issue](https://github.com/BravooZ/puzzle-piece-finder/issues)
- **Questions**: [GitHub Discussions](https://github.com/BravooZ/puzzle-piece-finder/discussions)
- **Complete documentation**: See `README.md`

---

**Ready! You can now start solving puzzles with AI! 🧩✨**
