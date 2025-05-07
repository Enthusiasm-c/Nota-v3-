"""
Image preprocessing module for enhancing scanned invoices before OCR.
Optimized for performance and OCR accuracy with adaptive processing.
"""

import io
import logging
import math
import numpy as np
from typing import Optional, Tuple, List
from PIL import Image, ImageEnhance, ImageFilter
from pathlib import Path

# Try to import OpenCV, fall back to PIL-only mode if not available
try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    logging.getLogger(__name__).warning("OpenCV (cv2) not available, using PIL fallback")

logger = logging.getLogger(__name__)

def prepare_without_preprocessing(path: str) -> bytes:
    """
    Send original image without any preprocessing.
    Simply reads and converts to WebP format with high quality.
    
    Args:
        path: Path to the source image file
        
    Returns:
        Original image as bytes in WebP/JPEG format
    """
    try:
        # Open image with PIL
        image = Image.open(path)
        
        # Save to bytes (WebP format if supported, or JPEG)
        buffer = io.BytesIO()
        if hasattr(Image, 'WEBP'):
            image.save(buffer, format="WebP", quality=98)
        else:
            image.save(buffer, format="JPEG", quality=98)
        
        logger.info("Image sent without preprocessing (original)")
        return buffer.getvalue()
    except Exception as e:
        logger.error(f"Error reading original image: {str(e)}")
        try:
            with open(path, "rb") as f:
                return f.read()
        except Exception as read_error:
            logger.error(f"Error reading original image file: {str(read_error)}")
            raise

def prepare_for_ocr(path: str, use_preprocessing: bool = True) -> bytes:
    """
    Prepare image for OCR by applying minimal enhancements or no preprocessing.
    
    Args:
        path: Path to the source image file
        use_preprocessing: Flag to enable/disable preprocessing
        
    Returns:
        Processed image as bytes in WebP format
    """
    # Skip preprocessing if disabled
    if not use_preprocessing:
        return prepare_without_preprocessing(path)
        
    # Use OpenCV if available, otherwise use PIL fallback
    if OPENCV_AVAILABLE:
        return prepare_with_opencv(path)
    else:
        return prepare_with_pil(path)

def prepare_with_pil(path: str) -> bytes:
    """
    PIL-only version of minimal image preprocessing for systems without OpenCV.
    
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
        max_dim = 2048
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
        
        # Step 3: Mild contrast enhancement (reduced from 1.5 to 1.2)
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(1.2)
        
        # Step 4: Save to bytes (WebP format if supported)
        buffer = io.BytesIO()
        if hasattr(Image, 'WEBP'):
            image.save(buffer, format="WebP", quality=95)  # Increased quality
        else:
            image.save(buffer, format="PNG", optimize=True)
        
        logger.info("Image processed with minimal PIL enhancements")
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
    OpenCV-based minimal image preprocessing for enhanced OCR results.
    Optimized for speed and OCR performance.
    
    Args:
        path: Path to the source image file
        
    Returns:
        Processed image as bytes
    """
    try:
        # Track processing time for performance monitoring
        import time
        t0 = time.time()
        
        # Open and read image
        pil_img = Image.open(path)
        img = np.array(pil_img)
        
        # Convert to RGB if needed
        if len(img.shape) == 2:  # Grayscale
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
        elif img.shape[2] == 4:  # RGBA
            img = cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)
        
        # Get original dimensions for logging
        orig_h, orig_w = img.shape[:2]
        img_size = f"{orig_w}x{orig_h}"
            
        # 1. Resize if too large - increased max_size to 2400 for better quality
        img = resize_if_needed(img, max_size=2400)
        
        # Check if image is dark and likely needs brightness enhancement
        mean_brightness = cv2.mean(img)[0]
        
        # 2. Skip alignment for most images unless very skewed (10 degrees+)
        # This significantly improves processing speed with minimal quality impact
        if mean_brightness < 50:  # Only try to align dark images which may be harder to read
            aligned_img = detect_and_align_document(img, skew_threshold=10.0)
            if aligned_img is not None:
                img = aligned_img
        
        # 3. Apply optimized normalization - different paths for different image types
        if mean_brightness < 70:  # Dark image
            logger.info(f"Applying enhanced brightness for dark image (brightness: {mean_brightness:.1f})")
            # For darker images, apply CLAHE to improve contrast without adding noise
            enhanced_img = apply_enhanced_normalization(img)
        else:
            # For normal brightness images, apply minimal processing
            enhanced_img = apply_mild_normalization(img)
            
        # 4. Save to WebP with high quality but enforce maximum file size
        result_bytes = save_to_webp(enhanced_img, quality=92, max_size=800)
        
        # Log processing time for performance monitoring
        elapsed = time.time() - t0
        logger.info(f"OpenCV preprocessing: {img_size} → {enhanced_img.shape[1]}x{enhanced_img.shape[0]} in {elapsed:.3f}s")
        
        return result_bytes
        
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

