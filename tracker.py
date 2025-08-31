import time
import re
import mss
import pygetwindow as gw
from PIL import Image
import pytesseract
import tkinter as tk
import threading

# Tell pytesseract where Tesseract is installed
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# --- Notification class ---
class ToastNotifier:
    def __init__(self, root):
        self.root = root
        self.temp_toasts = []

    def draw_rounded_rect(self, canvas, x1, y1, x2, y2, radius=15, **kwargs):
        points = [
            x1+radius, y1, x2-radius, y1,
            x2, y1, x2, y1+radius,
            x2, y2-radius, x2, y2,
            x2-radius, y2, x1+radius, y2,
            x1, y2, x1, y2-radius,
            x1, y1+radius, x1, y1
        ]
        return canvas.create_polygon(points, smooth=True, **kwargs)

    def animate_slide_in(self, toast, width, height):
        screen_w = toast.winfo_screenwidth()
        x_start = screen_w + 50
        x_end = screen_w - width - 20
        y = 20
        for i in range(20):
            t = 1 - (1 - i/19)**3
            x = int(x_start + t * (x_end - x_start))
            toast.geometry(f"{width}x{height}+{x}+{y}")
            toast.update()
            time.sleep(0.02)

    def show_temp_notification(self, message, duration=2):
        def popup():
            toast = tk.Toplevel(self.root)
            toast.overrideredirect(True)
            toast.attributes("-topmost", True)
            self.temp_toasts.append(toast)

            width, height = 280, 70
            canvas = tk.Canvas(toast, width=width, height=height, bg="#1e1e1e", highlightthickness=0)
            canvas.pack(fill="both", expand=True)
            self.draw_rounded_rect(canvas, 2, 2, width-2, height-2, radius=12, fill="#2d2d2d", outline="#FF9800", width=2)
            canvas.create_text(width/2, height/2, text=message, fill="#ffffff", font=("Segoe UI", 10))

            x = toast.winfo_screenwidth() - width - 20
            y = 100
            toast.geometry(f"{width}x{height}+{x}+{y}")
            threading.Thread(target=self.animate_slide_in, args=(toast, width, height), daemon=True).start()

            def cleanup():
                try:
                    toast.destroy()
                    self.temp_toasts.remove(toast)
                except: pass

            toast.after(int(duration*1000), cleanup)
        threading.Thread(target=popup, daemon=True).start()

# --- Auto-Sync using scaled window-relative OCR ---
# Reference dimensions and position from your fullscreen measurement
FULLSCREEN_WINDOW_WIDTH = 1936
FULLSCREEN_WINDOW_HEIGHT = 1048
FULLSCREEN_WINDOW_LEFT = 1912
FULLSCREEN_WINDOW_TOP = -8

FULL_LEFT = 2881
FULL_TOP = 978
FULL_RIGHT = 2977
FULL_BOTTOM = 1002
FULL_WIDTH = FULL_RIGHT - FULL_LEFT
FULL_HEIGHT = FULL_BOTTOM - FULL_TOP

