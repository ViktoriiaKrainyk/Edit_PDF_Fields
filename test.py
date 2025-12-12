import pikepdf
import os

# --- SETTINGS ---
INPUT_FILE = "incoming_veterans_2.pdf"  # Input file
OUTPUT_FILE = "result_moved.pdf"  # Output file
FIELD_NAME = "Signiture1"  # Field name
# New coordinates: [left, bottom, right, top]
# Example: A 200x50 box at position (100, 500)
NEW_COORDS = []
TARGET_PAGE_INDEX = 1  # Target page index (0 = first page)


def set_field_coordinates(input_path, output_path, field_name, new_rect, page_idx=0):
    if not os.path.exists(input_path):
        print(f"❌ File '{input_path}' not found.")
        return

    try:
        pdf = pikepdf.Pdf.open(input_path, allow_overwriting_input=True)

        # 1. Find the field
        target_widget = None
        if "/AcroForm" in pdf.Root and "/Fields" in pdf.Root.AcroForm:
            for field in pdf.Root.AcroForm.Fields:
                if field.get("/T") == field_name:
                    target_widget = field
                    break

        if not target_widget:
            print(f"❌ Field '{field_name}' not found in the document.")
            return

        # 2. "Fix" the object (if it's an indirect reference, get the real dictionary)
        if hasattr(target_widget, "objid"):
            target_widget = pdf.get_object(target_widget.objid)

        print(f"🔧 Updating field '{field_name}'...")

        # 3. SET COORDINATES
        # Pikepdf accepts the coordinate array as a standard list
        target_widget["/Rect"] = new_rect
        print(f"   -> New coordinates set: {new_rect}")

        # 4. (Important) Verify page binding
        # If the field was a "ghost", changing coords alone won't make it visible.
        # We must ensure it is linked to the page's Annots list.

        target_page = pdf.pages[page_idx]

        # A. Update the /P link within the field itself
        target_widget["/P"] = target_page.obj

        # B. Add the field to the page's annotation list (if missing)
        if "/Annots" not in target_page:
            target_page.Annots = []

        # Check if this widget is already on the page to avoid duplicates
        is_already_on_page = False
        target_objid = getattr(target_widget, "objid", None)

        for annot in target_page.Annots:
            if hasattr(annot, "objid") and annot.objid == target_objid:
                is_already_on_page = True
                break

        if not is_already_on_page:
            target_page.Annots.append(target_widget)
            print(f"   -> Field added to annotation list of page {page_idx + 1}.")
        else:
            print(f"   -> Field is already present on page {page_idx + 1}.")

        # C. Remove hidden flags (just in case)
        target_widget["/F"] = 4  # 4 = Print (Visible)

        # 5. Save
        pdf.save(output_path)
        print("-" * 50)
        print(f"✅ Done! File saved: {output_path}")
        print("-" * 50)

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    set_field_coordinates(INPUT_FILE, OUTPUT_FILE, FIELD_NAME, NEW_COORDS, TARGET_PAGE_INDEX)
