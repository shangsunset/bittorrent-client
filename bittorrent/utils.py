import time
import math
import logging


class Pieces():

    def __init__(self, torrent):
        self.logger = logging.getLogger('main.pieces')
        self.torrent = torrent
        self.received = {index: [] for index in range(torrent.number_of_pieces)}
        self.requested = {index: [] for index in range(torrent.number_of_pieces)}
        self.temp_piece_holder = {index: bytes() for index in range(torrent.number_of_pieces)}
        self.total_num_requested = 0

    def add_received(self, block):
        self.received[block['index']].append(block['begin_offset'])
        # self.logger.info(len(self.received[block['index']]))
        self.temp_piece_holder[block['index']] += block['payload']
        if len(self.received[block['index']]) == int(self.torrent.block_per_piece):
            # self.logger.info('we have piece {}'.format(block['index']))
            whole_piece = self.temp_piece_holder[block['index']]
            # self.logger.info(len(whole_piece))
            # self.logger.info(self.torrent.piece_length)
            self.temp_piece_holder[block['index']] = b''
            return (block['index'], whole_piece)
        return (None, None)

    def remove_received(self, index):
        self.received[index] = []

    def add_requested(self, block):
        self.requested[block['index']].append(block['begin_offset'])
        if len(self.requested[block['index']]) == self.torrent.block_per_piece:
            self.total_num_requested += 1

    def block_needed(self, block):
        # in case there are some pieces never received.
        # copy received list to requested, so can request missing pieces
        if self.total_num_requested == self.torrent.number_of_pieces:
            self.requested = self.received.copy()
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
        for i in range(self.torrent.num_of_blocks()):
            block = {
                'index': index,
                'begin_offset': i * self.torrent.REQUEST_LENGTH,
                'request_length': self.torrent.block_length(i * self.torrent.REQUEST_LENGTH)
            }
            self.queue.append(block)

    def pop(self):
        return self.queue.pop(0)

    def __len__(self):
        return len(self.queue)
