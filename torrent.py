from random import choice
from string import digits
from hashlib import sha1
from bcoding import bdecode, bencode


class Torrent():

    def __init__(self, torrent_file):
        self.metainfo = self.read_torrent_file(torrent_file)
        self.tracker_url = self.metainfo['announce']
        self.info = self.metainfo['info']
        self.info_hash = sha1(bencode(self.info)).digest()
        self.peer_id = self.generate_peer_id()
        self.left = self.file_length()

    def read_torrent_file(self, torrent_file):
        with open(torrent_file, 'rb') as f:
            return bdecode(f.read())

    def generate_peer_id(self):
        client_id = 'AS'
        version = '0001'
        random_numbers = ''.join(choice(digits) for i in range(12))
        return '-{}{}-{}'.format(client_id, version, random_numbers)

    def file_length(self):
        length = 0

        if 'length' in self.info:
            length = self.info['length']
        else:
            files = self.info['files']
            for file_dict in files:
                length += file_dict['length']

        return length

    def __str__(self):
        return 'info_hash: {}, peer_id: {}, left: {}'.format(
            self.info_hash, self.peer_id, self.left
            )
