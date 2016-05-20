import asyncio
import struct

class PeerProtocol(asyncio.Protocol):

    def __init__(self, torrent):
        self.torrent = torrent

    def connection_made(self, transport):
        host, port = transport.get_extra_info('peername')
        print('connected with {}:{}'.format(host, port))
        transport.write(self.hand_shake())
        self.transport = transport

    def data_received(self, data):
        print('Data received: {}'.format(data))

    def error_received(self, exc):
        print('Error received:', exc)

    def connection_lost(self, exc):
        print('disconnected...')
        print('exc: {}'.format(exc))

    def hand_shake(self):
        """ https://wiki.theory.org/BitTorrentSpecification#Handshake """

        pstrlen = 19
        pstr = 'BitTorrent protocol'
        reserved = bytes(8)

        return b''.join([
            struct.pack('>I', pstrlen),
            bytes(pstr, encoding='utf-8'),
            reserved,
            self.torrent.info_hash,
            bytes(self.torrent.peer_id, encoding='utf-8')
        ])
