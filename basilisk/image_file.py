import logging
import mimetypes
import os
import re
import tempfile
import time
from enum import Enum
from functools import cached_property, lru_cache

import httpx

from .image_helper import encode_image, get_image_dimensions, resize_image

log = logging.getLogger(__name__)

URL_PATTERN = re.compile(
	r'(https?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+|data:image/\S+)',
	re.IGNORECASE,
)


def get_display_size(size):
	if size < 1024:
		return f"{size} B"
	if size < 1024 * 1024:
		return f"{size / 1024:.2f} KB"
	return f"{size / 1024 / 1024:.2f} MB"


class ImageFileTypes(Enum):
	UNKNOWN = 0
	IMAGE_LOCAL = 1
	IMAGE_URL = 2


class ImageFile:
	def __init__(
		self,
		location: str,
		name: str = None,
		description: str = None,
		size: int = -1,
		dimensions: tuple = None,
		mime_type: str = None,
	):
		if not isinstance(location, str):
			raise TypeError("path must be a string")
		self._location = location
		self._name = name
		self._description = description
		self._size = size
		self._dimensions = dimensions
		self._mime_type = mime_type
		self._data = None

	@cached_property
	def type(self):
		if os.path.exists(self._location):
			return ImageFileTypes.IMAGE_LOCAL
		if re.match(URL_PATTERN, self._location):
			return ImageFileTypes.IMAGE_URL
		return ImageFileTypes.UNKNOWN

	@lru_cache(maxsize=None)
	def load(self):
		"""Read the image file retrieved from the URL or decode the data URL and populate the metadata."""
		if self.type == ImageFileTypes.IMAGE_LOCAL:
			with open(self._location, "rb") as image_file:
				return image_file.read()
		if self.type == ImageFileTypes.IMAGE_URL:
			if self._location.startswith("http"):
				response = httpx.get(self._location)
				if response.status_code != 200:
					raise ValueError(
						f"Failed to download image from {self._location}: {response.status_code}"
					)
				if "content-type" in response.headers and response.headers[
					"content-type"
				].lower().startswith("image/"):
					self._mime_type = response.headers["content-type"]
				else:
					raise ValueError("Invalid image content type")
				self._size = len(response.content)
				self._dimensions = get_image_dimensions(response.content)
				self._data = response.content
			if self._location.startswith("data:image/"):
				image_data = self._location.split(",", 1)[1]
				encoded_image_data = image_data.encode("utf-8")
				self._size = len(encoded_image_data)
				self._dimensions = get_image_dimensions(encoded_image_data)
				self._data = encoded_image_data
			raise ValueError("Invalid image URL")
		raise ValueError("Invalid image type")

	@cached_property
	def name(self):
		if self._name:
			return self._name
		if self.type == ImageFileTypes.IMAGE_LOCAL:
			return os.path.basename(self._location)
		if self.type == ImageFileTypes.IMAGE_URL:
			return self._location.split("/")[-1]
		return "N/A"

	@cached_property
	def size(self):
		if self.type == ImageFileTypes.IMAGE_LOCAL:
			size = os.path.getsize(self._location)
			return get_display_size(size)
		return "N/A"

	@cached_property
	def dimensions(self):
		if self.type == ImageFileTypes.IMAGE_LOCAL:
			return get_image_dimensions(self._location)
		return None

	@cached_property
	def mime_type(self):
		if self._mime_type:
			return self._mime_type
		if self.type == ImageFileTypes.IMAGE_LOCAL:
			mime_type, _ = mimetypes.guess_type(self._location)
			return mime_type
		if self.type == ImageFileTypes.IMAGE_URL:
			if self._location.startswith("data:image/"):
				return self._location.split(";", 1)[0]
			raise ValueError("Invalid image URL")
		return "N/A"

	@lru_cache(maxsize=None)
	def get_url(
		self, resize=False, max_width=None, max_height=None, quality=None
	) -> str:
		location = self._location
		log.debug(f'Processing image "{location}"')
		if self.type == ImageFileTypes.IMAGE_LOCAL:
			if resize:
				start_time = time.time()
				fd, path_resized_image = tempfile.mkstemp(
					prefix="basilisk_resized_", suffix=".jpg"
				)
				os.close(fd)
				resize_image(
					location,
					max_width=max_width,
					max_height=max_height,
					quality=quality,
					target=path_resized_image,
				)
				log.debug(
					f"Image resized in {time.time() - start_time:.2f} second"
				)
				location = path_resized_image
			start_time = time.time()
			base64_image = encode_image(location)
			if resize:
				os.remove(path_resized_image)
			log.debug(f"Image encoded in {time.time() - start_time:.2f} second")
			mime_type = self.mime_type
			return f"data:{mime_type};base64,{base64_image}"
		raise ValueError("Invalid image type")

	@property
	def display_location(self):
		location = self._location
		if location.startswith("data:image/"):
			location = f"{location[:50]}...{location[-10:]}"
		return location

	def __str__(self):
		location = self.display_location
		return f"{self._name} ({self._size}, {self._dimensions}, {self._description}, {location})"

	def __repr__(self):
		location = self.display_location
		return f"ImageFile(name={self._name}, size={self._size}, dimensions={self._dimensions}, description={self._description}, location={location})"
