import math
import logging
from random import choice
from string import digits, ascii_letters
from hashlib import sha1
from bcoding import bdecode, bencode


class Torrent():

    def __init__(self, torrent_file):
        self.logger = logging.getLogger('main.torrent')
        self.metainfo = self.read_torrent_file(torrent_file)
        self.tracker_url = self.metainfo['announce']
        self.info = self.metainfo['info']
        self.logger.info(self.info['files'])
        self.info_hash = sha1(bencode(self.info)).digest()
        self.peer_id = self.generate_peer_id()
        self.left = self.file_length()
        self.piece_length = self.info['piece length']
        self.REQUEST_LENGTH = 2**14
        self.number_of_pieces = self.number_of_pieces()
        self.block_per_piece = self.piece_length / self.REQUEST_LENGTH
        pieces_hash = self.info['pieces']
        self.piece_hash_list = []
        while len(pieces_hash) > 0:
            self.piece_hash_list.append(pieces_hash[0:20])
            pieces_hash = pieces_hash[20:]

    def read_torrent_file(self, torrent_file):
        with open(torrent_file, 'rb') as f:
            return bdecode(f.read())

    def generate_peer_id(self):
        client_id = 'AS'
        version = '0001'
        random_numbers = ''.join(choice(ascii_letters + digits) for i in range(12))
        return '-{}{}-{}'.format(client_id, version, random_numbers)

    def number_of_pieces(self):
        return math.ceil(self.file_length() / self.piece_length)

    def file_length(self):
        length = 0

        if 'length' in self.info:
            length = self.info['length']
        else:
            files = self.info['files']
            for file_dict in files:
                length += file_dict['length']

        return length

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

    def num_of_blocks(self):
        return math.ceil(self.piece_length / self.REQUEST_LENGTH)

    def block_length(self, begin_offset):
        if self.piece_length - begin_offset < self.REQUEST_LENGTH:
            return self.piece_length - begin_offset
        else:
            return self.REQUEST_LENGTH

    def __str__(self):
        return 'info_hash: {}, peer_id: {}, left: {}'.format(
            self.info_hash, self.peer_id, self.left
            )
