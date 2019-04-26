import csv

import atip
import pytac
from pytac.device import BasicDevice
from pytac.exceptions import HandleException, FieldException
from softioc import builder, device


class ATIPServer(object):
    """A soft-ioc server allowing ATIP to be interfaced using EPICS, in the
    same manner as the live machine.

    **Attributes**

    Attributes:
        lattice (pytac.lattice.Lattice): An instance of a Pytac lattice with a
                                          simulator data source.
    .. Private Attributes:
           _in_records (dict): A dictionary containing all the created in
                                records and their associated element index and
                                Pytac field, i.e. {in_record: [index, field]}.
           _out_records (dict): A dictionary containing the names of all the
                                 created out records and their associated in
                                 records, i.e. {out_record.name: in_record}.
           _rb_only_records (list): A list of all the in records that do not
                                     have an associated out record.
           _feedback_records  (dict): A dictionary containing all the feedback
                                       related records, in the same format as
                                       _in_records because they are all
                                       readback only.
    """
    def __init__(self, ring_mode, limits_csv=None, feedback_csv=None,
                 mirror_csv=None):
        """
        Args:
            ring_mode (string): The ring mode to create the lattice in.
            limits_csv (string): The filepath to the .csv file from which to
                                    load the pv limits, for more information
                                    see create_csv.py.
            feedback_csv (string): The filepath to the .csv file from which to
                                    load the feedback records, for more
                                    information see create_csv.py.
        """
        self.lattice = atip.utils.loader(ring_mode, self.update_pvs)
        self._in_records = {}
        self._out_records = {}
        self._rb_only_records = []
        self._feedback_records = {}
        self._mirrored_records = {}
        print("Starting record creation.")
        self._create_records(limits_csv)
        if feedback_csv is not None:
            self._create_feedback_records(feedback_csv)
        if mirror_csv is not None:
            self._create_mirror_records(mirror_csv)
        print("Finished creating all {0} records.".format(self.total_records))

    @property
    def total_records(self):
        return sum([len(self._in_records), len(self._out_records),
                    len(self._feedback_records)])

    def update_pvs(self):
        """The callback function passed to ATSimulator during lattice creation,
        it is called each time a calculation of physics data is completed. It
        updates all the in records that do not have a corresponding out record
        with the latest values from the simulator.
        """
        for rb_record in self._rb_only_records:
            index, field = self._in_records[rb_record]
            if index == 0:
                value = self.lattice.get_value(field, units=pytac.ENG,
                                               data_source=pytac.SIM)
                rb_record.set(value)
            else:
                value = self.lattice[index-1].get_value(field, units=pytac.ENG,
                                                        data_source=pytac.SIM)
                rb_record.set(value)
            if rb_record.name in self._mirrored_records:
                self._mirrored_records[rb_record.name].set(value)

    def _create_records(self, limits_csv):
        """Create all the standard records from both lattice and element Pytac
        fields. Several assumptions have been made for simplicity and
        efficiency, these are:
            - That bend elements all share a single PV, and are the only
               family to do so.
            - That every field that has an out record (SP) will also have an in
               record (RB).
            - That all lattice fields are never setpoint and so only in records
               need to be created for them.

        Args:
            limits_csv (string): The filepath to the .csv file from which to
                                    load the pv limits.
        """
        limits_dict = {}
        if limits_csv is not None:
            csv_reader = csv.DictReader(open(limits_csv))
            for line in csv_reader:
                limits_dict[line['pv']] = (float(line['upper']),
                                           float(line['lower']),
                                           int(line['precision']))
        bend_set = False
        for element in self.lattice:
            if element.type_ == 'BEND':
                # Create bends only once as they all share a single PV.
                if not bend_set:
                    value = element.get_value('b0', units=pytac.ENG,
                                              data_source=pytac.SIM)
                    get_pv = element.get_pv_name('b0', pytac.RB)
                    upper, lower, precision = limits_dict.get(get_pv, (None,
                                                                       None,
                                                                       None))
                    builder.SetDeviceName(get_pv.split(':', 1)[0])
                    in_record = builder.aIn(get_pv.split(':', 1)[1],
                                            LOPR=lower, HOPR=upper,
                                            PREC=precision,
                                            initial_value=value)
                    set_pv = element.get_pv_name('b0', pytac.SP)
                    def on_update(value, name=set_pv):  # noqa E306
                        self._on_update(name, value)
                    upper, lower, precision = limits_dict.get(set_pv, (None,
                                                                       None,
                                                                       None))
                    builder.SetDeviceName(set_pv.split(':', 1)[0])
                    out_record = builder.aOut(set_pv.split(':', 1)[1],
                                              LOPR=lower, HOPR=upper,
                                              DRVL=lower, DRVH=upper,
                                              PREC=precision,
                                              initial_value=value,
                                              on_update=on_update)
                    # how to solve the index problem?
                    self._in_records[in_record] = (element.index, 'b0')
                    self._out_records[out_record.name] = in_record
                    bend_set = True
            else:
                # Create records for all other families.
                for field in element.get_fields()[pytac.SIM]:
                    value = element.get_value(field, units=pytac.ENG,
                                              data_source=pytac.SIM)
                    get_pv = element.get_pv_name(field, pytac.RB)
                    upper, lower, precision = limits_dict.get(get_pv, (None,
                                                                       None,
                                                                       None))
                    builder.SetDeviceName(get_pv.split(':', 1)[0])
                    in_record = builder.aIn(get_pv.split(':', 1)[1],
                                            LOPR=lower, HOPR=upper,
                                            PREC=precision,
                                            initial_value=value)
                    self._in_records[in_record] = (element.index, field)
                    try:
                        set_pv = element.get_pv_name(field, pytac.SP)
                    except HandleException:
                        self._rb_only_records.append(in_record)
                    else:
                        def on_update(value, name=set_pv):
                            self._on_update(name, value)
                        upper, lower, precision = limits_dict.get(set_pv,
                                                                  (None, None,
                                                                   None))
                        builder.SetDeviceName(set_pv.split(':', 1)[0])
                        out_record = builder.aOut(set_pv.split(':', 1)[1],
                                                  LOPR=lower, HOPR=upper,
                                                  DRVL=lower, DRVH=upper,
                                                  PREC=precision,
                                                  initial_value=value,
                                                  on_update=on_update)
                        self._out_records[out_record.name] = in_record
        # Now for lattice fields
        lat_fields = self.lattice.get_fields()
        for field in set(lat_fields[pytac.LIVE]) & set(lat_fields[pytac.SIM]):
            # Ignore basic devices as they do not have PVs.
            if not isinstance(self.lattice.get_device(field), BasicDevice):
                get_pv = self.lattice.get_pv_name(field, pytac.RB)
                value = self.lattice.get_value(field, units=pytac.ENG,
                                               data_source=pytac.SIM)
                builder.SetDeviceName(get_pv.split(':', 1)[0])
                in_record = builder.aIn(get_pv.split(':', 1)[1], PREC=4,
                                        initial_value=value)
                self._in_records[in_record] = (0, field)
                self._rb_only_records.append(in_record)
        print("~*~*Woah, we're halfway there, Wo-oah...*~*~")

    def _create_feedback_records(self, feedback_csv):
        """Create all the feedback records from the .csv file at the location
        passed, see create_csv.py for more information.

        Args:
            feedback_csv (string): The filepath to the .csv file from which to
                                    load the records.
        """
        csv_reader = csv.DictReader(open(feedback_csv))
        for line in csv_reader:
            prefix, pv = line['pv'].split(':', 1)
            builder.SetDeviceName(prefix)
            in_record = builder.longIn(pv, initial_value=int(line['value']))
            self._feedback_records[(int(line['index']),
                                    line['field'])] = in_record

        # Storage ring electron BPMs enabled
        # Special case: since cannot currently create waveform records via CSV,
        # create by hand and add to list of feedback records
        N_BPM = len(self.lattice.get_elements('BPM'))
        builder.SetDeviceName("SR-DI-EBPM-01")
        bpm_enabled_record = builder.Waveform("ENABLED", NELM=N_BPM,
                                              initial_value=[0] * N_BPM)
        self._feedback_records[(0, "bpm_enabled")] = bpm_enabled_record

    def _create_mirror_records(self, mirror_csv):
        all_in_records = (self._in_records.keys() +
                          self._feedback_records.values())
        record_names = {rec.name: rec for rec in all_in_records}
        csv_reader = csv.DictReader(open(mirror_csv))
        for line in csv_reader:
            prefix, pv = line['mirror'].split(':', 1)
            builder.SetDeviceName(prefix)
            if isinstance(record_names[line['original']]._RecordWrapper__device,
                          device.ai):
                mirror = builder.aIn(pv, initial_value=float(line['value']))
            elif isinstance(record_names[line['original']]._RecordWrapper__device,
                            device.longin):
                mirror = builder.aIn(pv, initial_value=float(line['value']))
            else:
                raise TypeError("Type {0} doesn't currently support mirroring,"
                                " please only mirror aIn and longIn records."
                                .format(type(line['original']._RecordWrapper__device)))
            self._mirrored_records[line['original']] = mirror

    def _on_update(self, name, value):
        """The callback function passed to out records, it is called after
        successful record processing has been completed. It updates the out
        record's corresponding in record with the value that has been set and
        then sets the value to the centralised Pytac lattice.

        Args:
            name (str): The name of record object that has just been set to.
            value (number): The value that has just been set to the record.
        """
        in_record = self._out_records[name]
        index, field = self._in_records[in_record]
        self.lattice[index-1].set_value(field, value, units=pytac.ENG,
                                        data_source=pytac.SIM)
        in_record.set(value)
        if in_record.name in self._mirrored_records:
            self._mirrored_records[in_record.name].set(value)

    def set_feedback_record(self, index, field, value):
        """Set a value to the feedback in records, possible fields are:
            ['x_fofb_disabled', 'x_sofb_disabled', 'y_fofb_disabled',
             'y_sofb_disabled', 'h_fofb_disabled', 'h_sofb_disabled',
             'v_fofb_disabled', 'v_sofb_disabled', 'error_sum', 'enabled',
             'state', 'beam_current', feedback_status', 'bpm_enabled']

        Args:
            index (int): The index of the element on which to set the value;
                          starting from 1, 0 is used to set on the lattice.
            field (string): The field to set the value to.
            value (number): The value to be set.

        Raises:
            pytac.exceptions.FieldException: If the lattice or element does
                                              not have the specified field.
        """
        try:
            self._feedback_records[(index, field)].set(value)
        except KeyError:
            if index == 0:
                raise FieldException("Lattice {0} does not have field {1}."
                                     .format(self.lattice, field))
            else:
                raise FieldException("Element {0} does not have field {1}."
                                     .format(self.lattice[index], field))
