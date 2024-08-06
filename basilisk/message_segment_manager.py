import weakref
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from basilisk.conversation import MessageBlock


class MessageSegmentType(Enum):
	PREFIX = "prefix"
	CONTENT = "content"
	SUFFIX = "suffix"


@dataclass
class MessageSegment:
	length: int
	kind: MessageSegmentType
	message_block: weakref.ReferenceType[MessageBlock] = None


class MessageSegmentManager:
	def __init__(self, positions: Optional[List[MessageSegment]] = None):
		self.segments: List[MessageSegment] = (
			positions if positions is not None else []
		)
		self._current_index: int = -1
		self._absolute_position: int = -1
		if self.segments:
			self.position = 0
			self._absolute_position = 0

	def previous(
		self, message_position_type: Optional[MessageSegmentType] = None
	) -> int:
		"""Move to the previous position"""
		if self._current_index <= 0:
			raise IndexError("Cannot move to previous position")
		current_position = self._current_index - 1
		if message_position_type is not None:
			while (
				current_position >= 0
				and self.segments[current_position].kind
				!= message_position_type
			):
				current_position -= 1

		if current_position < 0:
			raise IndexError("Cannot move to previous position")
		self.position = current_position
		return self.absolute_position

	def next(
		self, message_position_type: Optional[MessageSegmentType] = None
	) -> int:
		"""Move to the next position"""
		if self._current_index >= len(self.segments) - 1:
			raise IndexError("Cannot move to next position")
		current_position = self._current_index + 1
		if message_position_type is not None:
			while (
				current_position < len(self.segments)
				and self.segments[current_position].kind
				!= message_position_type
			):
				current_position += 1

		if current_position >= len(self.segments):
			raise IndexError("Cannot move to next position")
		self.position = current_position
		return self.absolute_position

	@property
	def current_segment(self) -> MessageSegment:
		return self.segments[self._current_index]

	@property
	def position(self) -> int:
		return self._current_index

	@position.setter
	def position(self, value: int):
		if value < 0 or value >= len(self.segments):
			raise ValueError("Invalid current index")
		self._current_index = value
		self._refresh_absolute_position()

	@property
	def absolute_position(self) -> int:
		"""Get the absolute position of the current index"""
		return self._absolute_position

	@absolute_position.setter
	def absolute_position(self, absolute_position: int):
		if absolute_position < 0:
			raise ValueError("Invalid absolute position")
		length_sum = 0
		for index, segment in enumerate(self.segments):
			length_sum += segment.length
			if length_sum > absolute_position:
				self.position = index
				self._refresh_absolute_position()
				return
		self.position = len(self.segments) - 1
		self._refresh_absolute_position()

	@property
	def start(self) -> int:
		"""Get the start position of the current index"""
		return self.absolute_position - self.current_segment.length

	@property
	def end(self) -> int:
		"""Get the end position of the current index"""
		return self.absolute_position

	def insert(self, index: int, value: MessageSegment):
		self.segments.insert(index, value)
		self._refresh_absolute_position()

	def append(self, value: MessageSegment):
		self.segments.append(value)
		self._refresh_absolute_position()

	def remove(self, value: MessageSegment):
		self.segments.remove(value)
		self._refresh_absolute_position()

	def clear(self):
		self.segments.clear()
		self._current_index = -1
		self._absolute_position = -1

	def index(self, value: MessageSegment) -> int:
		return self.segments.index(value)

	def _refresh_absolute_position(self):
		"""Refresh the absolute position based on the current index"""
		self._absolute_position = 0
		for position in self.segments[: self._current_index]:
			self._absolute_position += position.length
		if self._current_index >= 0:
			self._absolute_position += self.segments[self._current_index].length

	def __len__(self) -> int:
		return len(self.segments)

	def __str__(self) -> str:
		return (
			f"MessageBlockPosition({self._current_index}/{len(self.segments)})"
		)

	def __repr__(self) -> str:
		return self.__str__()

	def __iter__(self):
		return iter(self.segments)

	def __getitem__(self, index: int) -> MessageSegment:
		return self.segments[index]

	def __setitem__(self, index: int, value: MessageSegment):
		self.segments[index] = value
		self._refresh_absolute_position()

	def __delitem__(self, index: int):
		del self.segments[index]
		self._refresh_absolute_position()