def auto_sync_once():
    windows = [w for w in gw.getAllWindows() if "Wplace" in w.title]
    if not windows:
        print("wplace.live not open, skipping auto-sync")
        return None, None, None

    w = windows[0]


    scale_x = w.width / FULLSCREEN_WINDOW_WIDTH
    scale_y = w.height / FULLSCREEN_WINDOW_HEIGHT


    relative_left_in_fullscreen = FULL_LEFT - FULLSCREEN_WINDOW_LEFT
    relative_top_in_fullscreen = FULL_TOP - FULLSCREEN_WINDOW_TOP

    scaled_left = relative_left_in_fullscreen * scale_x
    scaled_top = relative_top_in_fullscreen * scale_y
    scaled_width = FULL_WIDTH * scale_x
    scaled_height = FULL_HEIGHT * scale_y

    region = {
        "left": int(w.left + scaled_left),
        "top": int(w.top + scaled_top),
        "width": int(scaled_width),
        "height": int(scaled_height)
    }

    print(f"Window: {w.width}x{w.height} at ({w.left}, {w.top})")
    print(f"Scale factors: {scale_x:.3f}, {scale_y:.3f}")
    print(f"Relative coords in fullscreen: ({relative_left_in_fullscreen}, {relative_top_in_fullscreen})")
    print(f"Scaled coords: ({scaled_left:.1f}, {scaled_top:.1f})")
    print(f"OCR region: {region}")

    try:
        with mss.mss() as sct:
            img = sct.grab(region)
            pil_img = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")

            # Optional: Save debug image to see what's being captured
            # pil_img.save("debug_ocr.png")

            pil_img = pil_img.convert('L')


            custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789/:() '
            text = pytesseract.image_to_string(pil_img, config=custom_config)

            print(f"OCR text: '{text.strip()}'")
    except Exception as e:
        print(f"OCR error: {e}")
        return None, None, None

    patterns = [
        r"(\d+)\s*/\s*(\d+)\s*\((\d+):(\d+)\)",  
        r"(\d+)/(\d+)\s*\((\d+):(\d+)\)",        
        r"(\d+)\s*/\s*(\d+)\s*\((\d+):(\d+)",    
        r"(\d+)/(\d+)\((\d+):(\d+)\)",           
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            current = int(match.group(1))
            max_val = int(match.group(2))
            minutes = int(match.group(3))
            seconds = int(match.group(4))
            regen_timer = minutes*60 + seconds
            print(f"Matched pattern: {pattern}")
            print(f"Parsed: {current}/{max_val}, timer: {minutes}:{seconds:02d} ({regen_timer}s)")
            return current, max_val, regen_timer

    print("No pattern matched")
    return None, None, None

def precise_auto_sync(duration=3):
    print("Starting precise auto-sync...")
    start_time = time.time()
    best_current = None
    best_max = None
    best_timer = None
    attempts = 0

    while time.time() - start_time < duration:
        attempts += 1
        print(f"Auto-sync attempt {attempts}")
        current, max_charges, regen_timer = auto_sync_once()
        if current is not None:
            if best_timer is None or regen_timer < best_timer:
                best_current = current
                best_max = max_charges
                best_timer = regen_timer
        time.sleep(0.2)

    if best_current is not None:
        print(f"Precise auto-sync successful: {best_current}/{best_max}, next in {best_timer}s")
        return best_current, best_max, best_timer
    else:
        print(f"Auto-sync failed after {attempts} attempts")
        return None, None, None

# --- Main Tracker ---
def run_tracker(root):
    notifier = ToastNotifier(root)
    current, max_charges, regen_timer = precise_auto_sync()

    if current is None:
        print("Auto-sync failed, falling back to manual input")
        max_charges = int(input("Enter max charges: "))
        current = int(input("Enter current charges: "))
        regen_timer = 30

    notified_milestones = set()
    print(f"Starting tracker with {current}/{max_charges} charges, waiting {regen_timer}s")
    time.sleep(regen_timer if regen_timer > 0 else 30)

    while True:
        if current < max_charges:
            current += 1
            percent = int((current / max_charges) * 100)
            milestone = (percent // 10) * 10
            if milestone % 10 == 0 and milestone not in notified_milestones:
                notifier.show_temp_notification(f"Charges {milestone}% full ({current}/{max_charges})")
                notified_milestones.add(milestone)
            print(f"Current charges: {current}/{max_charges} ({percent}%)")
            time.sleep(30)
        else:
            if 100 not in notified_milestones:
                notifier.show_temp_notification(f"Charges 100% full ({current}/{max_charges})")
                notified_milestones.add(100)
            print(f"Charges full: {current}/{max_charges}")
            time.sleep(10)

if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    threading.Thread(target=run_tracker, args=(root,), daemon=True).start()
    root.mainloop()
