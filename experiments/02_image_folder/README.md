# 02 — Image folder classification

Classify images using `torchvision.datasets.ImageFolder` + a pretrained backbone (ResNet18 by default). **The most common real-world pattern for computer vision: your own images organised by class in folders.**

## Task
Classify images into N classes. Folder name = class label.

## Required dataset layout (on the REMOTE, i.e. Windows/WSL)

```
/mnt/d/datasets/my_images/
├── train/
│   ├── cat/
│   │   ├── img_0001.jpg
│   │   ├── img_0002.jpg
│   │   └── ...
│   ├── dog/
│   │   ├── img_0001.jpg
│   │   └── ...
│   └── rabbit/
│       └── ...
└── val/
    ├── cat/
    ├── dog/
    └── rabbit/
```

**Rules:**
- Any number of classes, any class names — whatever you put in `train/`, the same classes must exist in `val/`.
- Accepted file formats: `.jpg`, `.jpeg`, `.png`, `.bmp`, `.gif`, `.webp` (anything PIL can open).
- No fixed image size needed — all images are resized to `image_size` from `config.yaml`.
- Rough rule-of-thumb: at least 50–100 images per class to get something meaningful; 500+ for good results.

## How to upload your data

1. Arrange your local folder to match the layout above:
   ```
   ~/my_images/
   ├── train/<class>/*.jpg
   └── val/<class>/*.jpg
   ```

2. Upload once:
   ```bash
   ./scripts/push-data.sh ~/my_images my_images
   # rsyncs to /mnt/d/datasets/my_images/ on the Windows box
   ```

3. Edit `config.yaml`:
   ```yaml
   data:
     dataset_path: /mnt/d/datasets/my_images
   ```

## Try it with a demo dataset (no real images needed)

Generates 60 synthetic train + 20 val images across 3 colour classes (`red`/`green`/`blue`):

```bash
# generate locally (needs pillow):
python experiments/02_image_folder/make_sample_data.py

# upload to the remote:
./scripts/push-data.sh experiments/02_image_folder/sample_data demo_colors

# point the config at it (already the default — or edit to match):
# config.yaml -> data.dataset_path: /mnt/d/datasets/demo_colors

# run:
./scripts/submit.sh experiments/02_image_folder
```

The demo trains to ~100% val accuracy in under a minute since the task is trivial (just classify solid colours) — it verifies the pipeline end-to-end on data you can inspect.

## Tune for your data

`config.yaml` knobs:

| Key              | Meaning                                                |
|------------------|--------------------------------------------------------|
| `image_size`     | All images resized to this square.                     |
| `batch_size`     | Lower if you run out of GPU memory.                    |
| `model.backbone` | Any `torchvision.models` name (`resnet50`, `efficientnet_b0`, `convnext_tiny`, ...) |
| `model.pretrained` | `true` = start from ImageNet weights (recommended).  |
| `train.epochs`   | 5–20 typically; more for from-scratch.                 |
| `train.lr`       | `1e-3` for AdamW finetuning is a solid default.        |

## Output
- `models/<exp-id>/final_model/model.pt` — dict `{state_dict, classes, backbone}` so you can reconstruct the model for inference.
- `models/<exp-id>/metrics.json` — final accuracy, per-epoch history, class names.
