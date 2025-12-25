import base64
import os
import sys

# Add current directory to path to allow imports from app
sys.path.append(os.getcwd())

try:
    from app.ui.resources import LOGO_BASE64
    from PIL import Image
    import io

    if LOGO_BASE64:
        # Decode base64 to bytes
        img_data = base64.b64decode(LOGO_BASE64)
        
        # Load as PIL Image
        img = Image.open(io.BytesIO(img_data))
        
        # Save as ICO
        # We ensure it's resized to standard icon sizes if needed, 
        # but modern Windows handles large PNG-in-ICO well.
        icon_path = 'images/app_icon.ico'
        img.save(icon_path, format='ICO', sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (255, 255)])
        
        print(f"Successfully created {icon_path}")
    else:
        print("LOGO_BASE64 is empty")
except ImportError as e:
    print(f"Import Error: {e}")
except Exception as e:
    print(f"Error: {e}")
