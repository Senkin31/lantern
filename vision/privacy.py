"""Blur people (and their surroundings) on images that leave the city system, e.g. crops for the contractor.
YOLO11n detector (Ultralytics, AGPL-3.0, COCO) exported to ONNX; only the 'person' class is used.
Runs with onnxruntime + numpy + pillow."""
import os
import numpy as np
from PIL import Image, ImageFilter
HERE = os.path.dirname(os.path.abspath(__file__))


class PeopleBlur:
    def __init__(self, path=os.path.join(HERE, 'lantern_people.onnx'), conf=0.25, size=640):
        import onnxruntime as ort
        self.sess = ort.InferenceSession(path, providers=['CPUExecutionProvider']); self.conf, self.size = conf, size

    def detect(self, im: Image.Image):
        """Person boxes [x0, y0, x1, y1] in image pixels."""
        im = im.convert('RGB'); w, h = im.size; s = self.size / max(w, h)
        r = im.resize((round(w * s), round(h * s)), Image.BILINEAR)
        canvas = Image.new('RGB', (self.size, self.size), (114, 114, 114)); canvas.paste(r, (0, 0))
        x = np.asarray(canvas, np.float32).transpose(2, 0, 1)[None] / 255
        out = self.sess.run(None, {'images': x})[0][0]          # (84, 8400): cx, cy, w, h, 80 class scores
        score = out[4]; keep = score >= self.conf               # class 0 = person
        if not keep.any(): return []
        cx, cy, bw, bh = out[0][keep], out[1][keep], out[2][keep], out[3][keep]; sc = score[keep]
        boxes = np.stack([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], 1) / s
        order, res = np.argsort(-sc), []
        while len(order):                                       # simple NMS
            i = order[0]; res.append(boxes[i])
            xx0 = np.maximum(boxes[i, 0], boxes[order[1:], 0]); yy0 = np.maximum(boxes[i, 1], boxes[order[1:], 1])
            xx1 = np.minimum(boxes[i, 2], boxes[order[1:], 2]); yy1 = np.minimum(boxes[i, 3], boxes[order[1:], 3])
            inter = np.clip(xx1 - xx0, 0, None) * np.clip(yy1 - yy0, 0, None)
            area = lambda b: (b[..., 2] - b[..., 0]) * (b[..., 3] - b[..., 1])
            iou = inter / (area(boxes[i]) + area(boxes[order[1:]]) - inter + 1e-9)
            order = order[1:][iou < 0.5]
        return [[max(0, b[0]), max(0, b[1]), min(w, b[2]), min(h, b[3])] for b in res]

    def blur(self, im: Image.Image, pad=0.15) -> (Image.Image, int):
        """Returns (image with people blurred, number of people)."""
        im = im.convert('RGB').copy(); boxes = self.detect(im)
        for x0, y0, x1, y1 in boxes:
            px, py = (x1 - x0) * pad, (y1 - y0) * pad
            box = tuple(int(v) for v in (max(0, x0 - px), max(0, y0 - py), min(im.width, x1 + px), min(im.height, y1 + py)))
            if box[2] - box[0] < 2 or box[3] - box[1] < 2: continue
            region = im.crop(box); k = max(6, (box[2] - box[0]) // 4)
            im.paste(region.resize((max(1, region.width // k), max(1, region.height // k))).resize(region.size, Image.NEAREST).filter(ImageFilter.GaussianBlur(3)), box)
        return im, len(boxes)
