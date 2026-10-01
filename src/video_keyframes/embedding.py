from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from PIL import Image

from video_keyframes.models import KeyframeConfig
from video_keyframes.selection import l2_normalize


class DependencyError(RuntimeError):
    pass


class OpenClipEmbedder:
    def __init__(self, config: KeyframeConfig, batch_size: int = 16):
        self.config = config
        self.batch_size = batch_size
        self._model = None
        self._preprocess = None

    @staticmethod
    def available() -> bool:
        return all(
            importlib.util.find_spec(name) is not None
            for name in ("numpy", "torch", "open_clip")
        )

    def _load(self):
        if self._model is not None:
            return
        if not self.available():
            raise DependencyError(
                "OpenCLIP dependencies are unavailable; install .[video-keyframes]"
            )
        import open_clip

        self._model, _, self._preprocess = open_clip.create_model_and_transforms(
            self.config.clip_model,
            pretrained=self.config.clip_pretrained,
            device=self.config.device,
        )
        self._model.eval()

    def embed(self, paths: tuple[Path, ...]) -> Any:
        self._load()
        import numpy as np
        import torch

        batches: list[Any] = []
        assert self._model is not None and self._preprocess is not None
        with torch.inference_mode():
            for offset in range(0, len(paths), self.batch_size):
                tensors = []
                for path in paths[offset : offset + self.batch_size]:
                    with Image.open(path) as image:
                        tensors.append(self._preprocess(image.convert("RGB")))
                batch = torch.stack(tensors).to(self.config.device)
                encoded = self._model.encode_image(batch)
                batches.append(encoded.float().cpu().numpy())
        return l2_normalize(np.concatenate(batches, axis=0))
