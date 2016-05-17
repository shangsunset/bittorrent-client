class BencodeError(Exception):
    def __init__(self, mode, message, data):
        assert mode in ["encode", "decode"]

        self.mode = mode
        self.message = message
        self.data = data

    def __str__(self):
        return repr('{}Error: {}, {}'.format(self.mode.capitalize(), self.message, self.data))


def verify_type(data, bencoding_type, mode):
    try:
        assert bencoding_type == bencode_type(data, mode)
    except AssertionError:
        raise BencodeError(mode, 'incorrent data type provided', data)


def bencode_type(data, mode='decode'):
    """ given bencoded data, return what type it is"""

    print(data)
    if mode == 'decode':
        if data[0] == 'i':
            return 'int'
        elif data[0].isdigit():
            return 'str'
        elif data[0] == 'l':
            return 'list'
        elif data[0] == 'd':
            return 'dict'
    elif mode == 'encode':
        if isinstance(data, int):
            return 'int'
        elif isinstance(data, str):
            return 'str'
        elif isinstance(data, list):
            return 'list'
        elif isinstance(data, dict):
            return 'dict'

def decode_int(data):
    """ given a bencoded string of integer, returns an integer """

    verify_type(data, 'int', 'decode')
    # check if the data ends with e
    try:
        end = data.index('e')
    except ValueError:
        raise BencodeError('decode', 'can not find \'e\' in the end of expression', data)

    # get the substring we need, between i and e
    num = data[1:end]

    # leading zero is not allowed
    if len(num) > 1 and num[0] == '0':
        raise BencodeError('decode', 'leading zero is not allowed', data)

    # negative zero is not allowed
    if num.startswith('-0'):
        raise BencodeError('decode', 'negative zero is not allowed', data)

    return int(num)

def encode_int(num):
    """ given a integer, returns a bencoded expression """

    verify_type(num, 'int', 'encode')
    return 'i{}e'.format(str(num))

def decode_str(data):
    """ given a bencoded string, returns the real string """

    verify_type(data, 'str', 'decode')
    colon_pos = data.index(':')
    strlen = int(data[:colon_pos])
    s = data[colon_pos + 1: colon_pos + strlen + 1]
    return s

def encode_str(data):
    """ given a string, returns bencoded string """

    verify_type(data, 'str', 'encode')
    return '{}:{}'.format(len(data), data)

def decode_list(data):
    """ given a bencoded list, returns a list object """

    verify_type(data, 'list', 'decode')
    try:
        assert data[-1] == 'e'
    except ValueError:
        raise BencodeError('decode', 'can not find \'e\' in the end of expression', data)

    data = data[1:-1]
    items = itemize(data)
    return [decode(item) for item in items]

def decode_dict(data):
    """ given a bencoded dict, returtn a dict object """

    verify_type(data, 'dict', 'decode')
    try:
        assert data[-1] == 'e'
    except ValueError:
        raise BencodeError('decode', 'can not find \'e\' in the end of expression', data)

    data = data[1:-1]
    items = itemize(data)
    temp = {}
    for index in range(0, len(items), 2):
        temp[decode(items[index])] = decode(items[index + 1])

    return temp

def scan(data, index=1):

    if data[index] == 'i' or data[index].isdigit():
        return scan(data, index + expression_length(data[index:]))
    elif data[index] == 'l' or data[index] == 'd':
        sub_end = scan(data[index:])
        return scan(data, sub_end + index)
    elif data[index] == 'e':
        return index
    else:
        raise BencodeError('decode', 'bencoded list is invalid', data)

def itemize(data):

    if len(data) == 0:
        return []
    # check bencode type of leading expression
    ben_type = bencode_type(data)
    if ben_type is None:
        print('torrent file is invalid')
    if ben_type == 'int' or ben_type == 'str':
        element = data[:expression_length(data)]
        rest = itemize(data[expression_length(data):])
    elif ben_type == 'list' or ben_type == 'dict':
        end = scan(data)
        element = data[:end + 1]
        rest = itemize(data[end + 1:])

    return [element] + rest

def expression_length(exp):
    datatype = bencode_type(exp)

    if datatype == 'int':
        e = exp.index('e')
        # num length + (i and e)
        length = e - 1 + 2
    elif datatype == 'str':
        colon = exp.index(':')
        num = exp[:colon]
        num_len = colon
        # num length + colon + num
        length = num_len + 1 + int(num)
    else:
        raise BencodeError('decode', 'can not recognize the data type provided', exp)

    return length

decode_functions = {
    'int': decode_int,
    'str': decode_str,
    'dict': decode_dict,
    'list': decode_list
}

def decode(data):
    return decode_functions[bencode_type(data)](data)
