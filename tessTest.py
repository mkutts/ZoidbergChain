import pytesseract
from PIL import Image, ImageFilter, ImageEnhance

def preprocess_image(image_path):
    """Preprocess the image to improve OCR accuracy."""
    img = Image.open(image_path)

    # Convert to grayscale
    img = img.convert("L")

    # Enhance contrast
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2)

    # Apply a slight blur to reduce noise
    img = img.filter(ImageFilter.MedianFilter(size=3))

    # Save the preprocessed image for debugging
    img.save("preprocessed_image.jpg")
    return img

def extract_text(image_path):
    """Extract text from an image using pytesseract."""
    try:
        # Preprocess the image
        img = preprocess_image(image_path)

        # Extract text
        text = pytesseract.image_to_string(img, config="--psm 11")
        return text.strip()
    except Exception as e:
        print(f"Error during OCR: {e}")
        return None

# Run the test
if __name__ == "__main__":
    image_path = "button.jfif"
    print("Extracting text from the image...")
    extracted_text = extract_text(image_path)
    print(f"Extracted Text:\n{extracted_text if extracted_text else 'No text found'}")
