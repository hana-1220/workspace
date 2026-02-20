#!/usr/bin/env python3
"""
PDF → ページ別PNG変換ユーティリティ

使い方:
  python pdf_to_images.py input/heatmap.pdf
  → pdf_pages/page_01.png, page_02.png, ... が生成される

依存: poppler (brew install poppler)
"""

import os
import sys

from pdf2image import convert_from_path


def pdf_to_images(pdf_path, output_dir="pdf_pages", dpi=200):
    """PDFファイルをページ別PNGに変換する。"""
    if not os.path.exists(pdf_path):
        print(f"❌ ファイルが見つかりません: {pdf_path}")
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)

    print(f"📄 PDF読み込み中: {pdf_path}")
    pages = convert_from_path(pdf_path, dpi=dpi)

    output_files = []
    for i, page in enumerate(pages, 1):
        filename = os.path.join(output_dir, f"page_{i:02d}.png")
        page.save(filename, "PNG")
        output_files.append(filename)
        print(f"  ✅ {filename}")

    print(f"\n🎉 {len(pages)}ページを変換しました → {output_dir}/")
    return output_files


def main():
    if len(sys.argv) < 2:
        print("使い方: python pdf_to_images.py <PDFファイルパス> [出力ディレクトリ] [DPI]")
        print("例:     python pdf_to_images.py input/heatmap.pdf")
        print("        python pdf_to_images.py input/heatmap.pdf pdf_pages 300")
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "pdf_pages"
    dpi = int(sys.argv[3]) if len(sys.argv) > 3 else 200

    pdf_to_images(pdf_path, output_dir, dpi)


if __name__ == "__main__":
    main()
