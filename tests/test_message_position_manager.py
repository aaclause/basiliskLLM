import unittest

from basilisk.message_segment_manager import (
	MessageSegment,
	MessageSegmentManager,
	MessageSegmentType,
)


class TestMessagePositionManager(unittest.TestCase):
	def setUp(self):
		self.segments = [
			MessageSegment(length=7, kind=MessageSegmentType.CONTENT),
			MessageSegment(length=14, kind=MessageSegmentType.PREFIX),
			MessageSegment(length=21, kind=MessageSegmentType.CONTENT),
		]
		self.manager = MessageSegmentManager(self.segments)

	def test_initial_state(self):
		self.assertEqual(self.manager.position, 0, "Initial index should be 0")
		self.assertEqual(
			self.manager.absolute_position,
			0,
			"Initial absolute position should be 0",
		)

	def test_next(self):
		self.manager.next()
		self.assertEqual(self.manager.position, 1)
		self.assertEqual(self.manager.start, 7)
		self.assertEqual(self.manager.end, 7 + 14)

	def test_next_with_type(self):
		self.manager.next(MessageSegmentType.CONTENT)
		self.assertEqual(self.manager.position, 2)
		self.assertEqual(self.manager.start, 7 + 14)
		self.assertEqual(self.manager.end, 7 + 14 + 21)

	def test_next_with_type_not_found(self):
		self.manager.position = len(self.segments) - 1
		with self.assertRaises(IndexError):
			self.manager.next("nonexistent_type")

	def test_previous(self):
		self.manager.next()
		self.manager.next()
		self.manager.previous()
		self.assertEqual(self.manager.position, 1)
		self.assertEqual(self.manager.start, 7)
		self.assertEqual(self.manager.end, 7 + 14)

	def test_previous_with_type(self):
		self.manager.next()
		self.manager.next()
		self.manager.previous(MessageSegmentType.PREFIX)
		self.assertEqual(self.manager.position, 1)
		self.assertEqual(self.manager.start, 7)
		self.assertEqual(self.manager.end, 7 + 14)

	def test_previous_with_type_not_found(self):
		with self.assertRaises(IndexError):
			self.manager.previous("nonexistent_type")

	def test_insert(self):
		new_position = MessageSegment(length=5, kind=MessageSegmentType.PREFIX)
		self.manager.insert(2, new_position)
		self.assertEqual(self.manager.segments[2], new_position)
		self.assertEqual(self.manager.start, 0)
		self.assertEqual(self.manager.end, 7)
		self.assertEqual(self.manager.segments[3].length, 7 + 14)
		self.manager.position = 3
		self.assertEqual(self.manager.start, 7 + 5 + 14)
		self.assertEqual(self.manager.end, 7 + 5 + 14 + 21)

	def test_append(self):
		new_position = MessageSegment(length=28, kind=MessageSegmentType.PREFIX)
		self.manager.append(new_position)
		self.assertEqual(self.manager.segments[-1], new_position)
		self.assertEqual(self.manager.start, 0)
		self.assertEqual(self.manager.end, 7)

	def test_remove(self):
		position_to_remove = self.segments[1]
		self.manager.remove(position_to_remove)
		self.assertNotIn(position_to_remove, self.manager.segments)
		self.assertEqual(self.manager.start, 0)
		self.assertEqual(self.manager.end, 7)

	def test_absolute_position_setter(self):
		self.manager.absolute_position = 0
		self.assertEqual(self.manager.position, 0)
		self.assertEqual(self.manager.start, 0)
		self.assertEqual(self.manager.end, 7)
		self.manager.absolute_position = 7
		self.assertEqual(self.manager.position, 1)
		self.assertEqual(self.manager.start, 7)
		self.assertEqual(self.manager.end, 7 + 14)
		self.manager.absolute_position = 20
		self.assertEqual(self.manager.position, 1)
		self.assertEqual(self.manager.start, 7)
		self.assertEqual(self.manager.end, 7 + 14)
		self.manager.absolute_position = 7 + 14 + 21
		self.assertEqual(self.manager.position, 2)
		self.assertEqual(self.manager.absolute_position, 42)
		with self.assertRaises(ValueError):
			self.manager.absolute_position = -1
		self.manager.absolute_position = 1024
		self.assertEqual(self.manager.absolute_position, 42)

	def test_out_of_bounds_positions(self):
		with self.assertRaises(ValueError):
			self.manager.position = -1
		with self.assertRaises(ValueError):
			self.manager.position = len(self.segments)

	def test_str_repr(self):
		self.assertEqual(str(self.manager), "MessageBlockPosition(0/3)")
		self.assertEqual(repr(self.manager), "MessageBlockPosition(0/3)")

	def test_iteration_and_indexing(self):
		expected = self.segments[0]
		self.assertEqual(self.manager[0], expected)
		self.assertEqual(len(self.manager), len(self.segments))
		for pos in self.manager:
			self.assertIn(pos, self.segments)


if __name__ == "__main__":
	unittest.main()
