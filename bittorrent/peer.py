import asyncio
import struct
import logging

KEEPALIVE = bytes([0, 0, 0, 0])
CHOKE = bytes([0, 0, 0, 1]) + bytes([0])
UNCHOKE = bytes([0, 0, 0, 1]) + bytes([1])
INTERESTED = bytes([0, 0, 0, 1]) + bytes([2])
NOT_INTERESTED = bytes([0, 0, 0, 1]) + bytes([3])

class PeerProtocol(asyncio.Protocol):

    def __init__(self, torrent):
        self.torrent = torrent
        self.logger = logging.getLogger('main.peer_protocol')
        self.data = bytes()

    def connection_made(self, transport):
        # a tuple containing (host, port)
        self.peer = transport.get_extra_info('peername')
        self.logger.info('connected with {}'.format(self.peer))
        transport.write(self._hand_shake())
        self.transport = transport

    def data_received(self, data):
        """
        info hash looks something like:
        b'\x13BitTorrent protocol\x00\x00\x00\x00\x00\x00
        \x00\x00#\xb0\x93\x9ez\xc8\xb9\xb0\x1c\xda\xf0\x1f
        \x98\x8b\x9f\xfb\xbeD\xdd\xe2-AS0001-059505862275'
        """

        # existing message buffer
        # if self.data:
            # self.logger.info('existing buffer from {}: {}'.format(self.peer, self.data))
            # self.data += data
            # self.logger.info('conactenated buffer from {}: {}'.format(self.peer, self.data))
        # else:
        #     self.data = data
            # self.logger.info('new buffer from {}: {}'.format(self.peer, self.data))

        if data[1:20].lower() == b'bittorrent protocol':
            # info hash is 20 bytes long
            received_info_hash = data[28:48]
            if received_info_hash != self.torrent.info_hash:
                self._close_connection()
            else:
                data = data[68:]
                self.logger.info('Sending INTERESTED message to Peer {}'.format(self.peer))
                self.transport.write(INTERESTED)

        self._process_data(data)

    def connection_lost(self, exc):
        self.logger.info('disconnected...from {}'.format(self.peer))
        if exc is not None:
            self.logger.error('exc: {}'.format(exc))

    def _process_data(self, data):
        if self.data:
            self.data += data
        else:
            self.data = data

        # self.logger.info(self.data)
        while len(self.data) > 0:
            offset = 0
            message_length = struct.unpack(
                    '!i', self.data[0:4])[0]

            offset += 4
            # self.logger.info('from Peer {}, message length {}, {}'.format(self.peer, message_length, self.data))
            if len(self.data) - offset < message_length:
                self.logger.info('need more data, message length: {}, data length: {}'.format(message_length, len(self.data)))
                self.logger.info('data: {}'.format(self.data))
                return
            elif message_length == 0:
                self.logger.debug('Peer {} sent KEEP ALIVE message'.format(self.peer))
                return
            else:
                self.logger.info('enough data collected, message length: {}, data length: {}'.format(message_length, len(self.data)))
                self.logger.info('data: {}'.format(self.data))
                message_id = self.data[offset]
                payload = self.data[offset+1:message_length+1] if message_length > 1 else NULL

                self._parse_message(message_id, payload)

                offset += message_length
                self.data = self.data[offset:]
                self.logger.info('overflew data: {}, length: {}'.format(self.data[offset:], len(self.data[offset:])))

                # self.logger.info(
                #         'data received from Peer {}, message id: {}, data length: {}, message length: {}'.format(
                #         self.peer, message_id, len(self.data), message_length))
                # self._parse_message(message_id)

            # elif message_length == 0:
            #     self.logger.debug('Peer {} sent KEEP ALIVE message'.format(self.peer))
            # else:
            #     # not enough data received
            #     self.logger.debug('not enough data from Peer {}, message length: {}, data length: {}'.format(self.peer, message_length, len(self.data)))
            #     return

    def _parse_message(self, message_id):
        if message_id == 0:
            self.logger.debug('Peer {} sent CHOKE message'.format(self.peer))
        elif message_id == 1:
            self.logger.debug('Peer {} sent UNCHOKE message'.format(self.peer))
        elif message_id == 2:
            self.logger.debug('Peer {} sent INTERESTED message'.format(self.peer))
        elif message_id == 3:
            self.logger.debug('Peer {} sent NOT INTERESTED message'.format(self.peer))
        elif message_id == 4:
            self.logger.debug('Peer {} sent HAVE message'.format(self.peer))
        elif message_id == 5:
            self.logger.debug('Peer {} sent BITFIELD message'.format(self.peer))
        elif message_id == 6:
            self.logger.debug('Peer {} sent REQUEST message'.format(self.peer))
        elif message_id == 7:
            self.logger.debug('Peer {} sent PIECE message'.format(self.peer))
        elif message_id == 8:
            self.logger.debug('Peer {} sent CANCEL message'.format(self.peer))

    def _close_connection(self):
        self.transport.close()

    def _hand_shake(self):
        """ https://wiki.theory.org/BitTorrentSpecification#Handshake """

        pstrlen = 19
        pstr = 'BitTorrent protocol'
        reserved = bytes(8)

        # return a long byte string
        return b''.join([
            bytes([pstrlen]),
            bytes(pstr, encoding='utf-8'),
            reserved,
            self.torrent.info_hash,
            bytes(self.torrent.peer_id, encoding='utf-8')
        ])
