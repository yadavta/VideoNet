from src.models import Qwen25VL
from src.utils.common import extract_bboxs_qwen, draw_bboxs

# # @reza, change these and then re-run file
# !!! NOTE: ONLY WORKS WITH JPG FILES !!!
image = "/gscratch/raivn/tanush/VideoNet/tmp/sql1.jpg"
prompt = "Locate the schema for StateProvince."
output_file = "/gscratch/raivn/tanush/VideoNet/tmp/bbox.jpg"

# ignore the below
qwen = Qwen25VL()
templated = prompt + " Report the bbox coordinates in JSON format."
output = qwen.images_inference(templated, [image], are_paths = [True])[0]
bboxs = extract_bboxs_qwen(output)
print(bboxs)
if not bboxs:
    print("No bounding boxes found")
else:
    draw_bboxs(image, output_file, bboxs)