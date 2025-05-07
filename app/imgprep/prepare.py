"""
Image preprocessing module for enhancing scanned invoices before OCR.
Optimized for processing Indonesian HoReCa invoices with specific characteristics:
- Colored paper (pink, violet, blue, white)
- Dot-matrix printing and handwritten text
- Mixed printed/handwritten content
- Perspective distortion from phone camera
- Matrix printer artifacts and creases
"""

import io
import logging
import math
import numpy as np
import cv2
from typing import Optional, Tuple, List, Dict, Any
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

# Constants for Indonesian invoice processing
INVOICE_TYPES = {
    "MATRIX_PRINT": 1,  # Dot-matrix printer (thin, dotted characters)
    "HANDWRITTEN": 2,   # Mostly handwritten invoice
    "MIXED": 3          # Mixed printed headers with handwritten content
}

# Color backgrounds commonly found in Indonesian invoices
COLORED_PAPERS = {
    "WHITE": 1,
    "PINK": 2, 
    "VIOLET": 3,
    "BLUE": 4
}

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

def detect_invoice_properties(img: np.ndarray) -> Dict[str, Any]:
    """
    Analyze invoice image to detect key properties like paper color,
    presence of dot-matrix printing, dominant text type, etc.
    
    Args:
        img: Input image in RGB format
        
    Returns:
        Dictionary with detected properties
    """
    h, w = img.shape[:2]
    props = {
        "paper_color": COLORED_PAPERS["WHITE"],
        "invoice_type": INVOICE_TYPES["MIXED"],
        "is_perspective": False,
        "skew_angle": 0.0,
        "mean_brightness": 0,
        "has_dot_matrix": False,
        "has_handwriting": False
    }
    
    # Convert to HSV for better color analysis
    hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
    h_channel, s_channel, v_channel = cv2.split(hsv)
    
    # Get brightness stats
    mean_brightness = np.mean(v_channel)
    props["mean_brightness"] = mean_brightness
    
    # Detect paper color based on hue and saturation in top 20% of image
    # This is where invoice headers are typically located
    header_region = hsv[0:int(h*0.2), :, :]
    h_header = header_region[:,:,0]
    s_header = header_region[:,:,1]
    
    # Average hue and saturation values for header region
    avg_hue = np.mean(h_header)
    avg_sat = np.mean(s_header)
    
    # Detect paper color based on hue/saturation ranges
    if avg_sat < 30:  # Low saturation indicates white/gray paper
        props["paper_color"] = COLORED_PAPERS["WHITE"]
    elif 140 <= avg_hue <= 170 and avg_sat > 30:  # Pink/light red range
        props["paper_color"] = COLORED_PAPERS["PINK"]
    elif 120 <= avg_hue <= 140 and avg_sat > 30:  # Purple/violet range
        props["paper_color"] = COLORED_PAPERS["VIOLET"]
    elif 90 <= avg_hue <= 120 and avg_sat > 30:  # Blue range
        props["paper_color"] = COLORED_PAPERS["BLUE"]
    
    # Detect dot-matrix printing using edge detection and pattern analysis
    # Convert to grayscale for edge detection
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 100, 200)
    
    # Calculate stats on edges to detect dot-matrix patterns
    # Dot-matrix has characteristic small, regular dots
    _, contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    small_dots_count = 0
    for contour in contours:
        area = cv2.contourArea(contour)
        if 2 < area < 10:  # Small dots typical of dot-matrix printing
            small_dots_count += 1
    
    # If there are many small dots in a regular pattern, likely dot-matrix
    props["has_dot_matrix"] = small_dots_count > (w * h) * 0.0005
    
    # Detect handwriting using stroke width variation
    # Apply morphological operations to highlight handwritten strokes
    kernel = np.ones((3, 3), np.uint8)
    dilated = cv2.dilate(edges, kernel, iterations=1)
    stroke_width = cv2.subtract(dilated, edges)
    
    # Calculate stroke width variance
    # Handwritten text has higher stroke width variance than printed text
    nonzero_stroke = stroke_width[stroke_width > 0]
    if len(nonzero_stroke) > 0:
        stroke_std = np.std(nonzero_stroke)
        props["has_handwriting"] = stroke_std > 10.0
    
    # Determine predominant invoice type
    if props["has_dot_matrix"] and not props["has_handwriting"]:
        props["invoice_type"] = INVOICE_TYPES["MATRIX_PRINT"]
    elif props["has_handwriting"] and not props["has_dot_matrix"]:
        props["invoice_type"] = INVOICE_TYPES["HANDWRITTEN"]
    else:
        props["invoice_type"] = INVOICE_TYPES["MIXED"]
    
    # Check perspective distortion by analyzing horizontal and vertical lines
    # Common in photos taken by phone
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, 100, minLineLength=w*0.3, maxLineGap=10)
    if lines is not None and len(lines) > 0:
        angles = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            if abs(x2 - x1) > abs(y2 - y1):  # Horizontal line
                angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
                angles.append(angle)
        
        if angles:
            angle_std = np.std(angles)
            props["is_perspective"] = angle_std > 2.0
            props["skew_angle"] = np.mean(angles)
    
    return props

