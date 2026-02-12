import cv2
import numpy as np
import pandas as pd
from scipy import ndimage as ndi
from skimage.feature import peak_local_max
from skimage.filters import sobel
from skimage.measure import regionprops
from skimage.segmentation import watershed


class WatershedBubbleDetector:
    def __init__(self, clahe_clip_limit=2.0, clahe_tile_size=(8, 8), gaussian_sigma=6,
                 canny_low=20, canny_high=60, morph_kernel_size=(7, 7),
                 close_iterations=2, dilate_iterations=1, peak_footprint_size=29,
                 min_bubble_area=800):
        self.clahe_clip_limit = clahe_clip_limit
        self.clahe_tile_size = clahe_tile_size
        self.gaussian_sigma = gaussian_sigma
        self.canny_low = canny_low
        self.canny_high = canny_high
        self.morph_kernel_size = morph_kernel_size
        self.close_iterations = close_iterations
        self.dilate_iterations = dilate_iterations
        self.peak_footprint_size = peak_footprint_size
        self.min_bubble_area = min_bubble_area
    
    def preprocess_image(self, img):
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        L = lab[:, :, 0]
        clahe_obj = cv2.createCLAHE(clipLimit=self.clahe_clip_limit, 
                                     tileGridSize=self.clahe_tile_size)
        clahe = clahe_obj.apply(L)
        blur = cv2.GaussianBlur(clahe, (0, 0), self.gaussian_sigma)
        return blur
    
    def detect_walls(self, blur):
        edges = cv2.Canny(blur, self.canny_low, self.canny_high)
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, self.morph_kernel_size)
        walls = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, k, iterations=self.close_iterations)
        walls = cv2.dilate(walls, k, iterations=self.dilate_iterations)
        return walls
    
    def watershed_segmentation(self, blur, walls):
        interior = (walls == 0)
        dist = ndi.distance_transform_edt(interior)
        footprint = np.ones((self.peak_footprint_size, self.peak_footprint_size))
        peaks = peak_local_max(dist, footprint=footprint, labels=interior)
        markers = np.zeros(dist.shape, dtype=np.int32)
        markers[tuple(peaks.T)] = np.arange(1, len(peaks) + 1)
        elev = sobel(blur.astype(np.float32) / 255.0)
        labels = watershed(elev, markers, mask=interior)
        return labels
    
    def calculate_metrics(self, labels):
        rows = []
        for r in regionprops(labels):
            if r.area < self.min_bubble_area:
                continue
            A = r.area
            P = r.perimeter if r.perimeter > 0 else 1.0
            deq = np.sqrt(4 * A / np.pi)
            rows.append({
                "label": r.label,
                "area_px": A,
                "perimeter_px": P,
                "eq_diameter_px": deq,
                "cx": r.centroid[1],
                "cy": r.centroid[0],
            })
        df = pd.DataFrame(rows)
        return df
    
    def annotate_image(self, img, labels, df):
        output = img.copy()
        GREEN = (0, 255, 0)
        
        for idx, row in df.iterrows():
            label_id = int(row['label'])
            cx = int(row['cx'])
            cy = int(row['cy'])
            radius = int(row['eq_diameter_px'] / 2)
            
            # Draw circular outline
            cv2.circle(output, (cx, cy), radius, GREEN, 2)
        
        return output
    
    def add_legend(self, img, count, avg_diameter):
        output = img.copy()
        panel = np.ones((100, 280, 3), dtype=np.uint8) * 240
        cv2.rectangle(panel, (0, 0), (279, 99), (0, 0, 0), 2)
        cv2.putText(panel, "BUBBLE DETECTION", (10, 25),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2, cv2.LINE_AA)
        cv2.putText(panel, f"Count: {count}", (15, 55),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
        cv2.putText(panel, f"Avg Size: {avg_diameter:.1f} px", (15, 80),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
        output[10:110, 10:290] = panel
        return output
    
    def process_image(self, image_path, save_csv=True):
        print(f"\nProcessing: {image_path}")
        img = cv2.imread(image_path)
        if img is None:
            raise FileNotFoundError(f"Cannot read image: {image_path}")
        
        print("Running watershed segmentation...")
        blur = self.preprocess_image(img)
        walls = self.detect_walls(blur)
        labels = self.watershed_segmentation(blur, walls)
        df = self.calculate_metrics(labels)
        bubble_count = len(df)
        
        print(f"Detected {bubble_count} bubbles")
        annotated = self.annotate_image(img, labels, df)
        
        if bubble_count > 0:
            avg_diameter = df['eq_diameter_px'].mean()
            annotated = self.add_legend(annotated, bubble_count, avg_diameter)
            
            if save_csv:
                df.to_csv("metrics.csv", index=False)
                print("✓ Metrics saved to metrics.csv")
            
            print(f"Average diameter: {avg_diameter:.1f} px")
            print(f"Diameter range: {df['eq_diameter_px'].min():.1f} - {df['eq_diameter_px'].max():.1f} px")
        else:
            annotated = self.add_legend(annotated, 0, 0)
            print("No bubbles detected")
        
        return annotated, df, bubble_count


def main():
    detector = WatershedBubbleDetector(
        clahe_clip_limit=2.0,
        clahe_tile_size=(8, 8),
        gaussian_sigma=6,
        canny_low=20,
        canny_high=60,
        morph_kernel_size=(7, 7),
        close_iterations=2,
        dilate_iterations=1,
        peak_footprint_size=29,
        min_bubble_area=800
    )
    
    image_path = "test 3.jpg"
    
    try:
        annotated, df, count = detector.process_image(image_path, save_csv=True)
        
        output_path = "bubbles_watershed_annotated.jpg"
        cv2.imwrite(output_path, annotated)
        print(f"✓ Saved: {output_path}\n")
        
        scale = 0.6
        display = cv2.resize(annotated, None, fx=scale, fy=scale)
        cv2.imshow('Watershed Bubble Detection', display)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
        
        return annotated, df, count
        
    except FileNotFoundError as e:
        print(f"\n✗ Error: {e}")
        return None, None, 0
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return None, None, 0


if __name__ == "__main__":
    main()


