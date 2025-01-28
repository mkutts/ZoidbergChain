from PIL import Image
import imagehash
import pytesseract
import re
import os

def hash_image(image_path):
        """Generate a perceptual hash for an image."""
        try:
            print(f"Debug: Hashing image at path: {image_path}")

            # Check if the file exists
            if not os.path.isfile(image_path):
                print(f"Error: File does not exist at {image_path}")
                raise ValueError("Invalid image path provided for the meme.")

            img = Image.open(image_path)
            return str(imagehash.average_hash(img))  # Convert hash to string for storage and comparison
        except Exception as e:
            print(f"Error in hash_image: {e}")
            raise ValueError("Invalid image path provided for the meme.")



def extract_text(image_path):
        """Extract text from an image using pytesseract and clean it."""
        try:
            img = Image.open(image_path)

            # Use Tesseract to extract text
            raw_text = pytesseract.image_to_string(img, config="--psm 11")
            print(f"Raw Extracted Text: {raw_text}")  # Debug output

            # Clean the text: remove newlines, extra spaces, and unusual characters
            cleaned_text = re.sub(r'\s+', ' ', raw_text)  # Replace newlines and extra spaces with a single space
            cleaned_text = re.sub(r'[^\w\s]', '', cleaned_text)  # Remove non-alphanumeric characters except spaces
            cleaned_text = cleaned_text.strip()  # Remove leading/trailing whitespace

            print(f"Cleaned Text: {cleaned_text}")  # Debug output
            return cleaned_text
        except Exception as e:
            print(f"Error extracting text: {e}")
            return None
