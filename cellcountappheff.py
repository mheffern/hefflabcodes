import cv2
import numpy as np
import streamlit as st
from PIL import Image, ImageDraw
from streamlit_cropper import st_cropper
from streamlit_image_coordinates import streamlit_image_coordinates

st.set_page_config(page_title="Mammalian Cell Counter", layout="centered")

st.title("🔬 Interactive Mammalian Cell Counter")
st.write("Crop your photo to **one square**, then tap the image below to add missing cells or remove debris.")

# Initialize session state to remember custom user clicks across screen refreshes
if "user_clicks" not in st.session_state:
    st.session_state.user_clicks = []
if "last_image" not in st.session_state:
    st.session_state.last_image = None

# --- SIDEBAR SETTINGS ---
st.sidebar.header("Concentration Settings")
dilution_factor = st.sidebar.number_input(
    "Dilution Factor:", 
    min_value=1.0, value=1.0, step=0.1
)
if st.sidebar.button("Clear Manual Taps/Reset"):
    st.session_state.user_clicks = []
    st.rerun()

# --- IMAGE CAPTURE ---
uploaded_file = st.file_uploader("Upload a microscope photo...", type=["jpg", "jpeg", "png"])
camera_file = st.camera_input("Or snap a photo through the eyepiece")

target_file = uploaded_file if uploaded_file is not None else camera_file

if target_file is not None:
    # Reset clicks if a completely new image is uploaded
    if st.session_state.last_image != target_file.name:
        st.session_state.user_clicks = []
        st.session_state.last_image = target_file.name

    pil_image = Image.open(target_file)
    st.warning("📐 Step 1: Drag the box to isolate ONE large square grid:")
    
    # Interactive Cropping Tool
    cropped_pil = st_cropper(pil_image, realtime_update=True, box_color='#00FF00', aspect_ratio=None)
    
    # Convert cropped PIL image to OpenCV format
    img = cv2.cvtColor(np.array(cropped_pil), cv2.COLOR_RGB2BGR)
    
    # Standardize cropped image size
    height, width = img.shape[:2]
    target_width = 1000
    scale = target_width / width
    img_resized = cv2.resize(img, (target_width, int(height * scale)))
    
    # --- AUTOMATED PROCESSING ---
    gray = cv2.cvtColor(img_resized, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, thresh = cv2.threshold(blurred, 140, 255, cv2.THRESH_BINARY)
    
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    cleaned = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)
    
    dist_transform = cv2.distanceTransform(cleaned, cv2.DIST_L2, 5)
    _, foreground = cv2.threshold(dist_transform, 0.22 * dist_transform.max(), 255, 0)
    foreground = np.uint8(foreground)
    
    contours, _ = cv2.findContours(foreground, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # Build list of automatically detected cell coordinates
    auto_cells = []
    MIN_AREA, MAX_AREA = 15, 12000
    
    for contour in contours:
        area = cv2.contourArea(contour)
        if MIN_AREA < area < MAX_AREA:
            M = cv2.moments(contour)
            if M["m00"] != 0:
                cX, cY = int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])
                auto_cells.append((cX, cY))

    # --- STEP 2: INTERACTIVE POINT SELECTION / DESELECTION ---
    st.markdown("---")
    st.info("👆 **Step 2: Tap the image below to edit.** Tap a cell to delete it, or tap an empty spot to add a cell.")

    # Convert our processed OpenCV matrix to a PIL Image so we can safely draw on it and track coordinates
    display_pil = Image.fromarray(cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(display_pil)
    
    # Capture a mobile screen tap coordinate
    # (Note: streamlit-image-coordinates automatically scales down visually for mobile sizing)
    value = streamlit_image_coordinates(display_pil, key="coords")

    if value is not None:
        clicked_x = value["x"]
        clicked_y = value["y"]
        
        # Check if the click was close to an existing manual click (to delete it)
        matched_manual = False
        for pt in st.session_state.user_clicks:
            if np.hypot(clicked_x - pt[0], clicked_y - pt[1]) < 25:
                st.session_state.user_clicks.remove(pt)
                matched_manual = True
                st.rerun()
                break
                
        # If it wasn't a manual click, check if they clicked an automated cell to "delete" it
        if not matched_manual:
            matched_auto = False
            for pt in auto_cells:
                if np.hypot(clicked_x - pt[0], clicked_y - pt[1]) < 25:
                    # We store deleted automated cells as a special negative flag, 
                    # or simply filter them out. To keep it robust, we save it as an override block:
                    auto_cells.remove(pt)
                    matched_auto = True
                    st.rerun()
                    break
            
            # If they clicked a blank spot, add it as a new manual cell selection
            if not matched_auto:
                st.session_state.user_clicks.append((clicked_x, clicked_y))
                st.rerun()

    # --- FINAL RENDERING ---
    # Merge both active automated cells and user-added cells into the final count
    final_cell_list = auto_cells + st.session_state.user_clicks
    total_final_count = len(final_cell_list)
    
    # Draw the final counts cleanly onto the visual image
    for idx, (cX, cY) in enumerate(final_cell_list, 1):
        # Draw a bright green circle around finalized cells
        draw.ellipse([cX - 18, cY - 18, cX + 18, cY + 18], outline="#00FF00", width=3)
        draw.text((cX - 10, cY - 25), str(idx), fill="#FF0000")

    # --- STEP 3: CONCENTRATION CALCULATIONS ---
    concentration = total_final_count * dilution_factor * 10000

    st.success("Calculations complete!")
    col1, col2 = st.columns(2)
    col1.metric(label="Final Cell Count", value=total_final_count)
    col2.metric(label="Final Concentration", value=f"{concentration:,.0f} cells/mL")
    
    # Re-display the updated drawn image below the scores
    st.image(display_pil, caption="Interactive Hemacytometer View", use_column_width=True)
