import numpy
import pytac
import at
from threading import Thread
from functools import partial
from pytac.data_source import DataSource
from pytac.exceptions import FieldException, HandleException
try:
    from Queue import Queue  # with a python version < 3.0
except ImportError:
    from queue import Queue  # with a python version >=3.0 and <3.6
except ModuleNotFoundError:
    from queue import Queue  # with a python version >= 3.6


class ATElementDataSource(DataSource):
    def __init__(self, at_element, accelerator_data, fields=[]):
        self._field_functions = {'a1': partial(self.PolynomA, cell=1),
                                 'b0': partial(self.PolynomB, cell=0),
                                 'b1': partial(self.PolynomB, cell=1),
                                 'b2': partial(self.PolynomB, cell=2),
                                 'x': partial(self.Orbit, cell=0),
                                 'y': partial(self.Orbit, cell=2),
                                 'f': self.Frequency,
                                 'x_kick': self.x_kick,
                                 'y_kick': self.y_kick}
        self.units = pytac.PHYS
        self._element = at_element
        self._ad = accelerator_data
        self._fields = fields

    def get_value(self, field, handle=None):
        if field in self._fields:
            return self._field_functions[field](value=None)
        else:
            raise FieldException("No field {0} on AT element {1}."
                                 .format(field, self._element))

    def set_value(self, field, set_value):
        if field in self._fields:
            self._field_functions[field](value=set_value)
        else:
            raise FieldException("No field {0} on AT element {1}."
                                 .format(field, self._element))

    def get_fields(self):
        return self._fields

    def PolynomA(self, cell, value):
        # use value as get/set flag as well as the set value.
        if value is None:
            return self._element.PolynomA[cell]
        else:
            self._element.PolynomA[cell] = value
            self._ad.new_changes = True

    def PolynomB(self, cell, value):
        if value is None:
            return self._element.PolynomB[cell]
        else:
            if isinstance(self._element, at.elements.Quadrupole):
                self._element.K = value
            self._element.PolynomB[cell] = value
            self._ad.new_changes = True

    def Orbit(self, cell, value):
        index = self._element.Index-1
        if value is None:
            return float(self._ad.get_twiss()[3]['closed_orbit'][:,
                                                                 cell][index])
        else:
            field = 'x' if cell is 0 else 'y'
            raise HandleException("Field {0} cannot be set on element data "
                                  "source {1}.".format(field, self))

    def Frequency(self, value):
        if value is None:
            return self._element.Frequency
        else:
            self._element.Frequency = value
            self._ad.new_changes = True

    def x_kick(self, value):
        if isinstance(self._element, at.elements.Sextupole):
            if value is None:
                return (- self._element.PolynomB[0] * self._element.Length)
            else:
                self._element.PolynomB[0] = (- value / self._element.Length)
                self._ad.new_changes = True
        else:
            if value is None:
                return self._element.KickAngle[0]
            else:
                self._element.KickAngle[0] = value
                self._ad.new_changes = True

    def y_kick(self, value):
        if isinstance(self._element, at.elements.Sextupole):
            if value is None:
                return (self._element.PolynomA[0] * self._element.Length)
            else:
                self._element.PolynomA[0] = (value / self._element.Length)
                self._ad.new_changes = True
        else:
            if value is None:
                return self._element.KickAngle[1]
            else:
                self._element.KickAngle[1] = value
                self._ad.new_changes = True


class ATLatticeDataSource(DataSource):
    def __init__(self, accelerator_data):
        self.units = pytac.PHYS
        self._ad = accelerator_data
        self._field2twiss = {'x': partial(self.read_closed_orbit, field=0),
                             'phase_x': partial(self.read_closed_orbit, field=1),
                             'y': partial(self.read_closed_orbit, field=2),
                             'phase_y': partial(self.read_closed_orbit, field=3),
                             'm44': partial(self.read_twiss3, field='m44'),
                             's_position': partial(self.read_twiss3, field='s_pos'),
                             'alpha': partial(self.read_twiss3, field='alpha'),
                             'beta': partial(self.read_twiss3, field='beta'),
                             'mu': partial(self.read_twiss3, field='mu'),
                             'dispersion': partial(self.read_twiss3, field='dispersion'),
                             'tune_x': partial(self.read_tune, field=0),
                             'tune_y': partial(self.read_tune, field=1),
                             'chromaticity_x': partial(self.read_chrom, field=0),
                             'chromaticity_y': partial(self.read_chrom, field=1),
                             'energy': self.get_energy}

    def get_value(self, field, handle=None):
        if field in self._field2twiss.keys():
            return self._field2twiss[field]()
        else:
            raise FieldException("Lattice data source {0} does not have field "
                                 "{1}".format(self, field))

    def set_value(self, field):
        raise HandleException("Field {0} cannot be set on lattice data source "
                              "{0}.".format(field, self))

    def get_fields(self):
        return self._field2twiss.keys()

    def read_closed_orbit(self, field):
        return self._ad.get_twiss()[3]['closed_orbit'][:, field]

    def read_twiss3(self, field):
        return self._ad.get_twiss()[3][field]

    def read_tune(self, field):
        return (self._ad.get_twiss()[1][field] % 1)

    def read_chrom(self, field):
        return self._ad.get_twiss()[2][field]

    def get_energy(self):
        return float(self._ad.get_ring()[0].Energy)


class ATAcceleratorData(object):
    def __init__(self, ring, threads):
        self._ring = ring
        self._thread_number = threads
        self.new_changes = True
        self._rp = numpy.ones(len(self._ring), dtype=bool)
        self._twiss = at.physics.get_twiss(self._ring, refpts=self._rp,
                                           get_chrom=True)
        for i in range(self._thread_number):
            update = Thread(target=self.recalculate_twiss)
            update.setDaemon(True)
            update.start()

    def recalculate_twiss(self):
        while True:
            if self.new_changes is True:
                self._twiss = at.physics.get_twiss(self._ring, refpts=self._rp,
                                                   get_chrom=True)
                self.new_changes = False

    def get_twiss(self):
        return self._twiss

    def get_element(self, index):
        return self._ring[index-1]

    def get_ring(self):
        return self._ring