def prepare_with_opencv(path: str) -> bytes:
    """
    OpenCV-based preprocessing optimized for Indonesian invoices.
    Applies specific enhancements for colored paper, dot-matrix printing,
    and mixed handwritten/printed content.
    
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
            
        # 1. Resize if too large but preserve quality for OCR
        img = resize_if_needed(img, max_size=2800)  # Increased to maintain quality
        
        # 2. Detect invoice properties to customize preprocessing
        props = detect_invoice_properties(img)
        
        # Log detected properties
        logger.info(f"Detected invoice properties: " + 
                    f"paper_color={list(COLORED_PAPERS.keys())[list(COLORED_PAPERS.values()).index(props['paper_color'])]} " +
                    f"type={list(INVOICE_TYPES.keys())[list(INVOICE_TYPES.values()).index(props['invoice_type'])]} " +
                    f"perspective={props['is_perspective']} " +
                    f"brightness={props['mean_brightness']:.1f}")
        
        # 3. Apply perspective correction if needed (more sensitive threshold for invoices)
        # These documents often have perforation marks that help with alignment
        if props['is_perspective'] or abs(props['skew_angle']) > 5.0:
            aligned_img = detect_and_align_document(img, skew_threshold=5.0)
            if aligned_img is not None:
                img = aligned_img
                logger.info(f"Applied perspective correction, angle={props['skew_angle']:.1f}°")
        
        # 4. Apply specialized preprocessing based on invoice type
        if props['invoice_type'] == INVOICE_TYPES["MATRIX_PRINT"]:
            # Specialized processing for dot-matrix prints to connect broken characters
            enhanced_img = process_dot_matrix(img, props)
            logger.info("Applied dot-matrix optimization")
        elif props['invoice_type'] == INVOICE_TYPES["HANDWRITTEN"]:
            # Optimize for handwritten text (preserve stroke detail)
            enhanced_img = process_handwritten(img, props)
            logger.info("Applied handwriting optimization")
        else:  # MIXED type
            # Process for mixed content (headers printed, content handwritten)
            enhanced_img = process_mixed_content(img, props)
            logger.info("Applied mixed-content optimization")
        
        # 5. Save to WebP with higher quality for better OCR
        # Since accuracy is more important than size
        result_bytes = save_to_webp(enhanced_img, quality=95, max_size=1200)  # Higher quality, larger size limit
        
        # Log processing time for performance monitoring
        elapsed = time.time() - t0
        logger.info(f"Indonesian invoice preprocessing: {img_size} → {enhanced_img.shape[1]}x{enhanced_img.shape[0]} in {elapsed:.3f}s")
        
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
    Enhanced document edge detection and alignment optimized for Indonesian invoices.
    Detects perforation marks from fan-fold pages and handles colored backgrounds.
    
    Args:
        img: Input image
        skew_threshold: Minimum angle (in degrees) to consider skewed
        
    Returns:
        Perspective-corrected image or None if detection fails or skew is below threshold
    """
    try:
        # Convert to HSV for better edge detection on colored papers
        if len(img.shape) == 3:
            hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
            # Use value channel which works better for edge detection on colored paper
            gray = hsv[:,:,2]
        else:
            gray = img.copy()
        
        # Check for dot-matrix perforation marks in fan-fold invoices
        h, w = gray.shape
        has_perforation = False
        
        # Look for perforation patterns at the edges
        left_edge = gray[:, 0:20]
        right_edge = gray[:, w-20:w]
        
        # Calculate vertical variance of edge pixel values
        # High variance with regular spacing indicates perforation
        left_var = np.var(np.mean(left_edge, axis=1))
        right_var = np.var(np.mean(right_edge, axis=1))
        
        # High variance with regular pattern indicates perforation
        has_perforation = left_var > 500 or right_var > 500
        
        # Apply more aggressive preprocessing for invoices with perforation
        # as they usually have well-defined edges
        if has_perforation:
            # Use Canny with tighter thresholds for perforation marks
            edges = cv2.Canny(gray, 50, 150)
            logger.info("Fan-fold perforation marks detected, using optimized edge detection")
        else:
            # Apply Gaussian blur to reduce noise
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            # Use standard Canny edge detection
            edges = cv2.Canny(blurred, 75, 200)
        
        # Dilate edges to ensure connectivity
        kernel = np.ones((3, 3), np.uint8)
        dilated_edges = cv2.dilate(edges, kernel, iterations=1)
        
        # Find contours - use external only for document boundary
        contours, _ = cv2.findContours(dilated_edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # If no contours found, try a different approach with thresholding
        if not contours:
            # Try adaptive thresholding instead
            thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                          cv2.THRESH_BINARY_INV, 11, 2)
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                return None
        
        # Find the largest contour by area
        max_contour = max(contours, key=cv2.contourArea)
        
        # Check if contour is large enough (relaxed to 25% for photos with fingers holding invoice)
        img_area = img.shape[0] * img.shape[1]
        contour_area = cv2.contourArea(max_contour)
        if contour_area < 0.25 * img_area:
            logger.info(f"Largest contour area ({contour_area}) too small compared to image area ({img_area})")
            return None
        
        # Approximate the contour to find corners
        peri = cv2.arcLength(max_contour, True)
        # Lower epsilon for more points (Indonesian invoices often have rounded corners)
        approx = cv2.approxPolyDP(max_contour, 0.01 * peri, True)
        
        # Handle different contour shapes
        if len(approx) == 4:
            # Perfect quadrilateral - use directly
            corners = approx.reshape(4, 2)
        elif len(approx) > 4:
            # Too many points - find the four extreme corners
            # This handles rounded corners and irregular shapes better
            
            # Get bounding rectangle
            rect = cv2.minAreaRect(approx)
            box = cv2.boxPoints(rect)
            corners = np.array(box, dtype="float32")
        else:
            # Not enough points for a quadrilateral
            logger.info(f"Contour has {len(approx)} points, need at least 4 for alignment")
            return None
        
        # Order points to get top-left, top-right, bottom-right, bottom-left
        rect = order_points(corners)
        
        # Check for skew angle
        (tl, tr, br, bl) = rect
        
        # Calculate angles of edges
        def angle_between_points(p1, p2):
            return np.degrees(np.arctan2(p2[1] - p1[1], p2[0] - p1[0]))
        
        # Get angles of horizontal and vertical edges
        top_angle = angle_between_points(tl, tr)
        bottom_angle = angle_between_points(bl, br)
        left_angle = angle_between_points(tl, bl) - 90  # Should be close to 0 if vertical
        right_angle = angle_between_points(tr, br) - 90  # Should be close to 0 if vertical
        
        # Compute skew as deviation from orthogonal
        h_skew = max(abs(top_angle), abs(bottom_angle))
        v_skew = max(abs(left_angle), abs(right_angle))
        skew = max(h_skew, v_skew)
        
        # For perforation-detected invoices, use a lower threshold
        effective_threshold = skew_threshold * 0.6 if has_perforation else skew_threshold
        
        # Only align if skew is significant
        if skew < effective_threshold:
            logger.info(f"Document skew ({skew:.2f}°) below threshold ({effective_threshold}°), skipping alignment")
            return None
        
        # Get improved destination dimensions that maintain aspect ratio
        # This avoids stretching that might distort text
        width_a = np.sqrt(((br[0] - bl[0]) ** 2) + ((br[1] - bl[1]) ** 2))
        width_b = np.sqrt(((tr[0] - tl[0]) ** 2) + ((tr[1] - tl[1]) ** 2))
        max_width = max(int(width_a), int(width_b))
        
        height_a = np.sqrt(((tr[0] - br[0]) ** 2) + ((tr[1] - br[1]) ** 2))
        height_b = np.sqrt(((tl[0] - bl[0]) ** 2) + ((tl[1] - bl[1]) ** 2))
        max_height = max(int(height_a), int(height_b))
        
        # Ensure reasonable dimensions
        if max_width < 10 or max_height < 10 or max_width > img.shape[1]*5 or max_height > img.shape[0]*5:
            logger.info(f"Unreasonable dimensions calculated: {max_width}x{max_height}, skipping alignment")
            return None
        
        # Destination points
        dst = np.array([
            [0, 0],
            [max_width - 1, 0],
            [max_width - 1, max_height - 1],
            [0, max_height - 1]
        ], dtype="float32")
        
        # Compute perspective transform matrix
        M = cv2.getPerspectiveTransform(rect, dst)
        
        # Apply perspective transformation with border replication to avoid black edges
        warped = cv2.warpPerspective(img, M, (max_width, max_height), borderMode=cv2.BORDER_REPLICATE)
        
        logger.info(f"Indonesian invoice aligned from {img.shape[:2]} to {warped.shape[:2]}, corrected skew: {skew:.2f}°")
        
        # Verify the alignment improved the image
        # In rare cases, a failed alignment might result in all-black or distorted image
        if np.mean(warped) < 10 or np.std(warped) < 5:
            logger.warning("Alignment resulted in invalid image, returning original")
            return None
            
        return warped
    
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


