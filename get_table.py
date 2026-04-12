import requests
import re
from datetime import date
import os
from collections import defaultdict
from PIL import Image

response = requests.get("https://dreimetadaten.de/data/Serie.json")
if response.status_code == 200:
    series_data = response.json()
else:
    print(f"Failed to retrieve series data")

OUT_DIR = "covers"
TABLE_TEX = "table.tex"
MAX_COVER_HEIGHT_PX = 520
MAX_COVER_WIDTH_PX = 380
os.makedirs(OUT_DIR, exist_ok=True)

# remove entry 28 (Originalmusik)
series_data['serie'] = series_data['serie'][:28] + series_data['serie'][29:]

books = []


def download_cover(url: str, image_path: str) -> bool:
    r = requests.get(url)
    if r.status_code != 200:
        return False
    with open(image_path, "wb") as img_file:
        img_file.write(r.content)
    return True


def optimize_cover_image(image_path: str) -> None:
    with Image.open(image_path) as img:
        rgb_img = img.convert("RGB")
        rgb_img.thumbnail((MAX_COVER_WIDTH_PX, MAX_COVER_HEIGHT_PX), Image.Resampling.LANCZOS)
        rgb_img.save(image_path, format="JPEG", quality=82, optimize=True, progressive=True)


for entry in series_data['serie']:
    nr = entry['nummer']
    author = entry.get('autor', 'Unbekannt')
    release_date = entry.get('veröffentlichungsdatum') or "9999-12-31"
    cover_url = entry['links'].get('cover')
    if cover_url:
        img_path = os.path.join(OUT_DIR, f"cover_{nr}.jpg")
        if not os.path.exists(img_path):
            if download_cover(cover_url, img_path):
                optimize_cover_image(img_path)
        else:
            try:
                optimize_cover_image(img_path)
            except OSError:
                # Recover from previously truncated/corrupt files by downloading again.
                if download_cover(cover_url, img_path):
                    optimize_cover_image(img_path)
        books.append({
            "nr": nr,
            "author": author,
            "release_date": release_date,
            "cover_path": img_path
        })

# LaTeX table creation
def latex_escape(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    for char, escaped in replacements.items():
        text = text.replace(char, escaped)
    return text


def format_author_name(author: str) -> str:
    parts = [part.strip() for part in re.split(r"\s*(?:,|&)\s*", author) if part.strip()]
    escaped_parts = [latex_escape(part) for part in parts]
    if len(escaped_parts) <= 1:
        return escaped_parts[0] if escaped_parts else ""
    # Tighten spacing between multiple author lines in one cell.
    return r"\shortstack[l]{" + r"\\[-0.1em]".join(escaped_parts) + "}"


def parse_release_date(release_date: str) -> date:
    try:
        return date.fromisoformat(release_date)
    except ValueError:
        return date.max

by_author = defaultdict(list)
for book in books:
    by_author[book["author"]].append(book)

author_order = sorted(
    by_author.items(),
    key=lambda item: (
        min(parse_release_date(book["release_date"]) for book in item[1]),
        item[0].lower(),
    ),
)

lines: list[str] = []
lines.append("\\setlength{\\tabcolsep}{1.5pt}\n")
lines.append("\\renewcommand{\\arraystretch}{1.28}\n")
lines.append("\\begin{tabular}{>{\\raggedright\\arraybackslash}m{0.08\\textwidth} >{\\raggedright\\arraybackslash}m{0.92\\textwidth}}\n")
lines.append(r"\textbf{Autor} & \textbf{Cover} \\" + "\n")
lines.append("\\hline\n")
lines.append("\\noalign{\\vskip 0.18em}\n")

for author, author_books_raw in author_order:
    author_books = sorted(
        author_books_raw,
        key=lambda x: (parse_release_date(x["release_date"]), x["nr"]),
    )
    covers = " ".join(
        f"\\includegraphics[height=2.5cm,keepaspectratio]{{{b['cover_path']}}}"
        for b in author_books
    )
    lines.append(
        f"{format_author_name(author)} & {covers} \\\\\n"
    )

lines.append("\\end{tabular}\n")

with open(TABLE_TEX, "w", encoding="utf-8") as table_file:
    table_file.writelines(lines)
