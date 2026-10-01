---
title: BG Remover
emoji: ✂️
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# BG Remover

AI background removal tool built with FastAPI, rembg (U²-Net / ISNet), and ONNX Runtime.

- Three model options: fast, balanced, quality
- Processed in memory, nothing is stored
- Auto-uses GPU when CUDA is available, otherwise CPU

## Run locally

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

For an NVIDIA GPU, replace `onnxruntime` with `onnxruntime-gpu`.
