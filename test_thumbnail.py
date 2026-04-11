from PIL import Image
from cocli.core.video.thumbnailer import overlay_text

# Create a dummy image
img = Image.new("RGB", (1280, 720), color="black")
text = "Local-First<br />Task Agent"
processed = overlay_text(img, text)
processed.save("test_thumbnail_br.png")
print("Thumbnail saved as test_thumbnail_br.png")
