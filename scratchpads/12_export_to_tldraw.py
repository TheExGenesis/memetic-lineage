#!/usr/bin/env python3
"""
Generate square images for each strand with:
- AI-generated thumbnail (via Runware/Flux)
- Title + two emojis
- One-liner summary (from Groq)
- Full summary in small font
"""
# %%
import io
import json
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import wraps
from pathlib import Path
from typing import Callable, Optional, Tuple, Type, TypedDict, TypeVar

import httpx
from dotenv import load_dotenv
from groq import Groq
from PIL import Image, ImageDraw, ImageFont
from tqdm import tqdm

load_dotenv(Path(__file__).parent.parent / ".env")

# Cache directory for generated thumbnails
THUMBNAIL_CACHE_DIR = Path(__file__).parent / "data" / "strand_thumbnails"
THUMBNAIL_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# --- Inline retry utility ---
T = TypeVar('T')

def with_retry(
    max_retries: int = 5,
    base_delay: float = 1.0,
    retryable_errors: Tuple[Type[Exception], ...] = (Exception,),
):
    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @wraps(fn)
        def wrapper(*args, **kwargs) -> T:
            for attempt in range(max_retries):
                try:
                    return fn(*args, **kwargs)
                except retryable_errors as e:
                    if attempt == max_retries - 1:
                        raise
                    delay = base_delay * (2 ** attempt)
                    print(f"Retry {attempt + 1}/{max_retries} in {delay:.1f}s: {type(e).__name__}: {e}")
                    time.sleep(delay)
            raise RuntimeError("Unreachable")
        return wrapper
    return decorator

# Paths
FRESH_STRANDS_DIR = Path(__file__).parent / "data" / "fresh_rated_strands"
OUTPUT_DIR = Path(__file__).parent / "data" / "strand_imgs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
SERIATION_ORDER_PATH = Path(__file__).parent.parent / "top-qt-website" / "bangers" / "public" / "strand_seriation_order.json"

# Load seriation order for filename ordering
def load_seriation_order() -> dict[str, int]:
    """Load seriation order and return mapping from seed_id to position."""
    if not SERIATION_ORDER_PATH.exists():
        print(f"[WARN] Seriation order file not found: {SERIATION_ORDER_PATH}")
        return {}
    
    with open(SERIATION_ORDER_PATH) as f:
        data = json.load(f)
    
    # Create mapping: seed_id -> position (0-indexed)
    return {item["id"]: idx for idx, item in enumerate(data.get("order", []))}

SERIATION_ORDER = load_seriation_order()

# Image config
IMG_SIZE = 1330  # 30% larger than 1024
PADDING = 52
BG_COLOR = "#0d1117"  # Dark GitHub-style background
TITLE_COLOR = "#e6edf3"
ONELINER_COLOR = "#7ee787"  # Green accent
SUMMARY_COLOR = "#848d97"  # Muted gray
RATING_COLOR = "#f0883e"  # Orange for rating
ESSENTIAL_COLOR = "#58a6ff"  # Blue for essential tweets


class StrandMeta(TypedDict):
    emojis: str
    oneliner: str
    image_prompt: str


def get_groq_client() -> Groq:
    return Groq(api_key=os.environ.get("GROQ_API_KEY"))


@with_retry(max_retries=3, base_delay=2.0)
def get_strand_meta(title: str, summary: str) -> StrandMeta:
    """Get two emojis, a one-liner summary, and an image generation prompt from Groq."""
    client = get_groq_client()
    
    prompt = f"""Given this strand title and summary, provide:
1. Exactly TWO emojis that capture the essence/vibe of this strand (no text, just emojis)
2. A punchy one-liner summary (max 15 words, catchy/memorable)
3. A vivid image generation prompt (for Flux/Stable Diffusion) that would make a great blog post thumbnail. 
   - Should be visual, artistic, evocative of the thread's theme
   - NO text in the image, just visual elements
   - Think: what single image captures the vibe/essence of this thread?
   - Be specific about style, lighting, composition
   - Max 100 words

Title: {title}

Summary: {summary[:2000]}

Respond in this exact JSON format:
{{"emojis": "🔥💡", "oneliner": "Your catchy one-liner here", "image_prompt": "A detailed visual description..."}}"""

    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.9,
        max_completion_tokens=300,
        response_format={"type": "json_object"},
    )
    
    content = completion.choices[0].message.content or "{}"
    parsed = json.loads(content)
    return StrandMeta(
        emojis=parsed.get("emojis", "📝✨")[:4],
        oneliner=parsed.get("oneliner", "A fascinating thread exploration")[:100],
        image_prompt=parsed.get("image_prompt", "Abstract digital art with flowing colors")[:500]
    )


