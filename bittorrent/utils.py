import array
import time
import logging

class PieceBuffer():

    def __init__(self, torrent):
        self.logger = logging.getLogger('main.piece_buffer')
        self.torrent = torrent
        # store pieces requested from peers
        self.buffer = {index: array.array('B') for index in range(torrent.number_of_pieces)}

    def save(self, index, begin_offset, payload):
        block = array.array('B', payload)
        self.buffer[index][begin_offset:begin_offset+len(payload)] = block

        self.logger.info(self.torrent.info['piece length'])
        self.logger.info(len(self.buffer[index]))
        # return the index when a piece is complete
        if self.torrent.info['piece length'] - len(self.buffer[index]) < 5:
            return index

        return None
