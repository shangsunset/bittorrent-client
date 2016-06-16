import array
import time
import logging

class DataBuffer():

    def __init__(self, torrent):
        self.logger = logging.getLogger('main.piece_buffer')
        self.torrent = torrent
        self.buffer = {index: array.array('B') for index in range(torrent.number_of_pieces)}

    def save(self, index, begin_offset, payload):
        """
        saves block sent from peer,
        returns the index if a whole piece is downloaded
        """
        block = array.array('B', payload)
        self.buffer[index][begin_offset:begin_offset+len(payload)] = block

        # return the index when a piece is complete
        if self.torrent.info['piece length'] == len(self.buffer[index]):
            return index

        return None

    def is_block_downloaded(self, index, begin_offset):
        if not self.buffer[index][begin_offset:]:
            return False
        return True

