"""EXIF 방향 보정과 비율을 유지한 사진 크롭. 원본은 수정하지 않는다."""

import base64
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps


def image_data(path: Path, size: tuple[int, int], *, focal_x=0.5, focal_y=0.5,
               zoom=1.0, contain=False) -> str:
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGBA")
        if contain:
            image.thumbnail(size, Image.Resampling.LANCZOS)
        else:
            # 출력 종횡비와 확대율로 크롭 창을 계산한다. 초점은 창의 위치이다.
            ratio = size[0] / size[1]
            width = min(image.width, image.height * ratio) / zoom
            height = width / ratio
            left = (image.width - width) * focal_x
            top = (image.height - height) * focal_y
            image = image.crop((left, top, left + width, top + height))
            image = image.resize(size, Image.Resampling.LANCZOS)
        buffer = BytesIO()
        image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