def resize_if_needed(img: np.ndarray, max_size: int = 2048) -> np.ndarray:
    """
    Resize image if it's larger than max_size in either dimension.
    
    Args:
        img: Input image
        max_size: Maximum dimension size
        
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


def detect_and_align_document(img: np.ndarray, skew_threshold: float = 5.0) -> Optional[np.ndarray]:
    """
    Detect document edges and align/warp to correct perspective,
    but only if document is clearly skewed beyond the threshold.
    
    Args:
        img: Input image
        skew_threshold: Minimum angle (in degrees) to consider skewed
        
    Returns:
        Perspective-corrected image or None if detection fails or skew is below threshold
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
        
        # Check if contour is large enough (at least 30% of image area)
        img_area = img.shape[0] * img.shape[1]
        contour_area = cv2.contourArea(max_contour)
        if contour_area < 0.3 * img_area:
            logger.info(f"Largest contour area ({contour_area}) too small compared to image area ({img_area})")
            return None
            
        # Approximate the contour to simplify it
        peri = cv2.arcLength(max_contour, True)
        approx = cv2.approxPolyDP(max_contour, 0.02 * peri, True)
        
        # If approximated contour has 4 points, we assume it's a document
        if len(approx) == 4:
            # Order points to get top-left, top-right, bottom-right, bottom-left
            rect = order_points(approx.reshape(4, 2))
            
            # Check for skew angle
            (tl, tr, br, bl) = rect
            
            # Calculate angles of edges
            def angle_between_points(p1, p2):
                return np.degrees(np.arctan2(p2[1] - p1[1], p2[0] - p1[0]))
            
            # Get angles of horizontal edges
            top_angle = angle_between_points(tl, tr)
            bottom_angle = angle_between_points(bl, br)
            
            # Compute skew as deviation from horizontal
            skew = max(abs(top_angle), abs(bottom_angle))
            
            # Only align if skew is significant
            if skew < skew_threshold:
                logger.info(f"Document skew ({skew:.2f}°) below threshold ({skew_threshold}°), skipping alignment")
                return None
            
            # Get destination dimensions
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
            
            logger.info(f"Document aligned from {img.shape[:2]} to {warped.shape[:2]}, corrected skew: {skew:.2f}°")
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


