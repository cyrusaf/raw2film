"""Simple command-line entrypoint: raw2film render / compare / export-lut / demo."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

from .color import export_cube, load_profile
from .gallery import make_gallery
from .render import render_file
from .io import RAW_EXTENSIONS, RGB_EXTENSIONS, validate_output_paths

FILMS = ["portra400", "gold200", "classic_chrome", "classic_negative"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="raw2film", description="RAW film-inspired photo developer")
    parser.add_argument("--version", action="version", version="raw2film 0.1.0")
    commands = parser.add_subparsers(dest="command", required=True)
    render = commands.add_parser("render", help="Develop a RAW/JPEG/PNG image with one film look")
    render.add_argument("input", type=Path)
    render.add_argument("--look", "--film", "--stock", dest="film", choices=["neutral", *FILMS], default="portra400")
    render.add_argument("--output", type=Path)
    compare = commands.add_parser("compare", help="Generate HTML gallery with all four looks")
    compare.add_argument("input", type=Path)
    compare.add_argument("--output", type=Path, help="Output directory")
    batch = commands.add_parser("batch", help="Render every supported image in a directory")
    batch.add_argument("input", type=Path, help="Directory containing photos")
    batch.add_argument("--look", "--film", "--stock", dest="film", choices=["neutral", *FILMS], default="portra400")
    batch.add_argument("--output", type=Path, default=Path("raw2film-batch"))
    lut = commands.add_parser("export-lut", help="Export a display-sRGB .cube LUT")
    lut.add_argument("--look", "--film", "--stock", dest="film", choices=FILMS, required=True)
    lut.add_argument("--size", type=int, default=33)
    lut.add_argument("--output", type=Path)
    demo = commands.add_parser("demo", help="Create a synthetic demo image + film gallery")
    demo.add_argument("--output", type=Path, default=Path("raw2film-demo"))
    serve = commands.add_parser("serve", help="Open the local interactive RAW editor")
    serve.add_argument("--input-dir", type=Path, help="Optional folder of photos to show in the editor")
    serve.add_argument("--port", type=int, default=8843)
    for p in (render, compare, batch):
        p.add_argument("--exposure", type=float, default=0, help="Exposure compensation in stops")
        p.add_argument("--auto-exposure", action="store_true", help="Simple optional median-based auto exposure")
        p.add_argument("--no-grain", action="store_true")
        p.add_argument("--grain-multiplier", type=float, default=1.0)
        p.add_argument("--strength", type=float, default=1.0, help="Look strength 0-3 (1 = original profile)")
        p.add_argument("--max-edge", type=int, default=1600 if p is compare else None,
                       help="Resize longest edge in px (comparison defaults to 1600)")
        p.add_argument("--seed", type=int, default=42, help="Deterministic grain seed")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "serve":
            from .server import run_server
            run_server(input_dir=args.input_dir, port=args.port)
        elif args.command == "export-lut":
            dest = args.output or Path(f"{args.film}.cube")
            print(export_cube(load_profile(args.film), dest, size=args.size))
        elif args.command == "render":
            dest = args.output or Path(f"{args.input.stem}_{args.film}.jpg")
            print(render_file(args.input, dest, args.film, args.exposure,
                              args.auto_exposure, not args.no_grain,
                              args.grain_multiplier, args.strength,
                              args.max_edge, args.seed))
        elif args.command == "batch":
            if not args.input.is_dir():
                raise ValueError("batch input must be an existing directory")
            inputs = sorted(x for x in args.input.iterdir() if x.is_file() and
                            x.suffix.lower() in RAW_EXTENSIONS | RGB_EXTENSIONS)
            if not inputs:
                raise ValueError("No supported image files found in input directory")
            destinations = [args.output / f"{src.stem}_{args.film}.jpg" for src in inputs]
            validate_output_paths(inputs, destinations)
            for src, dest in zip(inputs, destinations):
                print(render_file(src, dest, args.film, args.exposure,
                                  args.auto_exposure, not args.no_grain,
                                  args.grain_multiplier, args.strength,
                                  args.max_edge, args.seed))
            print(f"Rendered {len(inputs)} file(s)")
        elif args.command == "compare":
            dest = args.output or Path("raw2film-output") / args.input.stem
            print(make_gallery(args.input, dest, args.exposure, args.auto_exposure,
                               args.max_edge, not args.no_grain,
                               args.grain_multiplier, args.strength, args.seed))
        elif args.command == "demo":
            from .demo import create_demo
            src = create_demo(args.output / "demo-input.png")
            print(make_gallery(src, args.output / "gallery", max_edge=1200))
        return 0
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        print(f"raw2film: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
