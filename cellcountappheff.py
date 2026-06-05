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
    # Since mammalian cells glow brightly against the grid, we isolate the brightest pixels directly.
    # 170 is the cutoff threshold. If it misses too much, lower it to 150. If it catches grid intersections, raise it to 185.
    _, thresh = cv2.threshold(blurred, 170, 255, cv2.THRESH_BINARY)
    
    # Clean up minor artifacts and separate slightly touching cell borders
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    cleaned = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, kernel, iterations=1)
    
    # 4. Count Contours with Open Constraints
    contours, _ = cv2.findContours(cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    cell_count = 0
    # Dropping min area significantly to make sure small or distant glowing spots register
    MIN_AREA = 15   
    MAX_AREA = 1000  
    
    for contour in contours:
        area = cv2.contourArea(contour)
        perimeter = cv2.arcLength(contour, True)
        
        if MIN_AREA < area < MAX_AREA:
            # Drop circularity check entirely for this test run to maximize total detection
            cell_count += 1
            (x, y), radius = cv2.minEnclosingCircle(contour)
            
            # Draw marker
            cv2.circle(output, (int(x), int(y)), int(radius), (0, 255, 0), 2)
            cv2.putText(output, str(cell_count), (int(x) - 8, int(y) - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)

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
