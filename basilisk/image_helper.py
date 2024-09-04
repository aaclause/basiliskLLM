import base64

from PIL import Image


def get_image_dimensions(path):
	"""
	Get the dimensions of an image.
	"""
	img = Image.open(path)
	return img.size


def resize_image(
	src: str,
	max_width: int = 0,
	max_height: int = 0,
	quality: int = 85,
	target: str = "Compressed.PNG",
) -> bool:
	"""
	Compress an image and save it to a specified file by resizing according to
	given maximum dimensions and adjusting the quality.

	@param src: path to the source image.
	@param max_width: Maximum width for the compressed image. If 0, only `max_height` is used to calculate the ratio.
	@param max_height: Maximum height for the compressed image. If 0, only `max_width` is used to calculate the ratio.
	@param quality: the quality of the compressed image
	@param target: output path for the compressed image
	@return: True if the image was successfully compressed and saved, False otherwise
	"""
	if max_width <= 0 and max_height <= 0:
		return False
	image = Image.open(src)
	if image.mode in ("RGBA", "P"):
		image = image.convert("RGB")
	orig_width, orig_height = image.size
	if max_width > 0 and max_height > 0:
		ratio = min(max_width / orig_width, max_height / orig_height)
	elif max_width > 0:
		ratio = max_width / orig_width
	else:
		ratio = max_height / orig_height
	new_width = int(orig_width * ratio)
	new_height = int(orig_height * ratio)
	resized_image = image.resize(
		(new_width, new_height), Image.Resampling.LANCZOS
	)
	resized_image.save(target, optimize=True, quality=quality)
	return True


def encode_image(image_path):
	with open(image_path, "rb") as image_file:
		return base64.b64encode(image_file.read()).decode('utf-8')
