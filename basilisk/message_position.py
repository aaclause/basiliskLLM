import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

log = logging.getLogger(__name__)


class MessagePositionType(Enum):
	PREFIX = "prefix"
	CONTENT = "content"
	SUFFIX = "suffix"


@dataclass
class MessagePosition:
	relative_position: int
	kind: MessagePositionType


class MessagePositionManager:
	positions: List[MessagePosition] = field(default_factory=list)
	_current_index: int = -1
	_absolute_position: int = -1

	def __init__(self, positions: List[MessagePosition] = []):
		self.positions = positions
		self._current_index = -1
		self._absolute_position = -1
		if positions:
			self.position = 0

	def previous(self, message_position_type: Optional[str] = None) -> int:
		"""Move to the previous position"""
		if self._current_index <= 0:
			raise IndexError("Cannot move to previous position")
		current_position = self._current_index - 1
		if message_position_type is not None:
			while (
				current_position >= 0
				and self.positions[current_position].kind
				!= message_position_type
			):
				current_position -= 1

		if current_position < 0:
			raise IndexError("Cannot move to previous position")
		self.position = current_position
		return self.absolute_position

	def next(self, message_position_type: Optional[str] = None) -> int:
		"""Move to the next position"""
		if self._current_index >= len(self.positions) - 1:
			raise IndexError("Cannot move to next position")
		current_position = self._current_index + 1
		if message_position_type is not None:
			while (
				current_position < len(self.positions)
				and self.positions[current_position].kind
				!= message_position_type
			):
				current_position += 1

		if current_position >= len(self.positions):
			raise IndexError("Cannot move to next position")
		self.position = current_position
		return self.absolute_position

	@property
	def message_position(self) -> MessagePosition:
		return self.positions[self._current_index]

	@property
	def position(self) -> int:
		return self._current_index

	@position.setter
	def position(self, value: int):
		if value < 0 or value >= len(self.positions):
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
		relative_position_sum = 0
		for index, position in enumerate(self.positions):
			relative_position_sum += position.relative_position
			if relative_position_sum > absolute_position:
				self.position = index - 1
				return
		self.position = len(self.positions) - 1

	def insert(self, index: int, value: MessagePosition):
		self.positions.insert(index, value)
		self._refresh_absolute_position()

	def append(self, value: MessagePosition):
		self.positions.append(value)
		log.debug(f"Positions: {self.positions}")
		self._refresh_absolute_position()

	def remove(self, value: MessagePosition):
		self.positions.remove(value)
		self._refresh_absolute_position()

	def index(self, value: MessagePosition) -> int:
		return self.positions.index(value)

	def _refresh_absolute_position(self):
		"""Refresh the absolute position based on the current index"""
		if not self.positions:
			self._absolute_position = -1
		else:
			self._absolute_position = 0
			for position in self.positions[: self._current_index + 1]:
				self._absolute_position += position.relative_position
		log.debug(f"New absolute position: {self._absolute_position}")

	def __len__(self) -> int:
		return len(self.positions)

	def __str__(self) -> str:
		return (
			f"MessageBlockPosition({self._current_index}/{len(self.positions)})"
		)

	def __repr__(self) -> str:
		return self.__str__()

	def __iter__(self):
		return iter(self.positions)

	def __getitem__(self, index: int) -> MessagePosition:
		return self.positions[index]

	def __setitem__(self, index: int, value: MessagePosition):
		self.positions[index] = value
		self._refresh_absolute_position()

	def __delitem__(self, index: int):
		del self.positions[index]
		self._refresh_absolute_position()
