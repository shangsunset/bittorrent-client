import time
import math
import logging


class Pieces():

    def __init__(self, torrent):
        self.logger = logging.getLogger('main.pieces')
        self.torrent = torrent
        self.received = {index: set() for index in range(torrent.number_of_pieces)}
        self.requested = {index: set() for index in range(torrent.number_of_pieces)}
        self.temp_piece_holder = {index: bytearray(self.torrent.piece_length(index)) for index in range(torrent.number_of_pieces)}
        self.end_game_mode = False
        self.total_pieces_requested = 0

    def add_received(self, block):
        begin = block['begin_offset']
        index = block['index']
        self.received[index].add(begin)
        self.temp_piece_holder[index][begin:len(block['payload'])+begin] = block['payload']

        # self.logger.info(self.temp_piece_holder[index])
        if len(self.received[index]) == self.torrent.blocks_per_piece(index):
            whole_piece = self.temp_piece_holder[index]
            self.temp_piece_holder[index] = bytearray()
            return (index, whole_piece)
        return (None, None)

    def discard_piece(self, index):
        self.received[index] = set()
        self.requested[index] = set()

    def add_requested(self, block):
        self.requested[block['index']].add(block['begin_offset'])
        if len(self.requested[block['index']]) == self.torrent.blocks_per_piece(block['index']):
            self.total_pieces_requested += 1

    def needed(self, block):
        # in case there are some pieces never received.
        # copy received list to requested, so can request missing pieces
        if self.total_pieces_requested == self.torrent.number_of_pieces:
            self.requested = self.received.copy()

        # self.logger.debug(self.requested[block['index']])
        # self.logger.info('index {}: {}'.format(index, len(self.requested[index])))
        return block['begin_offset'] not in self.requested[block['index']]

    def __len__(self):
        length = 0
        for key, value in self.received.items():
            length += len(value)

        return length

class PieceQueue():

    def __init__(self, torrent):
        self.logger = logging.getLogger('main.piece_queue')
        self.queue = []
        self.torrent = torrent

    def add(self, index):
        piece_length = self.torrent.info['piece length']
        for i in range(self.torrent.blocks_per_piece(index)):
            block = {
                'index': index,
                'begin_offset': i * self.torrent.REQUEST_LENGTH,
                'request_length': self.torrent.block_length(index, i)
            }
            self.queue.append(block)

    def pop(self):
        return self.queue.pop(0)

    def __len__(self):
        return len(self.queue)