def process_dot_matrix(img: np.ndarray, props: Dict[str, Any]) -> np.ndarray:
    """
    Specialized processing for dot-matrix printed invoices.
    Focuses on connecting broken dots in characters and handling
    colored backgrounds typical in Indonesian invoices.
    
    Args:
        img: Input RGB image
        props: Properties dictionary from detect_invoice_properties
        
    Returns:
        Enhanced grayscale image optimized for OCR
    """
    # Convert to grayscale
    if len(img.shape) == 3:
        # Use optimal channel based on paper color
        if props["paper_color"] == COLORED_PAPERS["PINK"]:
            # For pink paper, blue channel works best
            gray = img[:,:,2]
        elif props["paper_color"] == COLORED_PAPERS["BLUE"]:
            # For blue paper, red channel works best
            gray = img[:,:,0]
        elif props["paper_color"] == COLORED_PAPERS["VIOLET"]:
            # For violet paper, green channel often works best
            gray = img[:,:,1]
        else:
            # Default grayscale conversion for white paper
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    else:
        gray = img.copy()
    
    # 1. Apply adaptive thresholding to handle varying backgrounds
    # This works better for dot-matrix prints on colored paper
    window_size = 25  # Larger window for dot-matrix spacing
    const = 10  # Lower constant for better dot connection
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
        cv2.THRESH_BINARY_INV, window_size, const
    )
    
    # 2. Connect dots using morphological operations
    # Key for improving dot-matrix character recognition
    kernel = np.ones((2, 2), np.uint8)
    connected = cv2.dilate(binary, kernel, iterations=1)
    
    # 3. Clean up noise
    kernel_clean = np.ones((2, 2), np.uint8)
    cleaned = cv2.morphologyEx(connected, cv2.MORPH_OPEN, kernel_clean)
    
    # 4. Fill small holes in letters (especially important for 'e', 'a', etc.)
    kernel_close = np.ones((3, 3), np.uint8)
    closed = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, kernel_close)
    
    # 5. Invert back to black text on white background
    result = cv2.bitwise_not(closed)
    
    return result

