"""원본 영역과 출력 영역의 경계를 관리한다."""

from pathlib import Path


def output_directory(path: Path, root: Path) -> Path:
    """출력을 outputs/ 내부로 한정하고 심볼릭 링크 우회도 거부한다."""
    resolved = path.resolve()
    allowed = (root / "outputs").resolve()
    # outputs 자체가 원본 폴더의 링크가 된 경우도 거부한다.
    if allowed.is_relative_to((root / "data").resolve()):
        raise ValueError("outputs가 data 원본 영역을 가리킬 수 없습니다.")
    if not resolved.is_relative_to(allowed):
        raise ValueError("생성물은 프로젝트 outputs/ 내부에 저장하세요.")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def asset_path(path: Path, root: Path) -> Path:
    resolved = (root / path).resolve() if not path.is_absolute() else path.resolve()
    if not resolved.is_file():
        raise ValueError(f"자료 파일을 찾을 수 없습니다: {path}")
    return resolved
