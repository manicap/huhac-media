# Third-party models used by optional processors

Model weights are not committed to this repository. Operators must obtain them
from the listed official upstream source and retain the upstream license when
redistributing a model.

## Faces Processor v1

### YuNet face detector

- Required file: `face_detection_yunet_2023mar.onnx`.
- Official weights: [OpenCV Zoo model file](https://github.com/opencv/opencv_zoo/blob/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx).
- Model documentation: [OpenCV Zoo YuNet README](https://github.com/opencv/opencv_zoo/blob/main/models/face_detection_yunet/README.md).
- Model license: [MIT License](https://github.com/opencv/opencv_zoo/blob/main/models/face_detection_yunet/LICENSE).
- Runtime/code: OpenCV Python bindings; OpenCV is distributed under
  [Apache License 2.0](https://github.com/opencv/opencv/blob/4.x/LICENSE).

Faces v1 deliberately uses this exact official 2023mar model identity. It does
not use InsightFace weights.

### Intel face-reidentification-retail-0095

- Required OpenVINO IR files: matching `.xml` and `.bin` files for
  `face-reidentification-retail-0095`; the CLI examples use FP32.
- Official model definition and download metadata:
  [Open Model Zoo model.yml](https://github.com/openvinotoolkit/open_model_zoo/blob/master/models/intel/face-reidentification-retail-0095/model.yml).
- Official model documentation:
  [Open Model Zoo README](https://github.com/openvinotoolkit/open_model_zoo/blob/master/models/intel/face-reidentification-retail-0095/README.md).
- Model repository/license: Open Model Zoo,
  [Apache License 2.0](https://github.com/openvinotoolkit/open_model_zoo/blob/master/LICENSE).
- Runtime/code: OpenVINO,
  [Apache License 2.0](https://github.com/openvinotoolkit/openvino/blob/master/LICENSE).

The supported upstream acquisition path is Open Model Zoo's model downloader,
for example `omz_downloader --name face-reidentification-retail-0095`. Review
the current upstream model card and license before redistribution.