def process_handwritten(img: np.ndarray, props: Dict[str, Any]) -> np.ndarray:
    """
    Specialized processing for handwritten invoices.
    Focuses on preserving stroke details while enhancing contrast
    and handling colored backgrounds.
    
    Args:
        img: Input RGB image
        props: Properties dictionary from detect_invoice_properties
        
    Returns:
        Enhanced grayscale image optimized for OCR
    """
    # Convert to grayscale with optimal approach for handwriting
    if len(img.shape) == 3:
        # Convert to HSV to better handle colored backgrounds
        hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
        # Use value channel which separates handwriting best
        gray = hsv[:,:,2]
    else:
        gray = img.copy()
    
    # 1. Apply CLAHE for better contrast
    # Handwriting often has varying pressure points
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    
    # 2. Use bilateral filter to preserve edges (handwriting strokes)
    # while reducing noise - critical for handwritten text
    filtered = cv2.bilateralFilter(enhanced, 9, 20, 20)
    
    # 3. Apply Otsu thresholding to separate handwriting from background
    # Works well after CLAHE enhancement
    _, binary = cv2.threshold(filtered, 0, 255, cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)
    
    # 4. Remove small noise dots (dust, etc.)
    kernel = np.ones((2, 2), np.uint8)
    opened = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    
    # 5. Ensure stroke continuity for OCR
    kernel_close = np.ones((2, 2), np.uint8)
    processed = cv2.morphologyEx(opened, cv2.MORPH_CLOSE, kernel_close)
    
    # 6. Invert back to black text on white background
    result = cv2.bitwise_not(processed)
    
    return result

