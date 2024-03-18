from mint.tools.map_tricks import delete_keys_from_dict
from mint.tools.map_tricks import find_dict_in_list

#
# Test for find_dict_in_list function.
#
def test_find_dict_in_list():
    """
    Test that the function finds the dictionaries in the list.
    """

    # Given
    list_of_dicts = [({ 'a': 1, 'b': 2}), {'c': 3, 'd': 4}, (3, 4)]

    # When
    result = find_dict_in_list(list_of_dicts)

    # Then
    assert list(result) == [{'a': 1, 'b': 2}, {'c': 3, 'd': 4}]

#
# Test for delete_keys_from_dict function.
#
def test_delete_keys_from_dict():
    """
    Test that the function deletes the keys from the dictionary.
    """

    # Given
    dictionary = {
        'a': 1,
        'b': 2
    }
    keys = ['a']

    # When
    delete_keys_from_dict(dictionary, keys)

    # Then
    assert dictionary == {'b': 2}


def test_delete_keys_from_dict_empty_dict():
    """
    Test that the function does not raise an error when the dictionary is empty.
    """
    # Given
    dictionary = {}
    keys = ['a']

    # When
    delete_keys_from_dict(dictionary, keys)

    # Then
    assert dictionary == {}


def test_delete_keys_from_dict_key_not_in_dict():
    """

    """
    # Given
    dictionary = {
        'a': 1,
        'b': 2
    }
    keys = ['c']

    # When
    delete_keys_from_dict(dictionary, keys)

    # Then
    assert dictionary == {'a': 1, 'b': 2}

def test_delete_keys_from_dict_with_lists():
    """
    Test that the function deletes the keys from the list object.
    """
    # Given
    dictionary = {
        'a': 1,
        'b': [{'c': 3, 'd': 4}, {'e': 5, 'f': 6}]
    }
    keys = ['c', 'e']

    # When
    delete_keys_from_dict(dictionary, keys)

    # Then
    assert dictionary == {'a': 1, 'b': [{'d': 4}, {'f': 6}]}


from collections.abc import MutableMapping

def test_delete_keys_from_dict_with_mutable_mapping():
    """
    Test that the function deletes the keys from the MutableMapping object.
    """
    # Given: We define a dictionary that contains a MutableMapping object.
    dictionary = {
        'a': 1,
        'b': {'c': 3, 'd': 4}
    }
    # We also define the keys that we want to delete from the MutableMapping object.
    keys = ['c']

    # When: We call the delete_keys_from_dict function with the dictionary and keys as arguments.
    delete_keys_from_dict(dictionary, keys)

    # Then: We assert that the function has correctly deleted the key 'c' from the MutableMapping object.
    # The expected result is the original dictionary, but with the key 'c' removed from the MutableMapping object.
    assert dictionary == {'a': 1, 'b': {'d': 4}}