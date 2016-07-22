import logging
import asyncio

from bittorrent.client import TorrentClient

logger = logging.getLogger('main')
logger.setLevel(logging.DEBUG)

# create console handler with a higher log level
fh = logging.FileHandler('bittorrent.log')
ch = logging.StreamHandler()
# create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
ch.setFormatter(formatter)
# add the handlers to the logger
logger.addHandler(fh)
logger.addHandler(ch)

def main():
    filename = 'beats.torrent'
    dest = '~/Desktop'
    client = TorrentClient(filename, dest, loop)

    asyncio.ensure_future(client.connect_to_peers())
    asyncio.ensure_future(client.keep_alive())

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    main()