@with_retry(max_retries=3, base_delay=3.0)
def generate_thumbnail(seed_id: str, image_prompt: str) -> Optional[Image.Image]:
    """Generate a thumbnail image using Runware API with Flux Dev model."""
    # Check cache first
    cache_path = THUMBNAIL_CACHE_DIR / f"{seed_id}.png"
    if cache_path.exists():
        return Image.open(cache_path)
    
    api_key = os.environ.get("RUNWARE_API_KEY")
    if not api_key:
        print(f"[WARN] No RUNWARE_API_KEY set, skipping thumbnail for {seed_id}")
        return None
    
    # Runware API request
    request_data = [
        {
            "taskType": "imageInference",
            "taskUUID": str(uuid.uuid4()),
            "positivePrompt": image_prompt,
            "model": "runware:101@1",  # Flux Dev
            "width": 512,
            "height": 512,
            "numberResults": 1,
            "outputFormat": "PNG",
        }
    ]
    
    try:
        response = httpx.post(
            "https://api.runware.ai/v1",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=request_data,
            timeout=120.0,
        )
        response.raise_for_status()
        
        result = response.json()
        
        # Extract image URL from response
        if "data" in result and len(result["data"]) > 0:
            image_data = result["data"][0]
            image_url = image_data.get("imageURL")
            
            if image_url:
                # Download the image
                img_response = httpx.get(image_url, timeout=30.0)
                img_response.raise_for_status()
                
                img = Image.open(io.BytesIO(img_response.content))
                
                # Cache it
                img.save(cache_path, "PNG")
                return img
        
        print(f"[WARN] No image URL in Runware response for {seed_id}")
        return None
        
    except Exception as e:
        print(f"[ERROR] Runware API failed for {seed_id}: {e}")
        raise


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Try to load a nice font, fall back to default."""
    font_paths = [
        # macOS
        "/System/Library/Fonts/SFNSMono.ttf",
        "/Library/Fonts/SF-Pro-Display-Bold.otf" if bold else "/Library/Fonts/SF-Pro-Display-Regular.otf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        # Linux
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    
    for path in font_paths:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    
    return ImageFont.load_default()


def load_emoji_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a font that supports emoji rendering."""
    emoji_font_paths = [
        # macOS - Apple Color Emoji
        "/System/Library/Fonts/Apple Color Emoji.ttc",
        # Alternative macOS paths
        "/System/Library/Fonts/AppleColorEmoji.ttf",
        # Linux - Noto Color Emoji
        "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
        "/usr/share/fonts/noto-emoji/NotoColorEmoji.ttf",
        # Fallback to regular font
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    
    for path in emoji_font_paths:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    
    return load_font(size)


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Wrap text to fit within max_width pixels."""
    words = text.split()
    lines = []
    current_line = ""
    
    for word in words:
        test_line = f"{current_line} {word}".strip()
        bbox = font.getbbox(test_line)
        if bbox[2] <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    
    if current_line:
        lines.append(current_line)
    
    return lines


def draw_histogram(
    draw: ImageDraw.Draw,
    counts: list[int],
    x: int,
    y: int,
    width: int,
    height: int,
    date_range: dict
):
    """Draw a mini histogram chart."""
    if not counts or max(counts) == 0:
        return
    
    # Filter to non-zero range for better visualization
    first_nonzero = next((i for i, c in enumerate(counts) if c > 0), 0)
    last_nonzero = len(counts) - 1 - next((i for i, c in enumerate(reversed(counts)) if c > 0), 0)
    counts = counts[first_nonzero:last_nonzero + 1]
    
    if not counts:
        return
    
    max_count = max(counts)
    bar_width = max(1, width // len(counts))
    
    # Draw bars
    for i, count in enumerate(counts):
        if count == 0:
            continue
        bar_height = int((count / max_count) * height)
        bar_x = x + i * bar_width
        bar_y = y + height - bar_height
        
        # Gradient color based on intensity
        intensity = count / max_count
        r = int(88 + intensity * 80)
        g = int(166 + intensity * 50)
        b = int(255 - intensity * 50)
        color = f"#{r:02x}{g:02x}{b:02x}"
        
        draw.rectangle(
            [bar_x, bar_y, bar_x + bar_width - 1, y + height],
            fill=color
        )
    
    # Draw date labels
    label_font = load_font(11)
    start_year = date_range.get("start", "")[:4]
    end_year = date_range.get("end", "")[:4]
    draw.text((x, y + height + 3), start_year, font=label_font, fill="#6e7681")
    end_label_bbox = label_font.getbbox(end_year)
    draw.text((x + width - (end_label_bbox[2] - end_label_bbox[0]), y + height + 3), end_year, font=label_font, fill="#6e7681")


def create_strand_image(
    seed_id: str,
    title: str,
    summary: str,
    emojis: str,
    oneliner: str,
    rating: int,
    essential_tweets: list[dict],
    histogram: dict,
    thumbnail: Optional[Image.Image] = None
) -> Path:
    """Create a square image for a strand."""
    img = Image.new("RGB", (IMG_SIZE, IMG_SIZE), BG_COLOR)
    draw = ImageDraw.Draw(img)
    
    # Load fonts - BIG title (to take 30-50% of image)
    title_font = load_font(90, bold=True)
    emoji_font = load_emoji_font(48)
    oneliner_font = load_font(28)
    summary_font = load_font(14)
    rating_font = load_font(36, bold=True)
    essential_font = load_font(12)
    small_font = load_font(11)
    
    max_text_width = IMG_SIZE - (PADDING * 2)
    y_pos = PADDING
    
    # === TOP ROW: Emojis (left) | Thumbnail (center) | Rating (right) ===
    thumbnail_size = 200
    side_width = (IMG_SIZE - thumbnail_size) // 2 - PADDING
    
    # Draw emojis on the LEFT
    try:
        draw.text(
            (PADDING, y_pos + 70),
            emojis,
            font=emoji_font,
            fill=TITLE_COLOR,
            embedded_color=True
        )
    except Exception:
        draw.text(
            (PADDING, y_pos + 70),
            emojis,
            font=load_font(48),
            fill=TITLE_COLOR
        )
    
    # Draw rating on the RIGHT
    rating_text = f"★ {rating}/10"
    rating_bbox = rating_font.getbbox(rating_text)
    rating_width = rating_bbox[2] - rating_bbox[0]
    draw.text(
        (IMG_SIZE - PADDING - rating_width, y_pos + 70),
        rating_text,
        font=rating_font,
        fill=RATING_COLOR
    )
    
    # Draw thumbnail in CENTER
    if thumbnail:
        thumb_resized = thumbnail.resize((thumbnail_size, thumbnail_size), Image.Resampling.LANCZOS)
        thumb_x = (IMG_SIZE - thumbnail_size) // 2
        img.paste(thumb_resized, (thumb_x, y_pos))
    
    y_pos += thumbnail_size + 25
    
    # === BIG TITLE (30-50% of image height) ===
    # With 90px font, each line is ~100px, so 4 lines = 400px ≈ 30% of 1330
    title_lines = wrap_text(title, title_font, max_text_width)
    for line in title_lines[:4]:  # Up to 4 lines
        bbox = title_font.getbbox(line)
        line_width = bbox[2] - bbox[0]
        draw.text(
            ((IMG_SIZE - line_width) // 2, y_pos),
            line,
            font=title_font,
            fill=TITLE_COLOR
        )
        y_pos += 100
    
    y_pos += 15
    
    # === ONE-LINER ===
    oneliner_lines = wrap_text(f'"{oneliner}"', oneliner_font, max_text_width - 40)
    for line in oneliner_lines[:2]:
        bbox = oneliner_font.getbbox(line)
        line_width = bbox[2] - bbox[0]
        draw.text(
            ((IMG_SIZE - line_width) // 2, y_pos),
            line,
            font=oneliner_font,
            fill=ONELINER_COLOR
        )
        y_pos += 36
    
    y_pos += 15
    
    # === HISTOGRAM ===
    hist_counts = histogram.get("counts", [])
    hist_date_range = histogram.get("date_range", {})
    total_tweets = histogram.get("total_tweets", 0)
    
    if hist_counts:
        hist_width = 260
        hist_height = 35
        hist_x = (IMG_SIZE - hist_width) // 2
        
        hist_label = f"Activity ({total_tweets} tweets)"
        label_bbox = small_font.getbbox(hist_label)
        label_width = label_bbox[2] - label_bbox[0]
        draw.text(
            ((IMG_SIZE - label_width) // 2, y_pos),
            hist_label,
            font=small_font,
            fill="#6e7681"
        )
        y_pos += 14
        
        draw_histogram(draw, hist_counts, hist_x, y_pos, hist_width, hist_height, hist_date_range)
        y_pos += hist_height + 15
    
    y_pos += 5
    
    # === DIVIDER ===
    draw.line(
        [(PADDING, y_pos), (IMG_SIZE - PADDING, y_pos)],
        fill="#30363d",
        width=2
    )
    y_pos += 15
    
    # === SUMMARY ===
    remaining_height = IMG_SIZE - y_pos - PADDING
    summary_height = int(remaining_height * 0.60)
    
    summary_lines = wrap_text(summary, summary_font, max_text_width)
    line_height = 17
    max_summary_lines = summary_height // line_height
    
    for line in summary_lines[:max_summary_lines]:
        draw.text(
            (PADDING, y_pos),
            line,
            font=summary_font,
            fill=SUMMARY_COLOR
        )
        y_pos += line_height
    
    y_pos += 8
    
    # === DIVIDER ===
    draw.line(
        [(PADDING, y_pos), (IMG_SIZE - PADDING, y_pos)],
        fill="#30363d",
        width=1
    )
    y_pos += 8
    
    # === KEY MOMENTS ===
    header_text = "KEY MOMENTS"
    draw.text(
        (PADDING, y_pos),
        header_text,
        font=load_font(13, bold=True),
        fill=ESSENTIAL_COLOR
    )
    y_pos += 18
    
    essential_line_height = 14
    max_essential_lines = (IMG_SIZE - y_pos - PADDING) // essential_line_height
    lines_used = 0
    
    for tweet in essential_tweets:
        if lines_used >= max_essential_lines - 1:
            break
        annotation = tweet.get("annotation", "")
        full_text = f"• {annotation}"
        wrapped = wrap_text(full_text, essential_font, max_text_width)
        
        for line in wrapped:
            if lines_used >= max_essential_lines:
                break
            draw.text(
                (PADDING, y_pos),
                line,
                font=essential_font,
                fill=ESSENTIAL_COLOR
            )
            y_pos += essential_line_height
            lines_used += 1
    
    # Save with seriation order prefix for sorting (lexicographic)
    seriation_idx = SERIATION_ORDER.get(seed_id, 999)
    output_path = OUTPUT_DIR / f"{seriation_idx:03d}_{seed_id}.png"
    img.save(output_path, "PNG")
    return output_path


def process_strand(json_path: Path) -> tuple[str, bool]:
    """Process a single strand JSON file."""
    try:
        with open(json_path, "r") as f:
            data = json.load(f)
        
        seed_id = str(data["seed_tweet_id"])
        title = data.get("title", "Untitled Strand")
        summary = data.get("summary", "")
        
        # Extract rating info
        rating_data = data.get("rating", {})
        rating = rating_data.get("rating", 5)  # Default to 5 if missing
        essential_tweets = rating_data.get("essential_tweets", [])
        
        # Extract histogram
        histogram = data.get("histogram", {})
        
        # Check if already processed (with seriation order prefix)
        seriation_idx = SERIATION_ORDER.get(seed_id, 999)
        output_path = OUTPUT_DIR / f"{seriation_idx:03d}_{seed_id}.png"
        if output_path.exists():
            return seed_id, True
        
        # Get meta from Groq (includes image prompt)
        meta = get_strand_meta(title, summary)
        
        # Generate thumbnail via Runware
        thumbnail = None
        try:
            thumbnail = generate_thumbnail(seed_id, meta["image_prompt"])
        except Exception as e:
            print(f"[WARN] Thumbnail generation failed for {seed_id}: {e}")
        
        # Create image
        create_strand_image(
            seed_id=seed_id,
            title=title,
            summary=summary,
            emojis=meta["emojis"],
            oneliner=meta["oneliner"],
            rating=rating,
            essential_tweets=essential_tweets,
            histogram=histogram,
            thumbnail=thumbnail
        )
        
        return seed_id, True
        
    except Exception as e:
        print(f"[ERROR] {json_path.name}: {e}")
        return json_path.stem, False


def main():
    """Process all fresh rated strands."""
    json_files = sorted(FRESH_STRANDS_DIR.glob("*.json"))
    print(f"Found {len(json_files)} strand files")
    
    # Check which are already done (extract seed_id from "XXX_seedid.png" format)
    existing_seed_ids = set()
    for p in OUTPUT_DIR.glob("*.png"):
        # Filename format: "042_1234567890.png" -> extract "1234567890"
        parts = p.stem.split("_", 1)
        if len(parts) == 2:
            existing_seed_ids.add(parts[1])
        else:
            existing_seed_ids.add(p.stem)
    
    to_process = [f for f in json_files if f.stem not in existing_seed_ids]
    print(f"Found {len(SERIATION_ORDER)} strands in seriation order")
    print(f"Already done: {len(existing_seed_ids)}, to process: {len(to_process)}")
    
    if not to_process:
        print("All strands already processed!")
        return
    
    # Process with parallelization (5 workers)
    num_workers = 5
    success = 0
    failed = 0
    
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        # Submit all tasks
        future_to_path = {executor.submit(process_strand, path): path for path in to_process}
        
        # Process as they complete with progress bar
        with tqdm(total=len(to_process), desc=f"Generating images ({num_workers} workers)") as pbar:
            for future in as_completed(future_to_path):
                json_path = future_to_path[future]
                try:
                    seed_id, ok = future.result()
                    if ok:
                        success += 1
                    else:
                        failed += 1
                except Exception as e:
                    print(f"\n[ERROR] {json_path.name}: {e}")
                    failed += 1
                pbar.update(1)
    
    print(f"\nDone! Generated {success}/{len(to_process)} images ({failed} failed)")
    print(f"Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()

# %%

