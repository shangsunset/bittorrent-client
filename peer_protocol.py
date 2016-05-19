import asyncio

class PeerProtocol(asyncio.Protocol):

    def connection_made(self, transport):
        host, port = transport.get_extra_info('peername')
        print('connected with {}:{}'.format(host, port))

    def connection_lost(self, exc):
        print('disconnected...')
        print('exc: {}'.format(exc))
