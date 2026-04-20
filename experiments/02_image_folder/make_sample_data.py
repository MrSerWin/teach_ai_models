"""Generate a tiny demo dataset so you can try the pipeline without real images.

Creates synthetic coloured images (red / green / blue) in ImageFolder layout:
  sample_data/
    train/red/*.png
    train/green/*.png
    train/blue/*.png
    val/red/*.png
    val/green/*.png
    val/blue/*.png

Then upload once:
  ./scripts/push-data.sh experiments/02_image_folder/sample_data demo_colors

And point config.yaml at: /mnt/d/datasets/demo_colors
"""
import random
from pathlib import Path

from PIL import Image

OUT = Path(__file__).parent / "sample_data"
CLASSES = {"red": (220, 40, 40), "green": (40, 200, 60), "blue": (40, 80, 220)}
SPLITS = {"train": 60, "val": 20}
SIZE = 64


def make_one(color: tuple[int, int, int]) -> Image.Image:
    jitter = lambda c: max(0, min(255, c + random.randint(-30, 30)))
    return Image.new("RGB", (SIZE, SIZE), tuple(jitter(c) for c in color))


def main() -> None:
    for split, n in SPLITS.items():
        for name, rgb in CLASSES.items():
            d = OUT / split / name
            d.mkdir(parents=True, exist_ok=True)
            for i in range(n):
                make_one(rgb).save(d / f"{i:03d}.png")
    print(f"wrote demo dataset -> {OUT}")


if __name__ == "__main__":
    main()
