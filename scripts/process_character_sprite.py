import sys
import numpy as np
from PIL import Image

def process_sprite(in_path, out_path, target_h=48):
    im = Image.open(in_path).convert('RGBA')
    arr = np.array(im)
    
    # Chroma key: bright magenta is high R, low G, high B
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    # Distance to magenta [255, 0, 255]
    diff = np.sqrt((r.astype(float) - 255)**2 + g.astype(float)**2 + (b.astype(float) - 255)**2)
    is_magenta = diff < 120
    
    arr[is_magenta, 3] = 0
    
    # Crop to non-transparent bounding box
    alpha = arr[:, :, 3]
    ys, xs = np.where(alpha > 0)
    if len(ys) == 0 or len(xs) == 0:
        print(f"Warning: No non-transparent pixels found in {in_path}")
        return
    ymin, ymax = np.min(ys), np.max(ys)
    xmin, xmax = np.min(xs), np.max(xs)
    
    cropped = arr[ymin:ymax+1, xmin:xmax+1]
    cr_im = Image.fromarray(cropped, 'RGBA')
    
    # Scale to target_h preserving aspect ratio
    aspect = cr_im.width / cr_im.height
    new_w = max(1, round(target_h * aspect))
    resized = cr_im.resize((new_w, target_h), Image.Resampling.NEAREST)
    
    # Place on 32-wide canvas centered horizontally, bottom-aligned
    canvas_w = max(32, new_w)
    final_canvas = Image.new('RGBA', (canvas_w, target_h), (0, 0, 0, 0))
    x_off = (canvas_w - new_w) // 2
    final_canvas.paste(resized, (x_off, 0), resized)
    
    final_canvas.save(out_path)
    print(f"Processed {out_path}: {final_canvas.size}")

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python3 process_character_sprite.py <in_path> <out_path> [target_h]")
        sys.exit(1)
    in_p = sys.argv[1]
    out_p = sys.argv[2]
    th = int(sys.argv[3]) if len(sys.argv) > 3 else 48
    process_sprite(in_p, out_p, th)
