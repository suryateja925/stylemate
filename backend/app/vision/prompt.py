DETECTION_SCHEMA_INSTRUCTIONS = """
Return JSON only with this shape:
{
  "detections": [
    {
      "temporary_id": "garment-1",
      "category": "shirt|t-shirt|trousers|jeans|dress|skirt|jacket|shorts|sweater|traditional|footwear|accessory|other",
      "subcategory": "string or null",
      "primary_color": "string or null",
      "secondary_colors": ["strings"],
      "pattern": "string or null",
      "visibility_status": "mostly_visible|partially_occluded|heavily_occluded|unidentifiable",
      "confidence": 0.0,
      "bounding_box": {"x_min": 0.0, "y_min": 0.0, "x_max": 1.0, "y_max": 1.0},
      "uncertainty_explanation": "string or null",
      "requires_review": true
    }
  ],
  "needs_more_photos": false,
  "summary": "brief evidence-based summary"
}

Rules:
- Identify only individually distinguishable garments supported by visible pixels.
- Never infer hidden garments, exact brands, or colors that cannot be seen.
- Use normalized bounding-box coordinates from 0 to 1 and make them enclose the visible garment.
- Mark partially or heavily occluded items for review and set uncertain fields to null.
- A rectangular crop is made from each box later; do not claim it is background removed.
"""
