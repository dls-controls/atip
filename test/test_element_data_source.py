import mock
import atip
import at
import pytac
import pytest
from atip.sim_data_source import ATElementDataSource


@pytest.mark.parametrize('func_str,field,cell',
                         [('ateds._KickAngle', 'x_kick', 0),
                          ('ateds._KickAngle', 'y_kick', 1),
                          ('ateds._PolynomA', 'a1', 1),
                          ('ateds._PolynomB', 'b0', 0),
                          ('ateds._PolynomB', 'b1', 1),
                          ('ateds._PolynomB', 'b2', 2),
                          ('ateds._Orbit', 'x', 0), ('ateds._Orbit', 'y', 2),
                          ('ateds._Frequency', 'f', None)])
def test_elem_field_funcs(at_elem, func_str, field, cell):
    ateds = ATElementDataSource(at_elem, mock.Mock(), [field])
    ff = ateds._field_funcs
    if cell is not None:
        assert ff[field].func == eval(func_str)
        assert ff[field].args[0] == cell
    else:
        assert ff[field] == eval(func_str)


@pytest.mark.parametrize('fields', ['a1', ['x_kick', 'y_kick'], 'r', 1, [],
                                    ['r', 0]])
def test_elem_get_fields(at_elem, fields):
    ateds = ATElementDataSource(at_elem, mock.Mock(), fields)
    assert ateds.get_fields() == fields


@pytest.mark.parametrize('field', ['not_a_field', 1, [], 'a1', 'A_FIELD'])
def test_elem_get_value_raises_FieldException_if_nonexistent_field(at_elem,
                                                                   field):
    ateds = ATElementDataSource(at_elem, mock.Mock(), ['a_field'])
    with pytest.raises(pytac.exceptions.FieldException):
        ateds.get_value(field)


@pytest.mark.parametrize('field,value', [('x_kick', 0.1), ('y_kick', 0.01),
                                         ('f', 500), ('a1', 13), ('b0', 8),
                                         ('b1', -0.07), ('b2', 42)])
def test_elem_get_value(at_elem_preset, field, value):
    ateds = ATElementDataSource(at_elem_preset, mock.Mock(), [field])
    assert ateds.get_value(field) == value


def test_elem_get_orbit(at_elem_preset):
    ad = mock.Mock()
    ad.get_orbit.return_value = [27, 53, 741, 16, 12, 33]
    ateds = ATElementDataSource(at_elem_preset, ad, ['x', 'y'])
    assert ateds.get_value('x') == 33
    at_elem_preset.Index = 3
    assert ateds.get_value('y') == 741


def test_elem_get_value_on_Sextupole():
    s = at.elements.Sextupole('S1', 0.1, PolynomA=[50, 0, 0, 0],
                              PolynomB=[-10, 0, 0, 0])
    ateds = ATElementDataSource(s, mock.Mock(), ['x_kick', 'y_kick'])
    assert ateds.get_value('x_kick') == 1
    assert ateds.get_value('y_kick') == 5


@pytest.mark.parametrize('field', ['not_a_field', 1, [], 'a1', 'A_FIELD'])
def test_elem_set_value_raises_FieldException_if_nonexistant_field(at_elem,
                                                                   field):
    ateds = ATElementDataSource(at_elem, mock.Mock(), ['a_field'])
    with pytest.raises(pytac.exceptions.FieldException):
        ateds.set_value(field, 0)


@pytest.mark.parametrize('field', ['x_kick', 'y_kick', 'a1', 'b0', 'b1', 'b2',
                                   'f'])
def test_elem_set_value_sets_new_changes_flag(at_elem, field):
    ad = mock.Mock()
    ateds = ATElementDataSource(at_elem, ad, [field])
    ateds.set_value(field, 1)
    assert len(ad.new_changes.mock_calls) == 1
    assert ad.new_changes.mock_calls[0] == mock.call.set()


@pytest.mark.parametrize('field,attr_str', [('x_kick', 'at_elem.KickAngle[0]'),
                                            ('y_kick', 'at_elem.KickAngle[1]'),
                                            ('a1', 'at_elem.PolynomA[1]'),
                                            ('b0', 'at_elem.PolynomB[0]'),
                                            ('b1', 'at_elem.PolynomB[1]'),
                                            ('b2', 'at_elem.PolynomB[2]'),
                                            ('f', 'at_elem.Frequency')])
def test_elem_set_value(at_elem, field, attr_str):
    ateds = ATElementDataSource(at_elem, mock.Mock(), [field])
    ateds.set_value(field, 1)
    assert eval(attr_str) == 1


def test_elem_set_orbit_raises_HandleException(at_elem):
    ateds = ATElementDataSource(at_elem, mock.Mock(), ['x', 'y'])
    with pytest.raises(pytac.exceptions.HandleException):
        ateds.set_value('x', 0)
    with pytest.raises(pytac.exceptions.HandleException):
        ateds.set_value('y', 0)


def test_elem_set_value_on_Sextupole():
    s = at.elements.Sextupole('S1', 0.1, PolynomA=[0, 0, 0, 0],
                              PolynomB=[0, 0, 0, 0])
    ateds = ATElementDataSource(s, mock.Mock(), ['x_kick', 'y_kick'])
    ateds.set_value('x_kick', 1)
    ateds.set_value('y_kick', 5)
    assert s.PolynomA[0] == (5 / 0.1)
    assert s.PolynomB[0] == (- 1 / 0.1)


def test_elem_set_value_on_Quadrupole():
    q = at.elements.Quadrupole('Q1', 0.1, k=0, PolynomB=[0, 0, 0, 0])
    ateds = ATElementDataSource(q, mock.Mock(), ['b1'])
    ateds.set_value('b1', 0.5)
    assert q.PolynomB[1] == 0.5
    assert q.K == 0.5