"""Local OCR grouping experiment. Does not call remote APIs or alter source frames."""

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path


def signature(text: str) -> str:
    """Normalize case/spacing and numeric range dashes; preserve other punctuation."""
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = re.sub(r"(?<=\d)\s*[-–—•]\s*(?=\d)", "-", normalized)
    return " ".join(normalized.split())


def prepare(source: Path, output: Path, mode: str) -> None:
    from PIL import Image

    if output.exists():
        raise RuntimeError("Choose a fresh prepared-frame directory")
    output.mkdir(parents=True)
    for path in sorted(source.glob("frame-*.jpg")):
        with Image.open(path) as image:
            image = image.convert("RGB")
            if mode != "full-scale":
                # Manual ROI for this single story; NOT a universal detector.
                image = image.crop((40, 510, 700, 800))
            if mode in ("yellow-mask", "white-mask"):
                mask = Image.new("L", image.size)
                pixels = image.get_flattened_data()
                mask.putdata(
                    [
                        0
                        if (
                            (
                                red > 170
                                and green > 140
                                and red > blue * 1.4
                                and green > blue * 1.3
                            )
                            if mode == "yellow-mask"
                            else (
                                min(red, green, blue) > 170
                                and max(red, green, blue) - min(red, green, blue) < 50
                            )
                        )
                        else 255
                        for red, green, blue in pixels
                    ]
                )
                image = mask.convert("RGB")
            image = image.resize(
                (image.width * 2, image.height * 2), Image.Resampling.LANCZOS
            )
            image.save(output / path.name, quality=98)
    (output / "preprocessing.json").write_text(
        json.dumps(
            {
                "mode": mode,
                "scale": 2,
                "manual_roi": None if mode == "full-scale" else [40, 510, 700, 800],
                "yellow_mask_excludes_white_text": mode == "yellow-mask",
                "white_mask_excludes_yellow_text": mode == "white-mask",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Prepared {len(list(output.glob('frame-*.jpg')))} frames: {mode}")


def group(report: Path, output: Path) -> None:
    data = json.loads(report.read_text(encoding="utf-8-sig"))
    groups = defaultdict(list)
    for frame in data["results"]:
        text = signature(frame["text"])
        # Empty OCR is uncertainty, not duplicate evidence.
        key = text if text else f"unreadable:{frame['file']}"
        groups[key].append(frame["file"])
    result = {
        "source_frames": len(data["results"]),
        "exact_text_groups": len(groups),
        "groups": [{"text": key, "files": files} for key, files in groups.items()],
        "warning": "Equality of OCR strings does not prove completeness or visual equivalence.",
    }
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def make_controls(output: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    if output.exists():
        raise RuntimeError("Choose a fresh controls directory")
    output.mkdir(parents=True)
    baseline = "9 - 13 декабря\nВаршава Дрезден Прага\n100 EUR\nдля туристов с визами"
    texts = [
        baseline,
        baseline,
        baseline.replace("9 - 13", "10 - 13"),
        baseline.replace("100", "101"),
        baseline.replace("с визами", "без виз"),
        baseline.replace("EUR", "USD"),
        baseline.replace("Прага", "Вена"),
        "",
    ]
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 52)
    for index, text in enumerate(texts):
        image = Image.new("RGB", (1200, 400), "white")
        ImageDraw.Draw(image).multiline_text(
            (35, 30), text, font=font, fill="black", spacing=15
        )
        image.save(output / f"frame-{index:03}.jpg", quality=98)
    print("Prepared 8 synthetic OCR controls: duplicate, five important changes, blank")


def controls(report: Path | None = None) -> None:
    original = "9–13 декабря Варшава Дрезден Прага для туристов с визами 100 EUR"
    for changed in (
        original.replace("9–13", "10–13"),
        original.replace("100", "101"),
        original.replace("EUR", "USD"),
        original.replace("с визами", "без виз"),
        original.replace("Прага", "Вена"),
    ):
        assert signature(original) != signature(changed), "Important change was merged"
    assert signature("9–13 ДЕКАБРЯ") == signature("9 - 13 декабря")
    # These represent separate dates, so punctuation boundaries must not join numbers.
    assert signature("9–13") != signature("913")
    assert signature("100 €") != signature("100 $")
    assert signature("100%") != signature("100")
    assert signature("-100") != signature("100")
    assert signature("example.com/a") != signature("example.com.a")
    print(
        "Controls passed: date, price, currency, visa condition and city changes differ"
    )
    if report is not None:
        frames = json.loads(report.read_text(encoding="utf-8-sig"))["results"]
        texts = [signature(frame["text"]) for frame in frames]
        assert len(texts) == 8
        assert texts[0] == texts[1] and texts[0], "Duplicate control not recognized"
        assert all(texts[0] != changed for changed in texts[2:7]), (
            "OCR lost an important change"
        )
        assert texts[7] == "", "Blank OCR fixture is not blank"
        for index, expected in (
            (2, "10-13"),
            (3, "101"),
            (4, "без виз"),
            (5, "usd"),
            (6, "вена"),
        ):
            assert expected in texts[index], (
                "Changed fixture value was not actually read"
            )
        print(
            "Image controls passed: actual Windows OCR preserves five changed conditions"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("prepare", "group", "controls", "make-controls")
    )
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--mode", choices=("full-scale", "ad-crop", "yellow-mask", "white-mask")
    )
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.source, args.output, args.mode)
    elif args.action == "group":
        group(args.source, args.output)
    elif args.action == "make-controls":
        make_controls(args.output)
    else:
        controls(args.source)


if __name__ == "__main__":
    main()
