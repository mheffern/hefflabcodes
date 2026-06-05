import cv2
import numpy as np
import streamlit as st
from PIL import Image
from streamlit_cropper import st_cropper

st.set_page_config(page_title="Mammalian Cell Counter", layout="centered")

st.title("🔬 Mammalian Cell Counter & Calculator")
st.write("Crop your photo down to **one single large square grid** to calculate concentration.")

# --- SIDEBAR SETTINGS ---
st.sidebar.header("Concentration Settings")
dilution_factor = st.sidebar.number_input(
    "Dilution Factor:", 
    min_value=1.0, value=1.0, step=0.1,
    help="Set to 2.0 if you did a 1:1 mix with Trypan Blue."
)

# --- IMAGE CAPTURE ---
uploaded_file = st.file_uploader("Upload a microscope photo...", type=["jpg", "jpeg", "png"])
camera_file = st.camera_input("Or snap a photo through the eyepiece")

target_file = uploaded_file if uploaded_file is not None else camera_file

if target_file is not None:
    # Load image via PIL for the cropper tool
    pil_image = Image.open(target_file)
    
    st.warning("📐 Drag the box below to isolate exactly ONE large square grid:")
    
    # Interactive Cropping Tool (returns a PIL image of just the cropped region)
    # box_color dictates the color of the cropping boundary overlay
    cropped_pil = st_cropper(pil_image, realtime_update=True, box_color='#00FF00', aspect_ratio=None)
    
    # Convert cropped PIL image to OpenCV format
    img = cv2.cvtColor(np.array(cropped_pil), cv2.COLOR_RGB2BGR)
    
    # 1. Standardize cropped image size for predictable pixel-area counts
    height, width = img.shape[:2]
    target_width = 1000
    scale = target_width / width
    img_resized = cv2.resize(img, (target_width, int(height * scale)))
    output = img_resized.copy()
    
    # 2. Preprocessing & Smoothing
    gray = cv2.cvtColor(img_resized, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    
    # 3. Direct Thresholding for Glowing Centers
    _, thresh = cv2.threshold(blurred, 150, 255, cv2.THRESH_BINARY)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    cleaned = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)
    
    # --- WATERSHED CLUSTER-SLICING ---
    dist_transform = cv2.distanceTransform(cleaned, cv2.DIST_L2, 5)
    _, foreground = cv2.threshold(dist_transform, 0.18 * dist_transform.max(), 255, 0)
    foreground = np.uint8(foreground)
    
    # 4. Count the Isolated Peaks inside the cropped region
    contours, _ = cv2.findContours(foreground, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    cell_count = 0
    MIN_AREA = 5   
    MAX_AREA = 800  
    
    for contour in contours:
        area = cv2.contourArea(contour)
        if MIN_AREA < area < MAX_AREA:
            cell_count += 1
            M = cv2.moments(contour)
            if M["m00"] != 0:
                cX = int(M["m10"] / M["m00"])
                cY = int(M["m01"] / M["m00"])
            else:
                (x_c, y_c), _ = cv2.minEnclosingCircle(contour)
                cX, cY = int(x_c), int(y_c)
            
            cv2.circle(output, (cX, cY), 12, (0, 255, 0), 2)
            cv2.putText(output, str(cell_count), (cX - 8, cY - 14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 255), 1)
    
    # --- STEP 5: MANUAL OVERRIDE AND MATHEMATICAL CALCULATION ---
    st.markdown("---")
    st.subheader("📝 Verify and Adjust Count")
    
    # This input box defaults to the computer's count, but let's the student change it
    final_count = st.number_input(
        "Adjusted Cell Count for this square:",
        min_value=0,
        value=int(cell_count),
        step=1,
        help="If the green circles missed a cell or counted debris, change this number to fix the math."
    )
    
    # Concentration math updates dynamically based on the student's manual input
    # Formula: (Adjusted Cells / 1) * Dilution * 10^4
    concentration = final_count * dilution_factor * 10000

    # --- STEP 6: DISPLAY FINAL RESULTS ---
    st.success("Calculations complete!")
    col1, col2 = st.columns(2)
    col1.metric(label="Cells Used for Math", value=final_count)
    col2.metric(label="Final Concentration", value=f"{concentration:,.0f} cells/mL")
    
    # Convert back to RGB for web display
    output_rgb = cv2.cvtColor(output, cv2.COLOR_BGR2RGB)
    st.image(output_rgb, caption="Counted View of Selected Grid Square", use_column_width=True)# 5. Hemacytometer Math Calculation (Always based on 1 square now)
    # Formula: (Cells / 1) * Dilution * 10^4
    concentration = cell_count * dilution_factor * 10000

    # 6. Display Results
    st.success("Analysis complete for the cropped square!")
    col1, col2 = st.columns(2)
    col1.metric(label="Cells in Selected Square", value=cell_count)
    col2.metric(label="Calculated Concentration", value=f"{concentration:,.0f} cells/mL")
    
    # Convert back to RGB for display
    output_rgb = cv2.cvtColor(output, cv2.COLOR_BGR2RGB)
    st.image(output_rgb, caption="Counted View of Selected Grid Square", use_column_width=True)