def apply_mild_normalization(img: np.ndarray) -> np.ndarray:
    """
    Apply gentle contrast normalization without excessive processing.
    Optimized version for good quality images.
    
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
    
    # Apply very mild denoising only for noisy images
    # Calculate noise level
    noise_level = np.std(gray)
    if noise_level > 35:  # Only apply denoising if image is noisy
        # Use faster non-local means denoising with smaller search window
        denoised = cv2.fastNlMeansDenoising(gray, None, h=7, searchWindowSize=15)
        logger.info(f"Applied mild denoising (noise level: {noise_level:.1f})")
        return denoised
    
    # For clean images, just return grayscale
    return gray


def apply_enhanced_normalization(img: np.ndarray) -> np.ndarray:
    """
    Apply enhanced contrast normalization for dark or low-contrast images.
    Uses CLAHE (Contrast Limited Adaptive Histogram Equalization) for better results.
    
    Args:
        img: Input image
        
    Returns:
        Enhanced image with improved contrast
    """
    # Convert to grayscale if needed
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    else:
        gray = img.copy()
    
    # Check mean brightness and contrast
    mean_brightness = cv2.mean(gray)[0]
    contrast = np.std(gray)
    
    logger.info(f"Image stats: brightness={mean_brightness:.1f}, contrast={contrast:.1f}")
    
    # Create a CLAHE object with controlled clip limit
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    
    # Apply CLAHE for contrast enhancement
    enhanced = clahe.apply(gray)
    
    # Apply gentle bilateral filter to preserve edges while reducing noise
    # This is more OCR-friendly than regular Gaussian blur
    if contrast < 40:  # Only apply if contrast is low
        filtered = cv2.bilateralFilter(enhanced, 9, 75, 75)
        logger.info("Applied bilateral filtering for low contrast image")
        return filtered
    
    return enhanced


def save_to_webp(img: np.ndarray, quality: int = 95, max_size: int = 500) -> bytes:
    """
    Convert OpenCV image to WebP format with high quality compression.
    Optimized for OCR performance with adaptive quality settings.
    
    Args:
        img: Input image
        quality: WebP quality (0-100)
        max_size: Maximum size in kilobytes
        
    Returns:
        Image as bytes in WebP format
    """
    # Convert to RGB if grayscale (needed for WebP)
    if len(img.shape) == 2:
        rgb_img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
    else:
        rgb_img = img
    
    # Convert to PIL Image
    pil_img = Image.fromarray(rgb_img)
    
    # Calculate image complexity - helps determine if we can compress more
    # Simple heuristic: standard deviation of pixel values as percentage of max range
    complexity = np.std(img) / 255.0 * 100
    
    # Adjust initial quality based on image complexity
    # More complex images (high detail) need higher quality settings
    adjusted_quality = quality
    if complexity < 10:  # Very simple/flat image
        adjusted_quality = max(85, quality - 10)
        logger.info(f"Low complexity image ({complexity:.1f}%), reducing initial quality to {adjusted_quality}")
    elif complexity > 25:  # Very detailed image
        adjusted_quality = min(98, quality + 3)
        logger.info(f"High complexity image ({complexity:.1f}%), increasing initial quality to {adjusted_quality}")
    
    # Save to bytes with WebP format
    buffer = io.BytesIO()
    pil_img.save(buffer, format="WebP", quality=adjusted_quality)
    
    # Get bytes
    img_bytes = buffer.getvalue()
    
    # Check size and reduce quality if needed
    size_kb = len(img_bytes) / 1024
    current_quality = adjusted_quality
    
    # Use more aggressive compression strategies for very large images
    min_quality = 78  # Don't go below this quality
    
    # Reduce quality until file size is below max_size
    while size_kb > max_size and current_quality > min_quality:
        # Decrease quality more aggressively for larger sizes
        step = 5 if size_kb < 2 * max_size else 8
        current_quality -= step
        current_quality = max(current_quality, min_quality)  # Ensure we don't go below minimum
        
        buffer = io.BytesIO()
        pil_img.save(buffer, format="WebP", quality=current_quality)
        img_bytes = buffer.getvalue()
        size_kb = len(img_bytes) / 1024
        logger.info(f"Reduced WebP quality to {current_quality}, size: {size_kb:.1f} KB")
    
    # If we still exceed max size at minimum quality, need to resize
    if size_kb > max_size and current_quality <= min_quality:
        # Calculate new dimensions to reach target size
        target_ratio = math.sqrt(max_size / size_kb) * 0.9  # 10% buffer
        new_width = int(pil_img.width * target_ratio)
        new_height = int(pil_img.height * target_ratio)
        
        # Only resize if the reduction is significant (>10%)
        if target_ratio < 0.9:
            resized_img = pil_img.resize((new_width, new_height), Image.LANCZOS)
            buffer = io.BytesIO()
            resized_img.save(buffer, format="WebP", quality=min_quality + 5)  # Slightly higher quality for resized
            img_bytes = buffer.getvalue()
            size_kb = len(img_bytes) / 1024
            logger.info(f"Resized to {new_width}x{new_height} to reach target size, final: {size_kb:.1f} KB")
    
    return img_bytes