def process_mixed_content(img: np.ndarray, props: Dict[str, Any]) -> np.ndarray:
    """
    Specialized processing for mixed content invoices (printed headers with handwritten data).
    Balances techniques for both printed and handwritten text recognition.
    
    Args:
        img: Input RGB image
        props: Properties dictionary from detect_invoice_properties
        
    Returns:
        Enhanced grayscale image optimized for OCR
    """
    # For mixed content, process in HSV color space
    if len(img.shape) == 3:
        hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
        h, s, v = cv2.split(hsv)
        
        # Paper color compensation in saturation channel
        if props["paper_color"] != COLORED_PAPERS["WHITE"]:
            # Reduce saturation to minimize colored background impact
            s = cv2.subtract(s, np.full(s.shape, 40, dtype=np.uint8))
        
        # Use value channel for processing (best for mixed content)
        gray = v
    else:
        gray = img.copy()
    
    # 1. Apply adaptive binarization with parameters tuned for mixed content
    # Larger block size handles both printed headers and handwritten content
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
        cv2.THRESH_BINARY, 15, 12
    )
    
    # 2. If dot-matrix elements detected, enhance them
    if props["has_dot_matrix"]:
        # Kernel size tuned for connecting dot-matrix while preserving handwriting
        kernel = np.ones((2, 1), np.uint8)  # Horizontal connection for dot-matrix
        connected = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    else:
        connected = binary
    
    # 3. Apply edge-preserving denoising
    # Balances the needs of both printed and handwritten text
    denoised = cv2.fastNlMeansDenoising(connected, None, h=5, searchWindowSize=13)
    
    # 4. Enhance contrast in a way that works for both text types
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(denoised)
    
    # Final sharpening for clearer character edges (helps OCR)
    kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
    sharpened = cv2.filter2D(enhanced, -1, kernel)
    
    return sharpened


