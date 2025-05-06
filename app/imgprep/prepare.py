"""
Image preprocessing module for enhancing scanned invoices before OCR.
"""

import io
import logging
import numpy as np
from typing import Optional, Tuple, List
from PIL import Image, ImageEnhance, ImageFilter

# Try to import OpenCV, fall back to PIL-only mode if not available
try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    logging.getLogger(__name__).warning("OpenCV (cv2) not available, using PIL fallback")

logger = logging.getLogger(__name__)

def prepare_for_ocr(path: str) -> bytes:
    """
    Prepare image for OCR by applying a series of enhancements.
    
    Args:
        path: Path to the source image file
        
    Returns:
        Processed image as bytes in WebP format
    """
    # Use OpenCV if available, otherwise use PIL fallback
    if OPENCV_AVAILABLE:
        return prepare_with_opencv(path)
    else:
        return prepare_with_pil(path)

def prepare_with_pil(path: str) -> bytes:
    """
    PIL-only version of image preprocessing for systems without OpenCV.
    
    Args:
        path: Path to the source image file
        
    Returns:
        Processed image as bytes
    """
    try:
        # Open image with PIL
        image = Image.open(path)
        
        # Step 1: Resize if needed (max dimension 1200px)
        width, height = image.size
        max_dim = 1200
        if max(width, height) > max_dim:
            if width > height:
                new_width = max_dim
                new_height = int(height * (max_dim / width))
            else:
                new_height = max_dim
                new_width = int(width * (max_dim / height))
            image = image.resize((new_width, new_height), Image.LANCZOS)
            logger.info(f"Resized image from {width}x{height} to {new_width}x{new_height}")
        
        # Step 2: Convert to grayscale
        if image.mode != 'L':
            image = image.convert('L')
        
        # Step 3: Enhance contrast
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(1.5)
        
        # Step 4: Apply sharpening filter
        image = image.filter(ImageFilter.SHARPEN)
        
        # Step 5: Apply additional enhancement for text documents
        enhancer = ImageEnhance.Brightness(image)
        image = enhancer.enhance(1.1)  # Slightly increase brightness
        
        # Step 6: Save to bytes (WebP format if supported)
        buffer = io.BytesIO()
        if hasattr(Image, 'WEBP'):
            image.save(buffer, format="WebP", quality=90)
        else:
            image.save(buffer, format="PNG", optimize=True)
        
        logger.info("Image processed with PIL (OpenCV not available)")
        return buffer.getvalue()
        
    except Exception as e:
        logger.error(f"Error preprocessing image with PIL: {str(e)}")
        # Return original image if processing fails
        try:
            with open(path, "rb") as f:
                return f.read()
        except Exception as read_error:
            logger.error(f"Error reading original image: {str(read_error)}")
            raise

def prepare_with_opencv(path: str) -> bytes:
    """
    OpenCV-based image preprocessing for enhanced OCR results.
    
    Args:
        path: Path to the source image file
        
    Returns:
        Processed image as bytes in WebP format
    """
    try:
        # Open and read image
        pil_img = Image.open(path)
        img = np.array(pil_img)
        
        # Convert to RGB if needed
        if len(img.shape) == 2:  # Grayscale
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
        elif img.shape[2] == 4:  # RGBA
            img = cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)
            
        # 3.1 Resize if too large
        img = resize_if_needed(img)
        
        # 3.2 Detect and align document
        aligned_img = detect_and_align_document(img)
        if aligned_img is not None:
            img = aligned_img
            
        # 3.3 Apply CLAHE enhancement and denoise
        enhanced_img = apply_clahe_and_denoise(img)
        
        # 3.4 Apply adaptive threshold and morphological operations
        binary_img = apply_threshold_and_morph(enhanced_img)
        
        # 3.5 Save to WebP
        return save_to_webp(binary_img)
        
    except Exception as e:
        logger.error(f"Error preprocessing image with OpenCV: {str(e)}")
        # Return original image if processing fails
        try:
            with open(path, "rb") as f:
                return f.read()
        except Exception as read_error:
            logger.error(f"Error reading original image: {str(read_error)}")
            raise

# The remaining OpenCV functions are only used when OpenCV is available

def resize_if_needed(img: np.ndarray, max_size: int = 1600, quality: int = 85) -> np.ndarray:
    """
    Resize image if it's larger than max_size in either dimension.
    
    Args:
        img: Input image
        max_size: Maximum dimension size
        quality: JPEG quality for resizing
        
    Returns:
        Resized image or original if no resize needed
    """
    h, w = img.shape[:2]
    
    # Check if resizing is needed
    if max(h, w) <= max_size:
        return img
        
    # Calculate new dimensions
    if h > w:
        new_h = max_size
        new_w = int(w * (max_size / h))
    else:
        new_w = max_size
        new_h = int(h * (max_size / w))
        
    # Resize
    logger.info(f"Resizing image from {w}x{h} to {new_w}x{new_h}")
    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    
    return resized


