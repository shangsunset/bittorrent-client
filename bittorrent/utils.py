import array
import time
import logging

class DataBuffer():

    def __init__(self, torrent):
        self.logger = logging.getLogger('main.piece_buffer')
        self.torrent = torrent
        self.logger.info(self.torrent.info)
        self.buffer = {index: array.array('B') for index in range(torrent.number_of_pieces)}

    def save(self, index, begin_offset, payload):
        """
        saves block sent from peer,
        returns the index if a whole piece is downloaded
        """
        block = array.array('B', payload)
        piece_length = self.torrent.info['piece length']
        self.buffer[index][begin_offset:begin_offset+len(payload)] = block

        self.logger.info('piece length: {}'.format(self.torrent.info['piece length']))
        self.logger.info('index {} length {}'.format(index, len(self.buffer[index])))
        # return the index when a piece is complete

        # if self.torrent.file_length() % piece_length == 0:
        self.logger.info(self.__len__())
        self.logger.info(self.torrent.file_length())
        if piece_length == len(self.buffer[index]):
            return index
        elif self.torrent.file_length() == self.__len__():
            return index
        else:
            return None

    def is_block_downloaded(self, index, begin_offset):
        if not self.buffer[index][begin_offset:]:
            return False
        return True

    def __len__(self):
        length = 0
        for key, value in self.buffer.items():
            length += len(value)

        return length

