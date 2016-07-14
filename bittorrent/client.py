import struct
import sys
import os
import asyncio
import time
from hashlib import sha1
import socket
import logging
import datetime

import requests
from bcoding import bdecode

from torrent import Torrent
from peer import Peer, PeerProtocol
from utils import Pieces

KEEPALIVE = bytes([0, 0, 0, 0])
CHOKE = bytes([0, 0, 0, 1]) + bytes([0])
UNCHOKE = bytes([0, 0, 0, 1]) + bytes([1])
INTERESTED = bytes([0, 0, 0, 1]) + bytes([2])
NOT_INTERESTED = bytes([0, 0, 0, 1]) + bytes([3])


class TorrentClient():

    def __init__(self, torrent_file, download_destination, loop):
        self.logger = logging.getLogger('main.torrent_client')
        self.loop = loop
        self.torrent = Torrent(torrent_file)
        self.download_destination = download_destination
        self.files_info = self.torrent.get_files_info()
        self.dest_path = self.create_dir(self.files_info)
        self.pieces = Pieces(self.torrent) # save downloaded pieces
        self.pieces_downloaded = [] # keep track blocks that are requested
        self.peers = self._discover_peers()
        self.active_peers = []

    def _discover_peers(self):
        """
        get peers connected to the torrent.
        peers from the tracker response is bencoded raw binary data,
        this method parses the raw binary data and returns a list of peers
        """
        tracker_response = self._connect_to_tracker()
        if 'failure reason' not in tracker_response:
            peers = self._decode_peers(tracker_response['peers'])
            return peers
        else:
            time.sleep(tracker_response['interval'])

    def _decode_peers(self, bin_peers):
        """
        The first 4 bytes contain the 32-bit ipv4 address.
        The remaining two bytes contain the port number.
        Both address and port use network-byte order.
        """
        offset = 0
        peers = []
        # Length of bin_peers should be multiple of 6
        while offset != len(bin_peers):
            bin_ip = struct.unpack_from('!i', bin_peers, offset)[0]
            host = socket.inet_ntoa(struct.pack('!i', bin_ip))
            offset += 4
            port = struct.unpack_from('!H', bin_peers, offset)[0]
            offset += 2
            peer = Peer(host, port, self.torrent)
            # peer = {'host': host, 'port': port}
            peers.append(peer)

        return peers

    def _connect_to_tracker(self):
        """
        https://wiki.theory.org/BitTorrentSpecification#Tracker_Request_Parameters
        make a request to tracker which is an HTTP(S) service
        that holds information about the torrent and peers.
        """

        keys = {
            'info_hash': self.torrent.info_hash,
            'peer_id': self.torrent.peer_id,
            'left': self.torrent.left,
            'downloaded': 0,
            'uploaded': 0,
            'port': 6881,
            'compact': 1,
            'event': 'started'
        }

        r = requests.get(self.torrent.tracker_url, params=keys)
        response = bdecode(r.content)
        return response

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

    async def connect_to_peers(self):
        await asyncio.gather(
                *[self._connect_to_peer(peer) for peer in self.peers],
                )

    async def keep_alive(self):
        await asyncio.gather(
                *[self._send_keepalive_to_peer(peer) for peer in self.peers],
                )

    async def _send_keepalive_to_peer(self, peer):
        while True:
            await asyncio.sleep(90)
            if peer in self.active_peers:
                if not peer.writer.transport.is_closing():
                    try:
                        peer.writer.write(KEEPALIVE)
                        peer.writer.drain()
                        self.logger.info('just sent keep alive message to {}'.format(peer.address))
                    except Exception as e:
                        self.logger.error('keep live: {}'.format(e))
                else:
                    self.logger.debug('transport is closing or closed for {}'.format(peer.address))
                    self.logger.info('peer removed')
                    self._close_connection(peer)

    async def _connect_to_peer(self, peer):

        try:
            reader, writer = await asyncio.open_connection(
                    peer.address['host'], peer.address['port'])

            peer.reader = reader
            peer.writer = writer

            await self._connection_handler(peer)
            await self._receive_data(peer)
        except (ConnectionRefusedError,
                ConnectionResetError,
                ConnectionAbortedError,
                TimeoutError, OSError) as e:
            self.logger.error('{}, {}'.format(e, peer.address))

    async def _connection_handler(self, peer):
        self.logger.info('connected with peer {}'.format(peer.address))
        self.active_peers.append(peer)
        self.timer = datetime.datetime.now()
        try:
            peer.writer.write(self._hand_shake())
            await peer.writer.drain()
        except (IOError, Exception) as e:
            self.logger.error('hand shake: {}'.format(e))

        hand_shake_msg = b''
        while len(hand_shake_msg) < 68:
        # 68 is the length of hand shake message
            try:
                chunk = await peer.reader.read(68)
                hand_shake_msg += chunk
                if not chunk:
                    break
                info_hash = hand_shake_msg[28:48]
                if self.torrent.info_hash != info_hash:
                    self.logger.info('read hand shake refused')
                    self._close_connection(peer)
                else:
                    peer.writer.write(INTERESTED)
                    await peer.writer.drain()
                    self.logger.info('Sent INTERESTED message to Peer {}'.format(peer.address))
            except (ConnectionRefusedError, TimeoutError, Exception) as e:
                self.logger.info(e)
                break

    async def _receive_data(self, peer):
        while True:
            message_body = b''
            first_4_bytes = b''
            while len(first_4_bytes) < 4:
                try:
                    chunk = await peer.reader.read(4 - len(first_4_bytes))
                except Exception as e:
                    self.logger.error('read from peer Exception')
                    self.logger.error(e)
                    return

                if not chunk:
                    return
                first_4_bytes += chunk

            message_length = struct.unpack('!i', first_4_bytes)[0]

            if message_length == 0:
                peer.timer = datetime.datetime.now()
                self.logger.debug('Peer {} sent KEEP ALIVE message'.format(peer.address))
            else:
                while len(message_body) < message_length:
                    try:
                        message_body_chunk = await peer.reader.read(message_length - len(message_body))
                    except Exception as e:
                        self.logger.info('read message body')
                        self.logger.error(e)
                        return
                    if not message_body_chunk:
                        return
                    message_body += message_body_chunk

                message_id = message_body[0]
                payload = message_body[1:]
                await self._message_handler(peer, message_id, payload)

    async def _message_handler(self, peer, msg_id, payload):
        """ identity type of message sent from peer and make action accordingly """

        if msg_id == 0:
            self.logger.debug('Peer {} sent CHOKE message'.format(peer.address))

        elif msg_id == 1:
            self.logger.debug('Peer {} sent UNCHOKE message'.format(peer.address))
            peer.choked = False
            await self._request_piece(peer)

        elif msg_id == 2:
            self.logger.debug('Peer {} sent INTERESTED message'.format(peer.address))

        elif msg_id == 3:
            self.logger.debug('Peer {} sent NOT INTERESTED message'.format(peer.address))

        elif msg_id == 4:
            # peer tells what other pieces it has
            # we need to update our record
            self.logger.debug('Peer {} sent HAVE message'.format(peer.address))
            index = struct.unpack('!i', payload)[0]
            no_pieces = len(peer.queue) == 0
            peer.queue.add(index)
            if no_pieces:
                await self._request_piece(peer)

        elif msg_id == 5:
            # message payload is what pieces the peer has, labeled by indexes
            # we need to keep a record of what the peer has
            self.logger.debug('Peer {} sent BITFIELD message'.format(peer.address))
            no_pieces = len(peer.queue) == 0
            # peer.pieces = BitArray(payload)
            b = bytearray(payload)
            bitstring = ''.join([bin(x)[2:] for x in b])
            pieces_indexes = [i for i, x in enumerate(bitstring) if x == '1']
            for index in pieces_indexes:
                peer.queue.add(index)

            if no_pieces:
                await self._request_piece(peer)

        elif msg_id == 6:
            self.logger.debug('Peer {} sent REQUEST message'.format(peer.address))

        elif msg_id == 7:
            # self.logger.debug('Peer {} sent PIECE message'.format(peer.address))
            await self._handle_piece_msg(payload, peer)

        elif msg_id == 8:
            self.logger.debug('Peer {} sent CANCEL message'.format(peer.address))

    def _request_message(self, block):
        message_id = b'\x06'
        message_length = bytes([0, 0, 0, 13])
        piece_length = self.torrent.info['piece length']
        request_length = self.torrent.REQUEST_LENGTH

        # total_file_length = 0
        # begin_offset = 0
        # while begin_offset < piece_length and \
        #     total_file_length < self.torrent.file_length():

        msg = b''.join([
            message_length,
            message_id,
            struct.pack('!i', block['index']),
            struct.pack('!i', block['begin_offset']),
            struct.pack('!i', block['request_length'])
            ])
        # total_file_length += request_length

        return msg

    async def _request_piece(self, peer):

        if not peer.choked:
            while len(peer.queue) > 0:
                self.logger.info('{} blocks left to request from {}'.format(len(peer.queue.queue), peer.address['host']))
                block = peer.queue.pop()
                if self.pieces.needed(block):
                    peer.writer.write(self._request_message(block))
                    await peer.writer.drain()
                    self.pieces.add_requested(block)
                    self.logger.info('requested {} from {}'.format(block, peer.address['host']))
                    break
                else:
                    self.logger.info('index {} not needed'.format(block['index']))

    async def _handle_piece_msg(self, message_payload, peer):
        """ save blocks sent from peer """

        index = struct.unpack('!i', message_payload[:4])[0]
        begin_offset = struct.unpack('!i', message_payload[4:8])[0]
        payload = message_payload[8:]
        block = {
            'index': index,
            'begin_offset': begin_offset,
            'request_length': len(payload),
            'payload': payload
        }

        self.logger.info('block from {}, {}, {}'.format(peer.address, block['index'], block['begin_offset']))
        # self.logger.info(self.torrent.piece_hash_list[index])
        # self.logger.info(sha1(payload).digest())
        # if self.torrent.piece_hash_list[index] == sha1(payload).digest():
        piece_index, piece = self.pieces.add_received(block)

        if piece is not None:
            # self.logger.info('returned piece {}'.format(piece_index))
            # self.logger.info(self.torrent.piece_hash_list[piece_index])
            # self.logger.info(sha1(piece).digest())
            # if sha1(piece).digest() in self.torrent.piece_hash_list:
            #     self.logger.info('found one')
            if self.torrent.piece_hash_list[piece_index] == sha1(piece).digest():
                self.pieces_downloaded.append(piece_index)

                # self.write_data(piece, peer)
                self.logger.info('downloaded: {}, total: {}'.format(len(self.pieces_downloaded), self.torrent.number_of_pieces))
                # self.logger.info('percentage {:.2f}%'.format((len(self.pieces_downloaded) * 100) / self.torrent.number_of_pieces))
            else:
                self.logger.debug('discarding piece {} ***********************'.format(piece_index))
                self.pieces.discard_piece(piece_index)
                for p in self.active_peers:
                    p.queue.add(piece_index)

                # asyncio.ensure_future(
                #     await asyncio.gather(
                #             *[peer.queue.add(piece_index) for peer in self.active_peers],
                #         )
                #     )
                # self.logger.info('queue ajusted {}'.format(peer.address['host']))
            # self.logger.info('queue: {}'.format(peer.queue.queue))


        await self._request_piece(peer)

    def write_data(self, piece, peer):

        if 'length' in self.torrent.info:
            name = self.torrent.info['name']
        else:
            self.write_multi_files(piece, peer)

    def write_single_file(self, name):
        pass

    def create_dir(self, files_info):
        dirname = files_info['dirname']
        files = files_info['files']
        dest_path = os.path.join(
                os.path.expanduser(self.download_destination), dirname)
        if not os.path.exists(dest_path):
            os.makedirs(dest_path)

        return dest_path

    def write_multi_files(self, payload, peer):
        files = self.files_info['files']
        for index, f in enumerate(files):
            if not f['done']:
                if f['length'] < len(payload):
                    with open(os.path.join(self.dest_path, f['name']), 'wb') as new_file:
                        little_chunk = payload[:f['length']]
                        new_file.seek(f['length_written'])
                        new_file.write(little_chunk)
                        f['length_written'] = len(little_chunk)
                    with open(os.path.join(self.dest_path, files[index+1]['name']), 'ab') as next_file:
                        remaining_chunk = payload[f['length']:]
                        next_file.seek(files[index+1]['length_written'])
                        next_file.write(remaining_chunk)
                        files[index+1]['length_written'] = len(remaining_chunk)

                elif f['length'] - f['length_written'] < len(payload):
                    with open(os.path.join(self.dest_path, f['name']), 'wb') as new_file:
                        last_chunk = payload[:f['length'] - f['length_written']]
                        new_file.seek(f['length_written'])
                        new_file.write(last_chunk)
                        f['length_written'] += len(last_chunk)
                        self.logger.debug('wrote last chunk to file')
                    with open(os.path.join(self.dest_path, files[index+1]['name']), 'ab') as next_file:
                        remaining_chunk = payload[f['length'] - f['length_written']:]
                        next_file.seek(files[index+1]['length_written'])
                        next_file.write(remaining_chunk)
                        files[index+1]['length_written'] = len(remaining_chunk)

                else:
                    with open(os.path.join(self.dest_path, f['name']), 'wb') as new_file:
                        new_file.seek(f['length_written'])
                        new_file.write(payload)
                        f['length_written'] += len(payload)

                self.logger.info('file: {}, file length: {}, length written {}'.format(f['name'], f['length'], f['length_written'], peer.address['host']))
                if f['length'] == f['length_written']:
                    self.logger.info('finished file {}'.format(f['name']))
                    f['done'] = True
                break

    def _close_connection(self, peer):
        self.active_peers.remove(peer)
        peer.writer.close()
