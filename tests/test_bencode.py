import unittest
import bencode as b

class TestDecodeInt(unittest.TestCase):

    def test_single_int(self):
        self.assertEqual(2, b.decode_int(b'i2e'))

    def test_exception_on_leading_zero(self):
        with self.assertRaises(b.BencodeError) as context:
            b.decode_int(b'i023e')
        self.assertEqual('leading zero is not allowed', context.exception.message)

    def test_zero(self):
        self.assertEqual(0, b.decode_int(b'i0e'))

    def test_negative_int(self):
        self.assertEqual(-23, b.decode_int(b'i-23e'))

    def test_excepiton_on_negative_zero(self):
        with self.assertRaises(b.BencodeError) as context:
            b.decode_int(b'i-0e')


class TestDecodeStr(unittest.TestCase):

    def test_single_char(self):
        self.assertEqual('a', b.decode_str( '1:a'))

    def test_long_string(self):
        self.assertEqual('dweirieakddewqw', b.decode_str( '15:dweirieakddewqw'))

    def test_str_len(self):
        self.assertEqual('hello', b.decode_str('5:helloworld'))

    def test_exception_on_wrong_datatype(self):
        with self.assertRaises(b.BencodeError) as context:
            b.decode_str('i23e')


class TestDecodeList(unittest.TestCase):

    def test_one_dimentional_list(self):
        exp = 'l4:spam4:eggsi23ee'
        lst = ['spam', 'eggs', 23]
        self.assertEqual(b.decode_list(exp), lst)

    def test_multi_dimentional_list(self):
        exp = 'l4:spamli4e4:eggsi-23ee5:helloe'
        lst = ['spam', [4, 'eggs', -23], 'hello']
        self.assertEqual(lst, b.decode_list(exp))


class TestDecodeDict(unittest.TestCase):

    def test_reg_dict(self):
        exp = 'd3:cow3:moo4:spam4:eggse'
        d =  {'cow': 'moo', 'spam': 'eggs'}
        self.assertEqual(d, b.decode_dict(exp))

    def test_nested_dict(self):
        exp = 'd4:spaml1:a1:bee'
        d = {'spam': ['a', 'b']}
        exp1 = 'd4:spaml1:a1:be4:testd4:eggs3:moo5:helloi4eee'
        d1 = {'spam': ['a', 'b'], 'test': {'eggs': 'moo', 'hello': 4}}
        self.assertEqual(d, b.decode(exp))
        self.assertEqual(d1, b.decode(exp1))

class TestUtils(unittest.TestCase):

    def test_expression_length_on_int(self):
        self.assertEqual(5, b.expression_length('i-23e4:spam'))

    def test_expression_length_on_str(self):
        self.assertEqual(6, b.expression_length('4:spam'))

    def test_itemizing_to_list(self):
        exp1 = '4:spam3:eggi34e'
        lst1 = ['4:spam', '3:egg', 'i34e']
        exp2 = 'i-23ei4el4:spam4:eggsi8ee5:hello'
        lst2 = ['i-23e', 'i4e', 'l4:spam4:eggsi8ee', '5:hello']
        self.assertEqual(lst1, b.itemize(exp1))
        self.assertEqual(lst2, b.itemize(exp2))

if __name__ == '__main__':
    unittest.main()
