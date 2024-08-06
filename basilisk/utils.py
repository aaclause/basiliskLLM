def get_corrected_position(
	position: int, text: str, reverse: bool = False, count_newlines: bool = True
) -> int:
	"""Get the corrected position for a given position in a text for wx.TextCtrl"""
	if not isinstance(position, int):
		raise ValueError("Invalid position")
	if not isinstance(text, str):
		raise ValueError("Invalid text")
	if not text:
		return -1

	adjusted_position = position
	for i, c in enumerate(text[:position]):
		if 0x10000 <= ord(c):
			adjusted_position += -1 if reverse else 1
		if c == "\n" and count_newlines:
			adjusted_position += -1 if reverse else 1

	return adjusted_position
