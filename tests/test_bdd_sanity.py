import pytest
from pytest_bdd import scenario, given, when, then, parsers

@scenario('../features/sanity.feature', 'Basic addition')
def test_basic_addition():
    pass

@given(parsers.parse('I have a number {a:d}'), target_fixture="first_number")
def a_number(a):
    return {'a': a}

@given(parsers.parse('I have another number {b:d}'))
def another_number(first_number, b):
    first_number['b'] = b
    return first_number

@when('I add them together')
def add_numbers(first_number):
    first_number['result'] = first_number['a'] + first_number['b']
    return first_number

@then(parsers.parse('the result should be {c:d}'))
def result_should_be(first_number, c):
    assert first_number['result'] == c
