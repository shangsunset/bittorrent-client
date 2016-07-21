import os

class FileManager():

    def __init__(self, torrent, destination):
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

        self.file_descriptors = []
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
                    fd.close()
                    self.file_descriptors.append(fd)
        else:
            file_path = os.path.join(
                    os.path.expanduser(self.destination), info_dict['name'])

            if not os.path.exists(file_path):
                fd = open(file_path, 'wb')
                fd.close()
                self.file_descriptors.append(fd)
            else:
                raise IOError('file already exists.')

    def write(self, piece, peer):

        if self.info_dict['mode'] == 'single':
            self.write_single_file(piece, peer)
        else:
            self.write_multi_files(piece, peer)

    def write_single_file(self, name):
        pass

    def write_multi_files(self, payload, peer):
        for fd in self.file_descriptors:
            pass

    # def write_multi_files(self, payload, peer):
    #     for index, f in enumerate(self.file_list):
    #         if not f['done']:
    #             if f['length'] < len(payload):
    #                 with open(os.path.join(self.dest_path, f['name']), 'wb') as new_file:
    #                     little_chunk = payload[:f['length']]
    #                     new_file.seek(f['length_written'])
    #                     new_file.write(little_chunk)
    #                     f['length_written'] = len(little_chunk)
    #                 with open(os.path.join(self.dest_path, files[index+1]['name']), 'ab') as next_file:
    #                     remaining_chunk = payload[f['length']:]
    #                     next_file.seek(files[index+1]['length_written'])
    #                     next_file.write(remaining_chunk)
    #                     files[index+1]['length_written'] = len(remaining_chunk)
    #
    #             elif f['length'] - f['length_written'] < len(payload):
    #                 with open(os.path.join(self.dest_path, f['name']), 'wb') as new_file:
    #                     last_chunk = payload[:f['length'] - f['length_written']]
    #                     new_file.seek(f['length_written'])
    #                     new_file.write(last_chunk)
    #                     f['length_written'] += len(last_chunk)
    #                     self.logger.debug('wrote last chunk to file')
    #                 with open(os.path.join(self.dest_path, files[index+1]['name']), 'ab') as next_file:
    #                     remaining_chunk = payload[f['length'] - f['length_written']:]
    #                     next_file.seek(files[index+1]['length_written'])
    #                     next_file.write(remaining_chunk)
    #                     files[index+1]['length_written'] = len(remaining_chunk)
    #
    #             else:
    #                 with open(os.path.join(self.dest_path, f['name']), 'wb') as new_file:
    #                     new_file.seek(f['length_written'])
    #                     new_file.write(payload)
    #                     f['length_written'] += len(payload)
    #
    #             self.logger.info('file: {}, file length: {}, length written {}'.format(f['name'], f['length'], f['length_written'], peer.address['host']))
    #             if f['length'] == f['length_written']:
    #                 self.logger.info('finished file {}'.format(f['name']))
    #                 f['done'] = True
    #             break