def save_to_webp(img: np.ndarray, quality: int = 95, max_size: int = 800) -> bytes:
    """
    Convert processed image to WebP format with high quality compression.
    Optimized specifically for Indonesian invoice OCR where quality matters
    more than file size.
    
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
    
    # For Indonesian invoices, analyze image characteristics to determine optimal
    # encoding parameters - especially important for dot-matrix prints and handwriting
    
    # Calculate text density - helps determine optimal quality settings
    # Use edge detection to find text ratio
    if len(img.shape) == 2:
        gray = img.copy()
    else:
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        
    # Calculate edge information (text/line density)
    edges = cv2.Canny(gray, 100, 200)
    edge_density = np.count_nonzero(edges) / (gray.shape[0] * gray.shape[1])
    
    # Determine optimal quality based on document characteristics
    # Indonesian invoices with dense text or dot-matrix printing need higher quality
    optimal_quality = quality
    
    if edge_density > 0.1:  # High text density (likely dense tabular data)
        optimal_quality = min(98, quality + 3)
        logger.info(f"High text density ({edge_density:.3f}), using quality {optimal_quality}")
    elif edge_density < 0.03:  # Low text density (likely simple invoice)
        optimal_quality = max(85, quality - 5)
        logger.info(f"Low text density ({edge_density:.3f}), using quality {optimal_quality}")
    
    # Check for dot-matrix patterns which require higher quality
    has_dot_matrix = False
    
    # Simple dot pattern detection
    kernel = np.ones((3, 3), np.uint8)
    dilated = cv2.dilate(edges, kernel, iterations=1)
    dots = cv2.subtract(dilated, edges)
    dot_density = np.count_nonzero(dots) / (gray.shape[0] * gray.shape[1])
    
    if dot_density > 0.02:
        has_dot_matrix = True
        optimal_quality = min(98, optimal_quality + 5)  # Boost quality for dot-matrix
        logger.info(f"Dot-matrix pattern detected (density: {dot_density:.3f}), boosting quality")
    
    # For Indonesian invoices, we prioritize OCR accuracy over file size
    # Use lossless compression for smaller files when possible
    try_lossless = (gray.shape[0] * gray.shape[1] < 1000000) and has_dot_matrix
    
    if try_lossless:
        # Try lossless first for critical documents
        buffer = io.BytesIO()
        pil_img.save(buffer, format="WebP", lossless=True)
        
        # Check if lossless size is acceptable
        lossless_size = len(buffer.getvalue()) / 1024
        if lossless_size <= max_size * 1.2:  # Allow slightly larger files for lossless
            logger.info(f"Using lossless WebP ({lossless_size:.1f} KB) for better OCR accuracy")
            return buffer.getvalue()
    
    # Save with optimal quality (lossy)
    buffer = io.BytesIO()
    pil_img.save(buffer, format="WebP", quality=optimal_quality)
    
    # Get bytes and check size
    img_bytes = buffer.getvalue()
    size_kb = len(img_bytes) / 1024
    current_quality = optimal_quality
    
    # For Indonesian invoices, keep higher minimum quality
    min_quality = 85  # Higher minimum for better OCR results
    
    # Only reduce quality if absolutely necessary and in small steps
    # to maintain OCR accuracy
    if size_kb > max_size and current_quality > min_quality:
        logger.info(f"Initial size ({size_kb:.1f} KB) exceeds limit, reducing quality carefully")
        
        # Reduce quality gently until file size is below max_size
        while size_kb > max_size and current_quality > min_quality:
            # Small quality steps for better control
            current_quality -= 3
            current_quality = max(current_quality, min_quality)
            
            buffer = io.BytesIO()
            pil_img.save(buffer, format="WebP", quality=current_quality)
            img_bytes = buffer.getvalue()
            size_kb = len(img_bytes) / 1024
            logger.info(f"Reduced quality to {current_quality}, new size: {size_kb:.1f} KB")
    
    # If we still exceed max size at minimum quality, we need to resize
    # but do so very carefully to preserve text readability
    if size_kb > max_size * 1.5 and current_quality <= min_quality:
        # For OCR-critical documents, increase max_size rather than resize if possible
        if has_dot_matrix or edge_density > 0.08:
            logger.info(f"Allowing larger size ({size_kb:.1f} KB) for OCR-critical document")
            return img_bytes
            
        # If we must resize, do so with high-quality downsampling
        target_ratio = math.sqrt(max_size / size_kb) * 0.95
        new_width = int(pil_img.width * target_ratio)
        new_height = int(pil_img.height * target_ratio)
        
        # Only resize if the reduction isn't too extreme
        if target_ratio > 0.7:
            # Use high quality LANCZOS resampling
            resized_img = pil_img.resize((new_width, new_height), Image.LANCZOS)
            buffer = io.BytesIO()
            # Use higher quality for resized images
            resized_img.save(buffer, format="WebP", quality=min(current_quality + 8, 98))
            img_bytes = buffer.getvalue()
            size_kb = len(img_bytes) / 1024
            logger.info(f"Resized to {new_width}x{new_height}, final size: {size_kb:.1f} KB")
    
    return img_bytes