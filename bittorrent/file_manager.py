import os
import logging

class FileManager():

    def __init__(self, torrent, destination):
        self.logger = logging.getLogger('main.file_manager')
        self.torrent = torrent
        self.destination = destination
        info_dict = self.get_files_info()
        self.create_dir_file(info_dict)


    def get_files_info(self):

        if 'length' in self.torrent.info:

            length = self.torrent.info['length']
            name = self.torrent.info['name']
            mode = 'single'
            return {
                'length': length,
                'name': name,
                'mode': mode
            }

        else:
            multi_files = self.torrent.info['files']
            files = []

            for f in multi_files:
                files.append({
                    'name': f['path'][0],
                    'length': f['length'],
                    'length_written': 0,
                })

            files_info = {}
            files_info['dirname'] = self.torrent.info['name']
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

            tmp_file_path = os.path.join(dir_path, 'tmp.tmp')
            self.tmp_file_path = tmp_file_path
            if not os.path.isfile(tmp_file_path):
                self.tmp_file = open(tmp_file_path, 'wb')
                self.tmp_file.close()

            self.tmp_file = open(tmp_file_path, 'r+b')
            self.tmp_file.truncate()
            self.tmp_file_length = 0

            for f in file_list:
                file_path = os.path.join(dir_path, f['name'])

                if os.path.isfile(file_path):
                    os.remove(file_path)

                fd = open(file_path, 'wb')
                # fd.close()
                self.files.append({
                    'descriptor': fd,
                    'length_to_write': f['length'],
                })
        else:
            file_path = os.path.join(
                    os.path.expanduser(self.destination), info_dict['name'])

            if os.path.isfile(file_path):
                os.remove(file_path)
                fd = open(file_path, 'wb')
                # fd.close()
                self.files.append({
                    'descriptor': fd,
                    'length_to_write': f['length'],
                })
            else:
                raise IOError('file already exists.')

    def write(self, piece_index, data):
        """
        because pieces dont come in in order,
        we need to put pieces in order in a temporary file first.
        once we have all the pieces in order in the temporary file,
        write to actual files in order
        """

        offset = piece_index * len(data)
        self.tmp_file.seek(offset)
        self.tmp_file.write(data)
        self.tmp_file_length += len(data)
        # self.tmp_file_length = os.path.getsize(self.tmp_file_path)
        total_file_length = self.torrent.file_length()
        self.logger.debug('writing to tmp file: {}, total length: {}'.format(os.path.getsize(self.tmp_file_path), total_file_length))
        if self.tmp_file_length == total_file_length:
            # close tmp file for writing
            self.tmp_file.close()
            # open for reading
            with open(self.tmp_file_path, 'r+b') as fd:
                content = fd.read()
                self.logger.debug(len(content))
                self.write_to_file(content)

    def write_to_file(self, content):

        self.logger.debug('start writing to actual files')
        for f in self.files:
            fd = f['descriptor']
            length_to_write = f['length_to_write']
            fd.seek(0)
            fd.write(content[:length_to_write])
            content = content[length_to_write:]

            self.logger.debug('at pos {}'.format(fd.tell()))
            self.logger.debug('length to write {}'.format(length_to_write))
            self.logger.debug('wrote length: {}'.format(len(content[:length_to_write])))
            self.logger.debug('finished writing to {}'.format(fd.name))
            self.logger.debug('remaining content length: {}'.format(len(content[length_to_write:])))

            fd.close()
