import array
import time
import math
import logging

REQUEST_LENGTH = 2**14

class Pieces():

    def __init__(self, torrent):
        self.logger = logging.getLogger('main.pieces')
        self.torrent = torrent
        # self.logger.info(self.torrent.info)
        self.downloaded = {index: array.array('B') for index in range(torrent.number_of_pieces)}
        self.requested = {index: array.array('B') for index in range(torrent.number_of_pieces)}

    def save(self, index, begin_offset, payload):
        """
        saves block sent from peer,
        returns the index if a whole piece is downloaded
        """
        block = array.array('B', payload)
        piece_length = self.torrent.info['piece length']
        self.downloaded[index][begin_offset:begin_offset+len(payload)] = block

        # self.logger.info('piece length: {}'.format(self.torrent.info['piece length']))
        # self.logger.info('index {} length {}'.format(index, len(self.downloaded[index])))


        # return the index when a piece is complete
        if piece_length == len(self.downloaded[index]) or \
                self.torrent.file_length() == self.__len__():
            return index
        else:
            return None

    def is_block_downloaded(self, index, begin_offset):
        if not self.downloaded[index][begin_offset:]:
            return False
        return True

    def __len__(self):
        length = 0
        for key, value in self.downloaded.items():
            length += len(value)

        return length

class PieceQueue():

    def __init__(self, torrent):
        self.logger = logging.getLogger('main.piece_queue')
        self._queue = []
        self.torrent = torrent

    @property
    def queue(self):
        return self._queue

    def add(self, index):
        piece_length = self.torrent.info['piece length']
        for i in range(self.torrent.num_of_blocks()):
            block = {
                'index': index,
                'begin_offset': i * REQUEST_LENGTH,
                'request_length': self.torrent.block_length(i * REQUEST_LENGTH)
            }
            self._queue.append(block)

    def pop(self):
        return self._queue.pop(0)

    def __len__(self):
        return len(self._queue)
