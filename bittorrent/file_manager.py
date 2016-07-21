import os
import logging

class FileManager():

    def __init__(self, torrent, destination):
        self.logger = logging.getLogger('main.file_manager')
        self.torrent_info = torrent.info
        self.destination = destination

        info_dict = self.get_files_info()
        self.create_dir_file(info_dict)


    def get_files_info(self):

        if 'length' in self.torrent_info:

            length = self.torrent_info['length']
            name = self.torrent_info['name']
            mode = 'single'
            return {
                'length': length,
                'name': name,
                'mode': mode
            }

        else:
            multi_files = self.torrent_info['files']
            files = []

            for f in multi_files:
                files.append({
                    'name': f['path'][0],
                    'length': f['length'],
                    'length_written': 0,
                    'done': False
                })

            files_info = {}
            files_info['dirname'] = self.torrent_info['name']
            files_info['files'] = files
            files_info['mode'] = 'multiple'
            return files_info

    def create_dir_file(self, info_dict):

        self.files = []
        if info_dict['mode'] == 'multiple':
            file_list = info_dict['files']
            dir_path = os.path.join(
                    os.path.expanduser(self.destination), info_dict['dirname'])

            if not os.path.exists(dir_path):
                os.makedirs(dir_path)

            for f in file_list:
                file_path = os.path.join(dir_path, f['name'])
                if not os.path.exists(file_path):
                    fd = open(file_path, 'wb')
                    # fd.close()
                    self.files.append({
                        'descriptor': fd,
                        'length_to_write': f['length'],
                        'offset': 0
                    })
                else:
                    raise IOError('file already exists.')
        else:
            file_path = os.path.join(
                    os.path.expanduser(self.destination), info_dict['name'])

            if not os.path.exists(file_path):
                fd = open(file_path, 'wb')
                # fd.close()
                self.files.append({
                    'descriptor': fd,
                    'length_to_write': f['length'],
                    'offset': 0
                })
            else:
                raise IOError('file already exists.')

    def write(self, data, peer):
        for f in self.files:
            fd = f['descriptor']
            length_to_write = f['length_to_write']
            offset = f['offset']
            if length_to_write != 0:

                if length_to_write > len(data):
                    self.logger.debug('writing to {}'.format(fd.name))
                    self.logger.debug('at pos {}'.format(fd.tell()))
                    self.logger.debug('offset: {}'.format(offset))
                    self.logger.debug('length to write {}'.format(length_to_write))
                    self.logger.debug('wrote length: {}'.format(len(data)))

                    fd.seek(offset)
                    fd.write(data)
                    f['length_to_write'] -= len(data)
                    f['offset'] += len(data)
                    return
                else:
                    self.logger.debug('at pos {}'.format(fd.tell()))
                    self.logger.debug('length to write {}'.format(length_to_write))
                    self.logger.debug('offset: {}'.format(offset))
                    self.logger.debug('wrote length: {}'.format(len(data[:length_to_write])))
                    self.logger.debug('finished writing to {}'.format(fd.name))
                    self.logger.debug('remaining data length: {}'.format(len(data[length_to_write:])))

                    fd.seek(offset)
                    fd.write(data[:length_to_write])
                    fd.close()
                    f['length_to_write'] = 0
                    data = data[length_to_write:]
