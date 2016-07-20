import math
import time
import logging
from random import choice
from string import digits, ascii_letters
from hashlib import sha1
from bcoding import bdecode, bencode


class Torrent():

    def __init__(self, torrent_file):
        self.logger = logging.getLogger('main.torrent')
        self.metainfo = self.read_torrent_file(torrent_file)
        self.announce_url = self.metainfo['announce']
        self.info = self.metainfo['info']
        self.logger.info(self.info['files'])
        pieces_hash = self.info['pieces']
        self.piece_hash_list = []
        while len(pieces_hash) > 0:
            self.piece_hash_list.append(pieces_hash[0:20])
            pieces_hash = pieces_hash[20:]
        self.info_hash = sha1(bencode(self.info)).digest()
        self.peer_id = self.generate_peer_id()
        self.left = self.file_length()
        self.REQUEST_LENGTH = 2**14
        self.number_of_pieces = self.get_number_of_pieces()

    def read_torrent_file(self, torrent_file):
        with open(torrent_file, 'rb') as f:
            return bdecode(f.read())

    def generate_peer_id(self):
        client_id = 'AS'
        version = '0001'
        random_numbers = ''.join(choice(ascii_letters + digits) for i in range(12))
        return '-{}{}-{}'.format(client_id, version, random_numbers)

    def get_number_of_pieces(self):
        return len(self.piece_hash_list)
        # return math.ceil(self.file_length() / self.piece_length)

    def get_files_info(self):
        multi_files = self.info['files']
        files = []
        for f in multi_files:
            files.append({
                'name': f['path'][0],
                'length': f['length'],
                'length_written': 0,
                'done': False
            })

        files_info = {}
        files_info['dirname'] = self.info['name']
        files_info['files'] = files
        return files_info

    def blocks_per_piece(self, piece_index):
        return math.ceil(self.piece_length(piece_index) / self.REQUEST_LENGTH)

    def file_length(self):
        length = 0

        if 'length' in self.info:
            length = self.info['length']
        else:
            files = self.info['files']
            for file_dict in files:
                length += file_dict['length']

        return length

    def piece_length(self, piece_index):
        total_length = self.file_length()
        piece_length = self.info['piece length']
        last_piece_index = math.floor(total_length / piece_length)
        last_piece_length = total_length % piece_length

        return last_piece_length if piece_index == last_piece_index else piece_length

    def block_length(self, piece_index, block_index):
        piece_length = self.piece_length(piece_index)
        last_block_index = math.floor(piece_length / self.REQUEST_LENGTH)
        last_block_length = piece_length % self.REQUEST_LENGTH

        if block_index == last_block_index:
            return last_block_length
        else:
            return self.REQUEST_LENGTH
