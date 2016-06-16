import logging
import asyncio

from client import TorrentClient

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

def done(future):
    logger.info(future.result())
    # loop.stop()

def main():
    filename = '../street-fighter.torrent'
    client = TorrentClient(filename, loop)

    asyncio.ensure_future(client.connect_to_peers(future))
    # asyncio.ensure_future(client.keep_alive(future))
    future.add_done_callback(done)

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    future = asyncio.Future()

    main()
