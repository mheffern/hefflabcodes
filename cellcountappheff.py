import cv2
import numpy as np
import streamlit as st

st.set_page_config(page_title="Mammalian Cell Counter", layout="centered")

st.title("🔬 Mammalian Cell Counter & Calculator")
st.write("Optimized for mammalian cell culture images (10-20µm) via phone camera.")

# --- SIDEBAR FOR MATHEMATICAL CALCULATION ---
st.sidebar.header("Concentration Calculator Settings")
squares_counted = st.sidebar.number_input(
    "Number of large squares counted in this image:", 
    min_value=1, max_value=9, value=1, step=1,
    help="Usually 1 if the photo zooms in on one square, or 4 if it captures the whole grid."
)
dilution_factor = st.sidebar.number_input(
    "Dilution Factor:", 
    min_value=1.0, value=1.0, step=0.1,
    help="Set to 2.0 if you did a 1:1 mix with Trypan Blue."
)

# --- IMAGE CAPTURE OR UPLOAD ---
uploaded_file = st.file_uploader("Upload a microscope photo...", type=["jpg", "jpeg", "png"])
camera_file = st.camera_input("Or snap a photo through the eyepiece")

target_file = uploaded_file if uploaded_file is not None else camera_file

if target_file is not None:
    # Convert file to OpenCV image
    file_bytes = np.asarray(bytearray(target_file.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, 1)
    
    # 1. Standardize image size for predictable pixel-area counts
    height, width = img.shape[:2]
    target_width = 1000
    scale = target_width / width
    img_resized = cv2.resize(img, (target_width, int(height * scale)))
    output = img_resized.copy()
    
    # 2. Preprocessing targeted directly at glowing cell centers
    gray = cv2.cvtColor(img_resized, cv2.COLOR_BGR2GRAY)
    
    # Mild smoothing to drop camera sensor grain while protecting the cells
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    
    # 3. Direct Thresholding for High-Contrast Bright Objects
    # 165 is slightly lowered to ensure we catch every single cell's glowing center peak
    _, thresh = cv2.threshold(blurred, 165, 255, cv2.THRESH_BINARY)
    
    # Clean up minor artifacts
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    cleaned = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)
    
    # --- WATERSHED SEGMENTATION TO SEPARATE TOUCHING CELLS ---
    # Compute the distance transform (finds the exact center peaks of overlapping objects)
    dist_transform = cv2.distanceTransform(cleaned, cv2.DIST_L2, 5)
    
    # Threshold the distance image to isolate the absolute core of each individual cell
    # 0.25 is the sensitivity. Lowering it separates tighter clumps; raising it prevents over-splitting.
    _, foreground = cv2.threshold(dist_transform, 0.25 * dist_transform.max(), 255, 0)
    foreground = np.uint8(foreground)
    
    # 4. Count the Isolated Peaks (the individual cells)
    contours, _ = cv2.findContours(foreground, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    cell_count = 0
    MIN_AREA = 8   # Lowered because we are tracking the isolated center peaks of the cells
    MAX_AREA = 800  
    
    for contour in contours:
        area = cv2.contourArea(contour)
        
        if MIN_AREA < area < MAX_AREA:
            cell_count += 1
            
            # Find the center of the peak to draw a precise marker
            M = cv2.moments(contour)
            if M["m00"] != 0:
                cX = int(M["m10"] / M["m00"])
                cY = int(M["m01"] / M["m00"])
            else:
                (x_c, y_c), _ = cv2.minEnclosingCircle(contour)
                cX, cY = int(x_c), int(y_c)
            
            # Draw a clean marker dot and a circle over the actual cells
            cv2.circle(output, (cX, cY), 12, (0, 255, 0), 2)
            cv2.putText(output, str(cell_count), (cX - 8, cY - 14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 255), 1)

    # 5. Hemacytometer Math Calculation
    # Formula: (Cells / Squares) * Dilution * 10^4
    concentration = (cell_count / squares_counted) * dilution_factor * 10000

    # 6. Display Results side-by-side
    st.success("Processing complete!")
    col1, col2 = st.columns(2)
    col1.metric(label="Total Cells Detected", value=cell_count)
    col2.metric(label="Calculated Concentration", value=f"{concentration:,.0f} cells/mL")
    
    # Convert BGR back to RGB for web rendering
    output_rgb = cv2.cvtColor(output, cv2.COLOR_BGR2RGB)
    st.image(output_rgb, caption="Processed Hemacytometer View", use_column_width=True)