def detect_and_align_document(img: np.ndarray) -> Optional[np.ndarray]:
    """
    Detect document edges and align/warp to correct perspective.
    
    Args:
        img: Input image
        
    Returns:
        Perspective-corrected image or None if detection fails
    """
    try:
        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        
        # Apply Gaussian blur to reduce noise
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # Apply Canny edge detection
        edges = cv2.Canny(blurred, 75, 200)
        
        # Find contours
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # If no contours found, return None
        if not contours:
            return None
            
        # Find the largest contour by area
        max_contour = max(contours, key=cv2.contourArea)
        
        # Check if contour is large enough (at least 80% of image area)
        img_area = img.shape[0] * img.shape[1]
        contour_area = cv2.contourArea(max_contour)
        if contour_area < 0.1 * img_area:
            logger.info(f"Largest contour area ({contour_area}) too small compared to image area ({img_area})")
            return None
            
        # Approximate the contour to simplify it
        peri = cv2.arcLength(max_contour, True)
        approx = cv2.approxPolyDP(max_contour, 0.02 * peri, True)
        
        # If approximated contour has 4 points, we assume it's a document
        if len(approx) == 4:
            # Order points to get top-left, top-right, bottom-right, bottom-left
            rect = order_points(approx.reshape(4, 2))
            
            # Get destination dimensions
            (tl, tr, br, bl) = rect
            width_a = np.sqrt(((br[0] - bl[0]) ** 2) + ((br[1] - bl[1]) ** 2))
            width_b = np.sqrt(((tr[0] - tl[0]) ** 2) + ((tr[1] - tl[1]) ** 2))
            max_width = max(int(width_a), int(width_b))
            
            height_a = np.sqrt(((tr[0] - br[0]) ** 2) + ((tr[1] - br[1]) ** 2))
            height_b = np.sqrt(((tl[0] - bl[0]) ** 2) + ((tl[1] - bl[1]) ** 2))
            max_height = max(int(height_a), int(height_b))
            
            # Destination points
            dst = np.array([
                [0, 0],
                [max_width - 1, 0],
                [max_width - 1, max_height - 1],
                [0, max_height - 1]
            ], dtype="float32")
            
            # Compute perspective transform matrix
            M = cv2.getPerspectiveTransform(rect, dst)
            
            # Apply perspective transformation
            warped = cv2.warpPerspective(img, M, (max_width, max_height))
            
            logger.info(f"Document aligned from {img.shape[:2]} to {warped.shape[:2]}")
            return warped
            
        return None
    except Exception as e:
        logger.error(f"Error in document alignment: {str(e)}")
        return None


def order_points(pts: np.ndarray) -> np.ndarray:
    """
    Order contour points to get: top-left, top-right, bottom-right, bottom-left.
    
    Args:
        pts: Array of 4 points representing a quadrilateral
        
    Returns:
        Ordered points
    """
    # Initialize ordered array
    rect = np.zeros((4, 2), dtype="float32")
    
    # Top-left: smallest sum of coordinates
    # Bottom-right: largest sum of coordinates
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    
    # Top-right: smallest difference of coordinates
    # Bottom-left: largest difference of coordinates
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    
    return rect


def apply_clahe_and_denoise(img: np.ndarray) -> np.ndarray:
    """
    Apply CLAHE (Contrast Limited Adaptive Histogram Equalization) and denoise.
    
    Args:
        img: Input image
        
    Returns:
        Enhanced image
    """
    # Convert to grayscale if needed
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    else:
        gray = img.copy()
    
    # Calculate image statistics
    mean, std = cv2.meanStdDev(gray)
    mean_val = mean[0][0]
    std_val = std[0][0]
    
    # Determine CLAHE clip limit based on standard deviation
    clip_limit = 2.0
    if std_val < 50:  # Low contrast image
        clip_limit = 3.0
    elif std_val > 80:  # High contrast image
        clip_limit = 1.5
    
    # Create CLAHE object and apply
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8))
    clahe_img = clahe.apply(gray)
    
    # Apply appropriate denoising based on image noise level
    if std_val < 30:  # Low noise
        denoised = cv2.fastNlMeansDenoising(clahe_img, None, h=7, searchWindowSize=21)
    else:  # Normal or high noise
        denoised = cv2.fastNlMeansDenoising(clahe_img, None, h=10, searchWindowSize=21)
    
    return denoised


def apply_threshold_and_morph(img: np.ndarray) -> np.ndarray:
    """
    Apply adaptive thresholding, morphological operations, and sharpening.
    
    Args:
        img: Input grayscale image
        
    Returns:
        Processed binary image
    """
    # Apply adaptive thresholding
    thresh = cv2.adaptiveThreshold(
        img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )
    
    # Create kernels for morphological operations
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    
    # Apply morphological operations to clean up the image
    # Opening (erosion followed by dilation) to remove small noise
    cleaned = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
    
    # Apply sharpening
    blurred = cv2.GaussianBlur(cleaned, (0, 0), 3)
    sharpened = cv2.addWeighted(cleaned, 1.5, blurred, -0.5, 0)
    
    return sharpened


def save_to_webp(img: np.ndarray, quality: int = 90, max_size: int = 200) -> bytes:
    """
    Convert OpenCV image to WebP format with compression.
    
    Args:
        img: Input image
        quality: WebP quality (0-100)
        max_size: Maximum size in kilobytes
        
    Returns:
        Image as bytes in WebP format
    """
    # Convert to RGB if grayscale
    if len(img.shape) == 2:
        rgb_img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
    else:
        rgb_img = img
    
    # Convert to PIL Image
    pil_img = Image.fromarray(rgb_img)
    
    # Save to bytes with WebP format
    buffer = io.BytesIO()
    pil_img.save(buffer, format="WebP", quality=quality)
    
    # Get bytes
    img_bytes = buffer.getvalue()
    
    # Check size and reduce quality if needed
    size_kb = len(img_bytes) / 1024
    current_quality = quality
    
    # Reduce quality until file size is below max_size
    while size_kb > max_size and current_quality > 50:
        current_quality -= 10
        buffer = io.BytesIO()
        pil_img.save(buffer, format="WebP", quality=current_quality)
        img_bytes = buffer.getvalue()
        size_kb = len(img_bytes) / 1024
        logger.info(f"Reduced WebP quality to {current_quality}, size: {size_kb:.1f} KB")
    
    return img_bytes